#!/usr/bin/env python3
"""
Initialise le repo GitHub infra-provisioned :
  - bootstrap terraform/
  - workflow terraform-standard.yml

Usage:
  export GITHUB_TOKEN=...
  export GITHUB_OWNER=Lsabir
  export GITHUB_INFRA_REPO=infra-provisioned
  python scripts/setup_infra_provisioned.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass

from agent.config import load_config
from agent.github_manager import GitHubManager


def main() -> None:
    cfg = load_config()
    gh = GitHubManager(cfg)
    url = gh.ensure_repo_exists()
    print(f"Repo : {url}")
    pipeline_new = gh.ensure_standard_pipeline()
    print("Pipeline :", "installé/mis à jour" if pipeline_new else "déjà à jour")
    boot_new = gh.bootstrap_infra_repo()
    print("Bootstrap terraform/ :", "créé" if boot_new else "déjà présent")
    ctx = gh.get_repo_context()
    print(f"Fichiers .tf lus : {len(ctx)} — {', '.join(sorted(ctx.keys())[:10])}")
    print("\nProchaine étape : ajouter les secrets AZURE_CREDENTIALS et SSH_PUBLIC_KEY")
    print(f"sur https://github.com/{cfg.github_owner}/{cfg.github_infra_repo}/settings/secrets/actions")


if __name__ == "__main__":
    main()
