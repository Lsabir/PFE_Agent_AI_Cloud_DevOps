"""
config.py — Configuration centrale de l'Agent IA DevOps
Lit les paramètres depuis les variables d'environnement ou Azure Key Vault.
"""

import os
from dataclasses import dataclass, field


@dataclass
class AgentConfig:

    # ── Azure OpenAI ────────────────────────────────────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-4"
    azure_openai_api_version: str = "2024-02-01"

    # ── GitHub ──────────────────────────────────────────────────────────────
    github_token: str = ""
    github_owner: str = ""
    github_infra_repo: str = "infra-provisioned"

    # ── Jira ────────────────────────────────────────────────────────────────
    jira_url: str = ""            # ex: https://yourcompany.atlassian.net
    jira_email: str = ""          # email du compte Jira
    jira_api_token: str = ""      # token API généré sur id.atlassian.com
    jira_project_key: str = ""    # clé du projet, ex: INFRA ou DEV

    # ── Azure Key Vault (optionnel) ─────────────────────────────────────────
    keyvault_url: str = ""
    use_keyvault: bool = False

    # ── Valeurs par défaut ──────────────────────────────────────────────────
    default_location: str = "germanywestcentral"
    default_environment: str = "dev"
    naming_prefix: str = "infra-prov"


def load_config() -> AgentConfig:
    """
    Charge la configuration depuis Azure Key Vault (prioritaire) puis les
    variables d'environnement en fallback.
    Le Key Vault est activé automatiquement dès que AZURE_KEYVAULT_URL est
    défini, sauf si USE_KEYVAULT=false est explicitement positionné.
    """

    kv_url = os.getenv("AZURE_KEYVAULT_URL", "")
    # Auto-activation : KV actif si l'URL est présente et non désactivé explicitement
    use_keyvault = kv_url != "" and os.getenv("USE_KEYVAULT", "true").lower() != "false"

    cfg = AgentConfig(
        azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
        azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
        azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        github_token=os.getenv("GITHUB_TOKEN", ""),
        github_owner=os.getenv("GITHUB_OWNER", ""),
        github_infra_repo=os.getenv("GITHUB_INFRA_REPO", "infra-provisioned"),
        jira_url=os.getenv("JIRA_URL", ""),
        jira_email=os.getenv("JIRA_EMAIL", ""),
        jira_api_token=os.getenv("JIRA_API_TOKEN", ""),
        jira_project_key=os.getenv("JIRA_PROJECT_KEY", ""),
        keyvault_url=kv_url,
        use_keyvault=use_keyvault,
        default_location=os.getenv("DEFAULT_LOCATION", "swedencentral"),
        default_environment=os.getenv("DEFAULT_ENVIRONMENT", "dev"),
        naming_prefix=os.getenv("NAMING_PREFIX", "infra-prov"),
    )

    if cfg.use_keyvault and cfg.keyvault_url:
        cfg = _load_from_keyvault(cfg)

    _validate_config(cfg)
    return cfg


def _load_from_keyvault(cfg: AgentConfig) -> AgentConfig:
    """
    Lit les secrets depuis Azure Key Vault (source de vérité).
    Les variables d'environnement servent de fallback si un secret est absent.
    Utilise DefaultAzureCredential : Managed Identity sur VM, az login en local.
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=cfg.keyvault_url, credential=credential)

        def get_secret(name: str, fallback: str) -> str:
            try:
                value = client.get_secret(name).value
                return value if value else fallback
            except Exception:
                return fallback

        cfg.github_token          = get_secret("github-token",           cfg.github_token)
        cfg.github_owner          = get_secret("github-owner",           cfg.github_owner)
        cfg.azure_openai_api_key  = get_secret("azure-openai-key",       cfg.azure_openai_api_key)
        cfg.azure_openai_endpoint = get_secret("azure-openai-endpoint",  cfg.azure_openai_endpoint)
        cfg.jira_url              = get_secret("jira-url",               cfg.jira_url)
        cfg.jira_email            = get_secret("jira-email",             cfg.jira_email)
        cfg.jira_api_token        = get_secret("jira-api-token",         cfg.jira_api_token)
        cfg.jira_project_key      = get_secret("jira-project-key",       cfg.jira_project_key)

        print(f"[INFO] Secrets chargés depuis Key Vault : {cfg.keyvault_url}")

    except ImportError:
        print("[WARN] azure-keyvault-secrets non installé, utilisation des env vars.")
    except Exception as e:
        print(f"[WARN] Impossible de lire Key Vault ({e}), fallback sur env vars.")

    return cfg


def _validate_config(cfg: AgentConfig) -> None:
    errors = []
    if not cfg.azure_openai_endpoint:
        errors.append("AZURE_OPENAI_ENDPOINT manquant")
    if not cfg.azure_openai_api_key:
        errors.append("AZURE_OPENAI_API_KEY manquant")
    if not cfg.github_token:
        errors.append("GITHUB_TOKEN manquant")
    if not cfg.github_owner:
        errors.append("GITHUB_OWNER manquant")
    if not cfg.jira_url:
        errors.append("JIRA_URL manquant (ex: https://yourcompany.atlassian.net)")
    if not cfg.jira_email:
        errors.append("JIRA_EMAIL manquant")
    if not cfg.jira_api_token:
        errors.append("JIRA_API_TOKEN manquant")
    if not cfg.jira_project_key:
        errors.append("JIRA_PROJECT_KEY manquant (ex: INFRA)")
    if errors:
        raise EnvironmentError(
            "Configuration incomplète :\n" + "\n".join(f"  ✗ {e}" for e in errors)
        )
