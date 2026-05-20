"""
push_secrets_to_keyvault.py — Pousse tous les secrets depuis .env vers Azure Key Vault.

Usage :
    python scripts/push_secrets_to_keyvault.py

Prérequis :
    pip install azure-identity azure-keyvault-secrets python-dotenv
    az login  (ou Managed Identity / Service Principal actif)

Le script lit AZURE_KEYVAULT_URL depuis .env (ou l'env) et nécessite que
le compte courant ait le rôle "Key Vault Secrets Officer" sur le vault.
"""

import os
import sys

try:
    from dotenv import dotenv_values
except ImportError:
    print("❌ python-dotenv manquant : pip install python-dotenv")
    sys.exit(1)

try:
    from azure.identity import DefaultAzureCredential, AzureCliCredential
    from azure.keyvault.secrets import SecretClient
    from azure.core.exceptions import HttpResponseError
except ImportError:
    print("❌ azure-identity / azure-keyvault-secrets manquants :")
    print("   pip install azure-identity azure-keyvault-secrets")
    sys.exit(1)


# ── Mapping : variable d'env → nom du secret dans Key Vault ──────────────────
SECRET_MAP = {
    "GITHUB_TOKEN":          "github-token",
    "GITHUB_OWNER":          "github-owner",
    "AZURE_OPENAI_API_KEY":  "azure-openai-key",
    "AZURE_OPENAI_ENDPOINT": "azure-openai-endpoint",
    "JIRA_URL":              "jira-url",
    "JIRA_EMAIL":            "jira-email",
    "JIRA_API_TOKEN":        "jira-api-token",
    "JIRA_PROJECT_KEY":      "jira-project-key",
}

# Variables de config non-sensibles (non poussées dans KV)
NON_SECRET_VARS = {
    "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION",
    "GITHUB_INFRA_REPO", "DEFAULT_LOCATION", "DEFAULT_ENVIRONMENT",
    "NAMING_PREFIX", "USE_KEYVAULT", "AZURE_KEYVAULT_URL",
}


def load_env_values(env_file: str = ".env") -> dict:
    values = {}
    if os.path.exists(env_file):
        values = dict(dotenv_values(env_file))
        print(f"✅ .env chargé depuis {env_file}")
    # Les variables d'environnement système ont la priorité
    for key in list(SECRET_MAP) + ["AZURE_KEYVAULT_URL"]:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def get_keyvault_client(vault_url: str) -> SecretClient:
    try:
        # Essaie AzureCliCredential d'abord (az login local)
        cred = AzureCliCredential()
        client = SecretClient(vault_url=vault_url, credential=cred)
        # Test rapide
        client.list_properties_of_secrets(max_page_size=1)
        print("✅ Authentification via Azure CLI")
        return client
    except Exception:
        pass

    # Fallback : DefaultAzureCredential (Managed Identity, env vars SP, etc.)
    cred = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=cred)
    print("✅ Authentification via DefaultAzureCredential")
    return client


def push_secrets(client: SecretClient, values: dict, dry_run: bool = False) -> None:
    ok, skip, fail = [], [], []

    for env_var, secret_name in SECRET_MAP.items():
        value = values.get(env_var, "").strip()
        if not value:
            skip.append(f"  ⚠  {env_var} vide — ignoré")
            continue

        if dry_run:
            ok.append(f"  [DRY-RUN] {env_var} → {secret_name}")
            continue

        try:
            client.set_secret(secret_name, value)
            ok.append(f"  ✅ {env_var} → {secret_name}")
        except HttpResponseError as e:
            fail.append(f"  ❌ {env_var} → {secret_name} : {e.message}")

    print("\n── Résultats ────────────────────────────────────────────────────")
    for line in ok + skip + fail:
        print(line)
    print(f"\nTotal : {len(ok)} poussés, {len(skip)} ignorés, {len(fail)} erreurs")

    if fail:
        print("\n⚠  Vérifiez que votre compte a le rôle 'Key Vault Secrets Officer'")
        print("   sur le vault :", client.vault_url)
        sys.exit(1)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pousse les secrets vers Azure Key Vault")
    parser.add_argument("--env-file", default=".env", help="Chemin vers le fichier .env")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans écriture")
    args = parser.parse_args()

    values = load_env_values(args.env_file)

    vault_url = values.get("AZURE_KEYVAULT_URL", "").strip()
    if not vault_url:
        print("❌ AZURE_KEYVAULT_URL non défini dans .env ou l'environnement")
        sys.exit(1)

    print(f"\n🔐 Key Vault cible : {vault_url}")
    if args.dry_run:
        print("⚠  Mode DRY-RUN : aucune écriture effectuée\n")

    client = get_keyvault_client(vault_url)
    push_secrets(client, values, dry_run=args.dry_run)

    if not args.dry_run:
        print("\n✅ Terminé. Le fichier .env local n'est plus nécessaire pour les secrets.")
        print("   Conservez uniquement les variables non-sensibles dans .env :")
        for v in sorted(NON_SECRET_VARS):
            val = values.get(v, "")
            if val:
                print(f"   {v}={val}")


if __name__ == "__main__":
    main()
