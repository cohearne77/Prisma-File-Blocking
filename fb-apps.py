from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import threading
import time
import urllib.parse
import uuid
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ------------------------------------------------------
# Configuration
# ------------------------------------------------------
CLIENT_ID = "co-sase@1784958932.iam.panserviceaccount.com"
CLIENT_SECRET = "76c1ad57-1307-4ab1-b856-86cf8bd9a76f"
TSG_ID = "1784958932"

# True  = Exact 1,089 apps (~10-12 mins via pan.dev)
# False = 1,049 transfers_files subset (~2.5-3 mins via pan.dev)
FULL_CATALOG_SCAN = True

# ------------------------------------------------------
# Official pan.dev Endpoints
# ------------------------------------------------------
AUTH_URL = "https://auth.apps.paloaltonetworks.com/oauth2/access_token"
APPS_URL = "https://api.strata.paloaltonetworks.com/config/objects/v1/applications"
FB_PROFILES_URL = "https://api.strata.paloaltonetworks.com/config/security/v1/file-blocking-profiles"


def create_session() -> requests.Session:
    retry_strategy = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST", "DELETE"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session = requests.Session()
    session.mount("https://", adapter)
    return session


class RateLimiter:
    """Paces requests (~4.5 req/sec) and coordinates brief pauses on 429 responses."""

    def __init__(self, min_interval: float = 0.22):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.time()
            sleep_for = self._next_allowed - now
            if sleep_for > 0:
                self._next_allowed += self.min_interval
            else:
                self._next_allowed = now + self.min_interval
                sleep_for = 0.0
        if sleep_for > 0:
            time.sleep(sleep_for)

    def backoff(self, seconds: float) -> None:
        with self._lock:
            self._next_allowed = max(self._next_allowed, time.time() + seconds)


class TokenManager:
    """Thread-safe OAuth2 token manager with automatic refresh before 15-min expiry."""

    def __init__(self, session: requests.Session, client_id: str, client_secret: str, tsg_id: str):
        self.session = session
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.tsg_id = tsg_id.strip().removeprefix("tsg_id:")
        self._token = None
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def get_headers(self, force_refresh: bool = False) -> dict:
        with self._lock:
            if force_refresh or not self._token or (time.time() - self._fetched_at) > 720:
                self._refresh_token()
            return {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

    def _refresh_token(self) -> None:
        resp = self.session.post(
            AUTH_URL,
            auth=(
                urllib.parse.quote(self.client_id, safe=""),
                urllib.parse.quote(self.client_secret, safe=""),
            ),
            data={"grant_type": "client_credentials", "scope": f"tsg_id:{self.tsg_id}"},
            timeout=30,
        )
        if resp.status_code == 401 and "invalid_client" in resp.text:
            resp = self.session.post(
                AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": f"tsg_id:{self.tsg_id}",
                },
                timeout=30,
            )
        if resp.status_code != 200:
            raise RuntimeError(f"OAuth failed ({resp.status_code}): {resp.text}")

        self._token = resp.json()["access_token"]
        self._fetched_at = time.time()


def api_request(
    session: requests.Session,
    token_mgr: TokenManager,
    limiter: RateLimiter,
    method: str,
    url: str,
    **kwargs,
) -> requests.Response:
    for _ in range(8):
        limiter.wait()
        resp = session.request(method, url, headers=token_mgr.get_headers(), **kwargs)

        if resp.status_code == 401:
            resp = session.request(
                method, url, headers=token_mgr.get_headers(force_refresh=True), **kwargs
            )

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", "2"))
            limiter.backoff(retry_after)
            continue

        return resp

    resp.raise_for_status()
    return resp


def fetch_candidates(
    session: requests.Session, token_mgr: TokenManager, limiter: RateLimiter
) -> list[str]:
    limit = 500
    first_resp = api_request(
        session,
        token_mgr,
        limiter,
        "GET",
        APPS_URL,
        params={"folder": "All", "limit": limit, "offset": 0},
        timeout=(10, 60),
    )
    first_resp.raise_for_status()
    first_payload = first_resp.json()
    total = first_payload.get("total", 0)
    all_apps = list(first_payload.get("data", []))

    offsets = list(range(limit, total, limit))

    def fetch_page(page_offset: int) -> list[dict]:
        r = api_request(
            session,
            token_mgr,
            limiter,
            "GET",
            APPS_URL,
            params={"folder": "All", "limit": limit, "offset": page_offset},
            timeout=(10, 60),
        )
        r.raise_for_status()
        return r.json().get("data", [])

    with ThreadPoolExecutor(max_workers=4) as executor:
        for batch in executor.map(fetch_page, offsets):
            all_apps.extend(batch)

    # Deduplicate by application name
    unique_apps = {app["name"]: app for app in all_apps if app.get("name")}

    if FULL_CATALOG_SCAN:
        # Exclude raw IP-number protocols and non-file-transfer ICS apps (never have file decoders)
        candidates = sorted(
            name
            for name, app in unique_apps.items()
            if app.get("snippet") == "predefined-snippet"
            and not app.get("ident_by_ip_protocol")
            and not (app.get("subcategory") == "ics-protocols" and not app.get("transfers_files"))
        )
    else:
        candidates = sorted(
            name
            for name, app in unique_apps.items()
            if app.get("transfers_files") is True
        )

    print(
        f"Fetched {len(all_apps)} records ({len(unique_apps)} unique apps) "
        f"| Candidates to validate: {len(candidates)}"
    )
    return candidates


def extract_rejected_apps(resp: requests.Response, app_set: set[str]) -> set[str]:
    try:
        err_json = resp.json()
        messages = " ".join(json.dumps(err) for err in err_json.get("_errors", []))
    except ValueError:
        messages = resp.text

    tokens = set(re.findall(r"\b([a-z0-9][a-z0-9._-]+)\b", messages))
    return tokens & app_set


def validate_batch(
    session: requests.Session,
    token_mgr: TokenManager,
    limiter: RateLimiter,
    app_list: list[str],
    progress_cb=None,
) -> list[str]:
    if not app_list:
        return []

    body = {
        "name": f"tmp-fb-validate-{uuid.uuid4().hex[:8]}",
        "rules": [
            {
                "name": "schema-validation-rule",
                "action": "alert",
                "application": app_list,
                "direction": "both",
                "file_type": ["any"],
            }
        ],
    }

    resp = api_request(
        session,
        token_mgr,
        limiter,
        "POST",
        FB_PROFILES_URL,
        params={"folder": "Shared"},
        json=body,
        timeout=(10, 60),
    )

    if resp.status_code in (200, 201):
        profile_id = resp.json().get("id")
        if profile_id:
            del_resp = api_request(
                session,
                token_mgr,
                limiter,
                "DELETE",
                f"{FB_PROFILES_URL}/{profile_id}",
                timeout=30,
            )
            del_resp.raise_for_status()
        if progress_cb:
            progress_cb(len(app_list), len(app_list))
        return app_list

    if resp.status_code != 400:
        resp.raise_for_status()

    rejected = extract_rejected_apps(resp, set(app_list))
    if rejected:
        if progress_cb:
            progress_cb(len(rejected), 0)
        remaining = [app for app in app_list if app not in rejected]
        return validate_batch(session, token_mgr, limiter, remaining, progress_cb)

    if len(app_list) == 1:
        if progress_cb:
            progress_cb(1, 0)
        return []

    mid = len(app_list) // 2
    return (
        validate_batch(session, token_mgr, limiter, app_list[:mid], progress_cb)
        + validate_batch(session, token_mgr, limiter, app_list[mid:], progress_cb)
    )


def main():
    start_time = time.time()
    session = create_session()
    limiter = RateLimiter(min_interval=0.22)
    token_mgr = TokenManager(session, CLIENT_ID, CLIENT_SECRET, TSG_ID)

    print("Step 1: Fetching applications from pan.dev API...")
    candidates = fetch_candidates(session, token_mgr, limiter)

    print(f"\nStep 2: Validating {len(candidates)} candidates against File Blocking profile schema...")
    chunk_size = 100
    chunks = [candidates[i : i + chunk_size] for i in range(0, len(candidates), chunk_size)]

    lock = threading.Lock()
    stats = {"checked": 0, "supported": 0, "last_print": 0}

    def on_progress(checked_delta: int, supported_delta: int) -> None:
        with lock:
            stats["checked"] += checked_delta
            stats["supported"] += supported_delta
            if stats["checked"] - stats["last_print"] >= 100 or stats["checked"] == len(candidates):
                stats["last_print"] = stats["checked"]
                elapsed = round(time.time() - start_time, 1)
                print(
                    f"[{elapsed}s] Checked {stats['checked']}/{len(candidates)} "
                    f"| Supported: {stats['supported']}"
                )

    valid_apps = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [
            executor.submit(validate_batch, session, token_mgr, limiter, chunk, on_progress)
            for chunk in chunks
        ]
        for future in as_completed(futures):
            valid_apps.extend(future.result())

    valid_apps = sorted(set(valid_apps))
    output_file = "valid_file_blocking_apps.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(valid_apps, f, indent=2)

    elapsed = round(time.time() - start_time, 1)
    print(f"\nDone in {elapsed}s! Saved {len(valid_apps)} supported File Blocking applications to '{output_file}'.")


if __name__ == "__main__":
    main()