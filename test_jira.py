import os
from dotenv import load_dotenv
load_dotenv()
import requests
from requests.auth import HTTPBasicAuth

url = os.getenv("JIRA_URL") + "/rest/api/3/search/jql"
auth = HTTPBasicAuth(os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
headers = {"Accept": "application/json"}
params = {
    "jql": 'project = "PM" AND status = "To Do" ORDER BY created DESC',
    "maxResults": 5,
    "fields": "summary,status,priority",
}
r = requests.get(url, headers=headers, auth=auth, params=params)
print("Status:", r.status_code)
if r.status_code == 200:
    issues = r.json().get("issues", [])
    print(f"Tickets To Do: {len(issues)}")
    for i in issues:
        print(f"  {i['key']}: {i['fields']['summary']}")
    if not issues:
        print("  → Aucun ticket To Do. Creer un ticket dans le projet PM sur Jira.")
else:
    print(r.text[:500])
