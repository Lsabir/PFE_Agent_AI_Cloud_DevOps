"""
workflow_template.py — Template du workflow GitHub Actions
pour l'infrastructure générée par l'agent.

Ce workflow est différent du workflow de l'infra de l'agent lui-même.
Il gère le cycle Plan → Approbation → Apply de l'infrastructure provisionnée.
"""

WORKFLOW_TEMPLATE = """\
name: Terraform Infra — Plan & Apply

on:
  pull_request:
    branches: [ main ]
    paths:
      - '{project_name}/**'
  push:
    branches: [ main ]
    paths:
      - '{project_name}/**'

jobs:
  # ──────────────────────────────────────────────────────────────────
  # JOB 1 : PLAN — s'exécute sur chaque PR et chaque push sur main
  # ──────────────────────────────────────────────────────────────────
  plan:
    name: "Terraform Plan"
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: {project_name}

    permissions:
      contents: read
      id-token: write
      pull-requests: write    # pour poster les résultats du plan en commentaire PR

    outputs:
      plan_exitcode: ${{{{ steps.plan.outputs.exitcode }}}}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Login Azure
        uses: azure/login@v2
        with:
          creds: ${{{{ secrets.AZURE_CREDENTIALS }}}}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "~1.5"

      - name: Terraform Init
        id: init
        run: terraform init -backend=false

      - name: Terraform Validate
        id: validate
        run: terraform validate

      - name: Terraform Plan
        id: plan
        run: |
          # On crée un fichier dummy pour la clé SSH si le secret est vide
          SSH_KEY="${{{{ secrets.SSH_PUBLIC_KEY }}}}"
          if [ -z "$SSH_KEY" ]; then SSH_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPdummy local"; fi
          
          terraform plan \\
            -var="ssh_public_key=$SSH_KEY" \\
            -out=tfplan \\
            -detailed-exitcode
        continue-on-error: true
        env:
          TF_VAR_environment: "{environment}"

      - name: Post Plan Result to PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const output = `## 🤖 Terraform Plan — {project_name}
            
            | Étape       | Résultat                              |
            |-------------|---------------------------------------|
            | Init        | ${{{{ steps.init.outcome }}}}             |
            | Validate    | ${{{{ steps.validate.outcome }}}}         |
            | **Plan**    | **${{{{ steps.plan.outcome }}}}**         |
            
            > Reviewez ce plan sur GitHub Actions avant de merger.
            `;
            github.rest.issues.createComment({{
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: output
            }});

      - name: Upload Plan Artifact
        if: steps.plan.outcome == 'success' || steps.plan.outcome == 'changes'
        uses: actions/upload-artifact@v4
        with:
          name: tfplan-{project_name}
          path: {project_name}/tfplan
          retention-days: 7

  # ──────────────────────────────────────────────────────────────────
  # JOB 2 : APPLY — s'exécute UNIQUEMENT sur push vers main
  #          (après merge de la PR = approbation humaine confirmée)
  # ──────────────────────────────────────────────────────────────────
  apply:
    name: "Terraform Apply"
    runs-on: ubuntu-latest
    needs: plan
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    defaults:
      run:
        working-directory: {project_name}

    # Environnement GitHub avec protection de branche et required reviewers
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
          creds: ${{{{ secrets.AZURE_CREDENTIALS }}}}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "~1.5"

      - name: Terraform Init
        run: terraform init -reconfigure -backend=false

      - name: Terraform Apply
        run: |
          terraform apply \\
            -var="ssh_public_key=${{{{ secrets.SSH_PUBLIC_KEY }}}}" \\
            -auto-approve
        env:
          TF_VAR_environment: "{environment}"
"""


def generate_workflow(project_name: str, environment: str) -> str:
    """Génère le contenu du fichier workflow pour un projet donné."""
    return WORKFLOW_TEMPLATE.format(
        project_name=project_name,
        environment=environment,
    )
