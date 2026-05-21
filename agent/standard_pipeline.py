"""
standard_pipeline.py — Pipeline Terraform standard unique pour infra-provisioned.
Poussé une seule fois à la création du repo. L'agent ne génère plus de workflow
par ticket — il modifie uniquement les fichiers .tf et déclenche ce pipeline.
"""

STANDARD_PIPELINE = """\
name: Terraform — Standard Pipeline

# Plan  : sur chaque Pull Request
# Apply : sur merge vers main (approbation humaine via merge = validation)

on:
  pull_request:
    branches: [main]
    paths: ['**/*.tf', '**/*.tfvars']
  push:
    branches: [main]
    paths: ['**/*.tf', '**/*.tfvars']

concurrency:
  group: terraform-${{ github.ref }}
  cancel-in-progress: false

jobs:
# =============================================================================
# JOB 1 — PLAN (sur Pull Request uniquement)
# =============================================================================
  plan:
    name: "Terraform Plan"
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    permissions:
      contents: read
      id-token: write
      pull-requests: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Login Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Configurer les credentials Terraform (ARM)
        run: |
          echo "ARM_CLIENT_ID=$(echo '${{ secrets.AZURE_CREDENTIALS }}' | jq -r .clientId)" >> $GITHUB_ENV
          echo "ARM_CLIENT_SECRET=$(echo '${{ secrets.AZURE_CREDENTIALS }}' | jq -r .clientSecret)" >> $GITHUB_ENV
          echo "ARM_SUBSCRIPTION_ID=$(echo '${{ secrets.AZURE_CREDENTIALS }}' | jq -r .subscriptionId)" >> $GITHUB_ENV
          echo "ARM_TENANT_ID=$(echo '${{ secrets.AZURE_CREDENTIALS }}' | jq -r .tenantId)" >> $GITHUB_ENV

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "~1.9"
          terraform_wrapper: false

      - name: Détecter le dossier Terraform modifié
        id: tf_dir
        run: |
          CHANGED_DIR=$(git diff --name-only origin/${{ github.base_ref }}...HEAD \\
            | grep '\\.tf$' \\
            | xargs -I{} dirname {} \\
            | sort -u | head -1)
          if [ -z "$CHANGED_DIR" ]; then
            echo "❌ Aucun fichier .tf modifié détecté"
            exit 1
          fi
          echo "dir=$CHANGED_DIR" >> "$GITHUB_OUTPUT"
          echo "✅ Dossier Terraform : $CHANGED_DIR"

      - name: Terraform Init
        working-directory: ${{ steps.tf_dir.outputs.dir }}
        run: terraform init -backend=false

      - name: Terraform Validate
        id: validate
        working-directory: ${{ steps.tf_dir.outputs.dir }}
        run: terraform validate -no-color

      - name: Terraform Plan
        id: plan
        working-directory: ${{ steps.tf_dir.outputs.dir }}
        run: |
          set -o pipefail
          TFVARS_ARG=""
          if [ -f terraform.tfvars ]; then TFVARS_ARG="-var-file=terraform.tfvars"; fi
          terraform plan -no-color -out=tfplan $TFVARS_ARG 2>&1 | tee /tmp/plan_output.txt
          echo "exitcode=${PIPESTATUS[0]}" >> "$GITHUB_OUTPUT"
        continue-on-error: true

      - name: Poster le résultat du Plan sur la PR
        uses: actions/github-script@v7
        if: always()
        with:
          script: |
            const fs = require('fs');
            let planOutput = '';
            try {
              planOutput = fs.readFileSync('/tmp/plan_output.txt', 'utf8').slice(-3000);
            } catch(e) { planOutput = 'Sortie non disponible'; }
            const status = '${{ steps.plan.outcome }}' === 'success' ? '✅' : '❌';
            const body = [
              `## ${status} Terraform Plan — \`${{ steps.tf_dir.outputs.dir }}\``,
              '',
              `| Étape    | Résultat |`,
              `|----------|----------|`,
              `| Validate | ${{ steps.validate.outcome }} |`,
              `| Plan     | ${{ steps.plan.outcome }} |`,
              '',
              '<details><summary>Détails du plan</summary>',
              '',
              '```hcl',
              planOutput,
              '```',
              '</details>',
              '',
              '> Mergez cette PR pour déclencher le **terraform apply** automatiquement.'
            ].join('\\n');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body
            });

      - name: Échec si plan KO
        if: steps.plan.outputs.exitcode != '0' && steps.plan.outputs.exitcode != '2'
        run: exit 1

# =============================================================================
# JOB 2 — APPLY (sur push vers main = après merge de la PR)
# =============================================================================
  apply:
    name: "Terraform Apply"
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    permissions:
      contents: read
      id-token: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 2

      - name: Login Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Configurer les credentials Terraform (ARM)
        run: |
          echo "ARM_CLIENT_ID=$(echo '${{ secrets.AZURE_CREDENTIALS }}' | jq -r .clientId)" >> $GITHUB_ENV
          echo "ARM_CLIENT_SECRET=$(echo '${{ secrets.AZURE_CREDENTIALS }}' | jq -r .clientSecret)" >> $GITHUB_ENV
          echo "ARM_SUBSCRIPTION_ID=$(echo '${{ secrets.AZURE_CREDENTIALS }}' | jq -r .subscriptionId)" >> $GITHUB_ENV
          echo "ARM_TENANT_ID=$(echo '${{ secrets.AZURE_CREDENTIALS }}' | jq -r .tenantId)" >> $GITHUB_ENV

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "~1.9"
          terraform_wrapper: false

      - name: Détecter le dossier Terraform modifié
        id: tf_dir
        run: |
          CHANGED_DIR=$(git diff --name-only HEAD~1 HEAD \\
            | grep '\\.tf$' \\
            | xargs -I{} dirname {} \\
            | sort -u | head -1)
          if [ -z "$CHANGED_DIR" ]; then
            echo "Aucun .tf modifié dans ce push — apply ignoré."
            echo "dir=" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          echo "dir=$CHANGED_DIR" >> "$GITHUB_OUTPUT"
          echo "✅ Dossier Terraform : $CHANGED_DIR"

      - name: Restaurer le state Terraform
        if: steps.tf_dir.outputs.dir != ''
        uses: actions/cache/restore@v4
        with:
          path: ${{ steps.tf_dir.outputs.dir }}/terraform.tfstate
          key: tfstate-infra-provisioned
          restore-keys: |
            tfstate-infra-provisioned

      - name: Terraform Init
        if: steps.tf_dir.outputs.dir != ''
        working-directory: ${{ steps.tf_dir.outputs.dir }}
        run: terraform init -backend=false

      - name: Terraform Apply
        if: steps.tf_dir.outputs.dir != ''
        working-directory: ${{ steps.tf_dir.outputs.dir }}
        run: |
          set -o pipefail
          TFVARS_ARG=""
          if [ -f terraform.tfvars ]; then TFVARS_ARG="-var-file=terraform.tfvars"; fi
          terraform apply -auto-approve -no-color $TFVARS_ARG 2>&1 | tee /tmp/apply_output.txt
          echo "✅ Terraform Apply terminé"
          grep -E "^(Apply complete|Error)" /tmp/apply_output.txt || tail -10 /tmp/apply_output.txt

      - name: Sauvegarder le state Terraform
        if: steps.tf_dir.outputs.dir != '' && always()
        uses: actions/cache/save@v4
        with:
          path: ${{ steps.tf_dir.outputs.dir }}/terraform.tfstate
          key: tfstate-infra-provisioned
"""


def get_standard_pipeline() -> str:
    return STANDARD_PIPELINE
