# Palo Alto SCM File Blocking App-ID Fetcher

This Python script dynamically retrieves the exact list of applications (App-IDs) that are supported by **File Blocking profiles** in Palo Alto Networks' Strata Cloud Manager (SCM). 

Because the public SASE API does not currently expose the internal decoder flags (e.g., `file_type_ident`), this script uses 100% documented, official `pan.dev` endpoints to fetch candidate applications and automatically validate them against the File Blocking schema.

## Features
* **100% Supported APIs:** Uses official `pan.dev` endpoints (no undocumented or internal UI APIs).
* **Auto-Validation:** Tests application batches against the profile schema, safely creating and immediately deleting temporary test profiles without triggering any commits.
* **Auto Token Refresh:** Seamlessly manages the 15-minute OAuth2 token lifecycle for long-running scans.
* **Rate Limit Handling:** Built-in pacing and `429 Too Many Requests` backoff management.
* **Parallel Processing:** Utilizes threading to speed up the validation process.

## Prerequisites
* Python 3.8 or higher.
* Required Python packages: `requests`, `urllib3`
* A Palo Alto SCM **Service Account** with API access.
  * The Service Account must have **Security Services read/write** permissions on the `Shared` folder (e.g., *Network Admin* or *Superuser*), as the script creates and deletes a temporary validation profile.

## Setup & Installation
1. Clone the repository and navigate to the directory.
2. Install the required dependencies:
   ```bash
   pip install requests urllib3
   ```
3. Open `fb-apps.py` and update the authentication variables at the top of the file with your Service Account details:
   ```python
   CLIENT_ID = "your-client-id@1234567890.iam.panserviceaccount.com"
   CLIENT_SECRET = "<YOUR_CLIENT_SECRET>"
   TSG_ID = "1234567890"
   ```

## Scan Modes
At the top of the script, you can toggle the `FULL_CATALOG_SCAN` variable:

* `FULL_CATALOG_SCAN = True` **(Recommended for completeness):** Scans the entire predefined app catalog to ensure 100% coverage (approx. 1,089 apps). Because it must test and strip out over 3,000 unsupported applications one by one, **this mode takes about 45-60 minutes to complete.**
* `FULL_CATALOG_SCAN = False` **(Fast mode):** Only scans apps explicitly flagged with `transfers_files=true`. This captures the vast majority of apps (approx. 1,049) and completes in about **3 minutes**. 

## Usage
Run the script from your terminal:
```bash
python fb-apps.py
```

## Output
The script will output progress to the console. Once finished, it generates a `valid_file_blocking_apps.json` file in the same directory containing a sorted list of all valid App-IDs. 

*Note: No configuration changes are committed to your SCM tenant during this process.*