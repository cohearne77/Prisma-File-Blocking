import json
import requests

ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJraWQiOiJyc2Etc2lnbi1wa2NzMS0yMDQ4LXNoYTI1Ni8xIiwiYWxnIjoiUlMyNTYifQ.eyJzdWIiOiI2MTAzZWQ4Mi04OWI5LTRlNmEtYWU2ZS1jODk1MzA4MGE3YWMiLCJjdHMiOiJPQVVUSDJfU1RBVEVMRVNTX0dSQU5UIiwiYXVkaXRUcmFja2luZ0lkIjoiOTQ0OGU4YjktNGM4OS00MjRhLTliNGQtYzE3YTA4NzFkZTQ5LTYwMDIyNzMyIiwic3VibmFtZSI6IjYxMDNlZDgyLTg5YjktNGU2YS1hZTZlLWM4OTUzMDgwYTdhYyIsImlzcyI6Imh0dHBzOi8vYXV0aC5hcHBzLnBhbG9hbHRvbmV0d29ya3MuY29tOjQ0My9hbS9vYXV0aDIiLCJ0b2tlbk5hbWUiOiJhY2Nlc3NfdG9rZW4iLCJ0b2tlbl90eXBlIjoiQmVhcmVyIiwiYXV0aEdyYW50SWQiOiJvMmI3QXVaWGdzMnVUdVpWX19vdk4xd0NxRjAiLCJhdWQiOiJjby1zYXNlQDE3ODQ5NTg5MzIuaWFtLnBhbnNlcnZpY2VhY2NvdW50LmNvbSIsIm5iZiI6MTc5NTA4OTU4NiwiZ3JhbnRfdHlwZSI6ImNsaWVudF9jcmVkZW50aWFscyIsInNjb3BlIjpbInByb2ZpbGUiLCJlbWFpbCIsInRzZ19pZDoxNzg0OTU4OTMyIl0sImF1dGhfdGltZSI6MTc5NTA4OTU4NiwicmVhbG0iOiIvIiwiZXhwIjoxNzk1MDkwNDg2LCJpYXQiOjE3OTUwODk1ODYsImV4cGlyZXNfaW4iOjkwMCwianRpIjoiUXBjYnRJUGV3Mml6OHpSVVJVTWhrWk9Jd01jIiwidHNnX2lkIjoiMTc4NDk1ODkzMiIsImFjY2VzcyI6eyJwcm46MTc4NDk1ODkzMjo6OjoiOlsibXNwX3N1cGVydXNlciIsImJhc2UiXX19.n9yhnQQqxewz4O89XC0X3eU23AWYUExPbyD6goRSc4Gez7MqLNa7_EZBJQxKfDimKeCSav5J5vX8iBl5vKm7k0cd1jTEtnmbCGqrbVupbTeF-Edj-Gh8bgZfBogRdGeN1Q60nnO6cEyL8POuIlCUuZJPCxlAy6g_n3lwvEhb-tMKR5jaadA3S1cNZ-xPlUIL1ubu5b7jREJXTJgV2MvS5IXfLyssxsROLOm1bWp_sJbZxCi8ApvgBtmtknRX1t9rZfvVRoYmMJlXCghTYScTf0n0dXKpthNe_8z2U1ibGJoarAjNenYq5X6Ek6oVRa2sEmc1rUvITub8NGkzggiCzQ".strip()
COMPLETE_URL = "https://paas-1.prod.uk.panorama.paloaltonetworks.com/api/config/v9.2/complete"

headers = {
    "x-auth-jwt": ACCESS_TOKEN,
    "Content-Type": "application/json",
    "Accept": "application/json",
}
payload = {
    "xpath": (
        "/config/devices/entry[@name='localhost.localdomain']"
        "/container/entry[@name='All']/profiles/file-blocking"
        "/entry[@name='temp']/rules/entry[@name='temp']/application/member"
    )
}

resp = requests.post(COMPLETE_URL, headers=headers, json=payload, timeout=30)
resp.raise_for_status()

completions = resp.json()["result"]["completions"]["completion"]
valid_apps = sorted(
    item["@value"]
    for item in completions
    if item.get("@type") == "application"
)

with open("valid_file_blocking_apps.json", "w", encoding="utf-8") as f:
    json.dump(valid_apps, f, indent=2)

print(f"Saved {len(valid_apps)} applications to valid_file_blocking_apps.json")