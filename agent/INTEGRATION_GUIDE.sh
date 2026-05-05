# Guide d'intégration de l'Agent dans le Repo GitHub existant
# github.com/Lsabir/PFE_Agent_AI_Cloud_DevOps

# ═══════════════════════════════════════════════════════════════════════════
# STRUCTURE FINALE DU REPO APRÈS INTÉGRATION
# ═══════════════════════════════════════════════════════════════════════════
#
# PFE_Agent_AI_Cloud_DevOps/
# ├── terraform/                       ← EXISTANT (infra de l'agent)
# │   ├── main.tf
# │   ├── variables.tf
# │   ├── providers.tf
# │   ├── backend.tf
# │   ├── outputs.tf
# │   └── modules/
# │       ├── network/
# │       ├── vm-agent/
# │       ├── keyvault/
# │       └── openai/
# │
# ├── agent/                           ← NOUVEAU (code Python de l'agent)
# │   ├── __init__.py
# │   ├── config.py
# │   ├── openai_client.py
# │   ├── github_manager.py
# │   ├── workflow_template.py
# │   └── main.py
# │
# ├── .github/
# │   └── workflows/
# │       ├── terraform.yml            ← EXISTANT (deploy infra de l'agent)
# │       └── agent-tests.yml          ← NOUVEAU (tests de l'agent Python)
# │
# ├── run_agent.py                     ← NOUVEAU
# ├── requirements.txt                 ← NOUVEAU
# ├── .env.example                     ← NOUVEAU
# ├── .gitignore                       ← MODIFIER
# └── README.md                        ← MODIFIER

# ═══════════════════════════════════════════════════════════════════════════
# ÉTAPES D'INTÉGRATION
# ═══════════════════════════════════════════════════════════════════════════

# ───────────────────────────────────────────────────────────────────────────
# ÉTAPE 1 — Cloner le repo existant
# ───────────────────────────────────────────────────────────────────────────
git clone https://github.com/Lsabir/PFE_Agent_AI_Cloud_DevOps.git
cd PFE_Agent_AI_Cloud_DevOps

# ───────────────────────────────────────────────────────────────────────────
# ÉTAPE 2 — Créer la branche pour l'agent
# ───────────────────────────────────────────────────────────────────────────
git checkout -b feature/agent-python

# ───────────────────────────────────────────────────────────────────────────
# ÉTAPE 3 — Copier les fichiers de l'agent dans le repo
# ───────────────────────────────────────────────────────────────────────────
# Copier tous les fichiers du dossier agent_project/ dans le repo :
#
# agent/                   → PFE_Agent_AI_Cloud_DevOps/agent/
# run_agent.py             → PFE_Agent_AI_Cloud_DevOps/run_agent.py
# requirements.txt         → PFE_Agent_AI_Cloud_DevOps/requirements.txt
# .env.example             → PFE_Agent_AI_Cloud_DevOps/.env.example

# ───────────────────────────────────────────────────────────────────────────
# ÉTAPE 4 — Modifier le .gitignore existant
# ───────────────────────────────────────────────────────────────────────────
# Ajouter ces lignes au .gitignore existant :
cat >> .gitignore << 'GITIGNORE'

# Agent Python
.env
.venv/
__pycache__/
*.py[cod]
GITIGNORE

# ───────────────────────────────────────────────────────────────────────────
# ÉTAPE 5 — Ajouter le workflow de tests de l'agent (optionnel)
# ───────────────────────────────────────────────────────────────────────────
# Ce workflow vérifie que le code Python de l'agent est syntaxiquement correct
# et que les imports fonctionnent — sans appeler de vraies APIs.
mkdir -p .github/workflows
cat > .github/workflows/agent-tests.yml << 'WORKFLOW'
name: Agent Python — Tests

on:
  push:
    paths:
      - 'agent/**'
      - 'requirements.txt'
  pull_request:
    paths:
      - 'agent/**'

jobs:
  lint-and-syntax:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install flake8

      - name: Syntax check
        run: python -m py_compile agent/config.py agent/openai_client.py agent/github_manager.py agent/workflow_template.py agent/main.py

      - name: Lint (non-bloquant)
        run: flake8 agent/ --max-line-length=100 --ignore=E501,W503
        continue-on-error: true
WORKFLOW

# ───────────────────────────────────────────────────────────────────────────
# ÉTAPE 6 — Modifier le workflow terraform.yml existant
# (séparer plan et apply pour l'approbation humaine sur l'infra de l'agent)
# ───────────────────────────────────────────────────────────────────────────
# Le terraform.yml actuel fait plan + apply dans le même job.
# Pour avoir une approbation humaine, il faut séparer en deux jobs.
# Remplacer le contenu de .github/workflows/terraform.yml par :

cat > .github/workflows/terraform.yml << 'TFWORKFLOW'
name: Terraform CI/CD — Infra Agent

on:
  push:
    branches: [ main ]
    paths:
      - 'terraform/**'
  pull_request:
    branches: [ main ]
    paths:
      - 'terraform/**'

jobs:
  # ── Job 1 : Plan ──────────────────────────────────────────────────────────
  plan:
    name: Terraform Plan
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
      pull-requests: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Login Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.5.0"

      - name: Terraform Init
        working-directory: terraform
        run: terraform init -reconfigure

      - name: Terraform Validate
        working-directory: terraform
        run: terraform validate

      - name: Terraform Plan
        id: plan
        working-directory: terraform
        env:
          TF_VAR_ssh_public_key: ${{ secrets.SSH_PUBLIC_KEY }}
        run: terraform plan -out=tfplan -detailed-exitcode
        continue-on-error: true

      - name: Post Plan Result to PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const planResult = '${{ steps.plan.outcome }}';
            const icon = planResult === 'success' ? '✅' : '❌';
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## ${icon} Terraform Plan\n\nRésultat : **${planResult}**\n\n> Reviewer ce plan avant d'approuver la PR.`
            });

      - name: Upload tfplan artifact
        uses: actions/upload-artifact@v4
        with:
          name: tfplan-agent-infra
          path: terraform/tfplan
          retention-days: 7

  # ── Job 2 : Apply ─────────────────────────────────────────────────────────
  # S'exécute UNIQUEMENT après merge sur main
  # Nécessite l'approbation via GitHub Environments (Settings > Environments)
  apply:
    name: Terraform Apply
    runs-on: ubuntu-latest
    needs: plan
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'

    # Configurer dans : Settings > Environments > production > Required reviewers
    environment:
      name: production

    permissions:
      contents: read
      id-token: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Login Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.5.0"

      - name: Terraform Init
        working-directory: terraform
        run: terraform init -reconfigure

      - name: Terraform Apply
        working-directory: terraform
        env:
          TF_VAR_ssh_public_key: ${{ secrets.SSH_PUBLIC_KEY }}
        run: terraform apply -auto-approve
TFWORKFLOW

# ───────────────────────────────────────────────────────────────────────────
# ÉTAPE 7 — Configurer l'environnement GitHub pour l'approbation
# ───────────────────────────────────────────────────────────────────────────
# Sur GitHub, aller dans :
# Settings → Environments → New environment → "production"
# Cocher "Required reviewers" → ajouter votre username
# Cela fait que le job "apply" attend votre approbation sur GitHub
# avant de s'exécuter, en plus de l'approbation locale de l'agent.

# ───────────────────────────────────────────────────────────────────────────
# ÉTAPE 8 — Ajouter les secrets GitHub nécessaires
# ───────────────────────────────────────────────────────────────────────────
# Dans : Settings → Secrets and variables → Actions → New repository secret

# Secrets EXISTANTS (déjà configurés pour le terraform.yml actuel) :
#   AZURE_CREDENTIALS   → JSON du Service Principal Azure
#   SSH_PUBLIC_KEY      → Clé publique SSH pour la VM

# Nouveaux secrets pour l'agent Python :
#   AZURE_OPENAI_ENDPOINT  → https://infra-agent-ai-openai.openai.azure.com/
#   AZURE_OPENAI_API_KEY   → clé d'API Azure OpenAI
#   GITHUB_TOKEN_AGENT     → Personal Access Token avec droits repo+workflow
#   (GITHUB_TOKEN est automatiquement disponible dans les workflows)

# ───────────────────────────────────────────────────────────────────────────
# ÉTAPE 9 — Committer et pousser
# ───────────────────────────────────────────────────────────────────────────
git add agent/ run_agent.py requirements.txt .env.example .gitignore
git add .github/workflows/
git commit -m "feat: add Python DevOps AI Agent

- agent/config.py        : configuration (env vars / Key Vault)
- agent/openai_client.py : analyse description + génération Terraform via GPT-4
- agent/github_manager.py: gestion GitHub (branch, push, PR, pipeline monitor)
- agent/workflow_template.py: template workflow GitHub Actions
- agent/main.py          : orchestrateur principal avec approbation humaine
- run_agent.py           : point d'entrée
- requirements.txt       : dépendances Python
- .env.example           : template configuration
- .github/workflows/terraform.yml: séparation plan/apply + env protection
- .github/workflows/agent-tests.yml: tests syntaxe Python"

git push origin feature/agent-python

# Puis créer une PR sur GitHub pour merger dans main.

# ───────────────────────────────────────────────────────────────────────────
# ÉTAPE 10 — Test local de l'agent
# ───────────────────────────────────────────────────────────────────────────
# Sur votre machine locale ou sur la VM Azure :

# 1. Installer les dépendances
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configurer
cp .env.example .env
# Éditer .env avec vos vraies valeurs

# 3. Lancer l'agent
python run_agent.py

# L'agent vous demandera :
# → Description de l'infrastructure souhaitée
# → Confirmation de l'analyse
# → Approbation du plan Terraform (après exécution du pipeline)
# → Approbation finale avant terraform apply

# ───────────────────────────────────────────────────────────────────────────
# RÉCAPITULATIF DES MODIFICATIONS SUR LE REPO EXISTANT
# ───────────────────────────────────────────────────────────────────────────
#
# AJOUTS (nouveaux fichiers) :
#   + agent/__init__.py
#   + agent/config.py
#   + agent/openai_client.py
#   + agent/github_manager.py
#   + agent/workflow_template.py
#   + agent/main.py
#   + run_agent.py
#   + requirements.txt
#   + .env.example
#   + .github/workflows/agent-tests.yml
#
# MODIFICATIONS (fichiers existants) :
#   ~ .gitignore                      → ajout .env, .venv/, __pycache__/
#   ~ .github/workflows/terraform.yml → séparation plan/apply + env protection
#
# AUCUNE MODIFICATION sur :
#   = terraform/main.tf               (inchangé)
#   = terraform/variables.tf          (inchangé)
#   = terraform/modules/              (inchangés)
#   = README.md                       (à compléter manuellement)
