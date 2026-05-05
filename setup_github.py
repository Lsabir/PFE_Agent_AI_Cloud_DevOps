"""
setup_github.py — Crée le repo infra-provisioned et configure les secrets GitHub Actions.
"""
import base64
import json
import os
import sys
import requests
from dotenv import load_dotenv
from nacl import encoding, public

load_dotenv()

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "Lsabir")
REPO_NAME    = "infra-provisioned"

AZURE_CREDENTIALS = json.dumps({
    "clientId": os.environ["ARM_CLIENT_ID"],
    "clientSecret": os.environ["ARM_CLIENT_SECRET"],
    "subscriptionId": os.environ["ARM_SUBSCRIPTION_ID"],
    "tenantId": os.environ["ARM_TENANT_ID"],
    "activeDirectoryEndpointUrl": "https://login.microsoftonline.com",
    "resourceManagerEndpointUrl": "https://management.azure.com/",
    "activeDirectoryGraphResourceId": "https://graph.windows.net/",
    "sqlManagementEndpointUrl": "https://management.core.windows.net:8443/",
    "galleryEndpointUrl": "https://gallery.azure.com/",
    "managementEndpointUrl": "https://management.core.windows.net/"
})

SSH_PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILWk5zmH/zvd1fB32CNivY1Oo5V7WrLNDFHzaA9wi+yV corp\\absabir@LMA-5CD549D7ZT"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def encrypt_secret(public_key_b64: str, secret: str) -> str:
    pk = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder())
    box = public.SealedBox(pk)
    encrypted = box.encrypt(secret.encode())
    return base64.b64encode(encrypted).decode()


def ensure_repo():
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{REPO_NAME}"
    r = requests.get(url, headers=HEADERS)
    if r.status_code == 200:
        print(f"  ✓ Repo '{REPO_NAME}' existe déjà.")
        return
    if r.status_code == 404:
        print(f"  → Création du repo '{REPO_NAME}'...")
        r2 = requests.post(
            "https://api.github.com/user/repos",
            headers=HEADERS,
            json={"name": REPO_NAME, "description": "Infrastructure as Code - Agent IA DevOps", "private": False, "auto_init": True},
        )
        r2.raise_for_status()
        print(f"  ✓ Repo créé : {r2.json()['html_url']}")
    else:
        r.raise_for_status()


def set_secret(secret_name: str, secret_value: str):
    # Récupère la clé publique du repo
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{REPO_NAME}/actions/secrets/public-key"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    key_data = r.json()
    key_id = key_data["key_id"]
    pub_key = key_data["key"]

    encrypted = encrypt_secret(pub_key, secret_value)

    url2 = f"https://api.github.com/repos/{GITHUB_OWNER}/{REPO_NAME}/actions/secrets/{secret_name}"
    r2 = requests.put(url2, headers=HEADERS, json={"encrypted_value": encrypted, "key_id": key_id})
    if r2.status_code in (201, 204):
        print(f"  ✓ Secret '{secret_name}' configuré.")
    else:
        print(f"  ✗ Erreur secret '{secret_name}': {r2.status_code} {r2.text}")


def create_environment():
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{REPO_NAME}/environments/production"
    r = requests.put(url, headers=HEADERS, json={"wait_timer": 0})
    if r.status_code in (200, 201):
        print("  ✓ Environnement 'production' créé.")
    else:
        print(f"  ⚠ Environnement: {r.status_code} {r.text[:100]}")


if __name__ == "__main__":
    print("\n=== Setup repo infra-provisioned ===\n")
    ensure_repo()
    import time; time.sleep(2)
    set_secret("AZURE_CREDENTIALS", AZURE_CREDENTIALS)
    set_secret("SSH_PUBLIC_KEY", SSH_PUBLIC_KEY)
    create_environment()
    print("\n✅ Setup terminé. Le repo est prêt pour GitHub Actions.")
