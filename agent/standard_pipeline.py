"""
<<<<<<< HEAD
standard_pipeline.py — Pipeline Terraform pour le repo infra-provisioned.
Installé automatiquement par l'agent via ensure_standard_pipeline().
"""

PIPELINE_VERSION = "2"

STANDARD_PIPELINE = """\
# pipeline-version: 2
name: Terraform — infra-provisioned
=======
standard_pipeline.py — Pipeline Terraform standard unique pour infra-provisioned.
Poussé une seule fois à la création du repo. L'agent ne génère plus de workflow
par ticket — il modifie uniquement les fichiers .tf et déclenche ce pipeline.
"""

STANDARD_PIPELINE = """\
name: Terraform — Standard Pipeline

# Déclenché automatiquement sur toute modification de fichiers .tf
# Plan  : sur chaque Pull Request
# Apply : sur merge vers main (approbation humaine via merge = validation)
>>>>>>> 09ab011fd74f9934b02a5d2b8cc5928b1dfb7e1b

on:
  pull_request:
    branches: [main]
<<<<<<< HEAD
    paths:
      - 'terraform/**'
  push:
    branches: [main]
    paths:
      - 'terraform/**'
  workflow_dispatch:

concurrency:
  group: terraform-infra-provisioned
  cancel-in-progress: false

env:
  TF_WORKING_DIR: terraform
  ARM_CLIENT_ID:       ${{ fromJSON(secrets.AZURE_CREDENTIALS).clientId }}
  ARM_CLIENT_SECRET:   ${{ fromJSON(secrets.AZURE_CREDENTIALS).clientSecret }}
  ARM_SUBSCRIPTION_ID: ${{ fromJSON(secrets.AZURE_CREDENTIALS).subscriptionId }}
  ARM_TENANT_ID:       ${{ fromJSON(secrets.AZURE_CREDENTIALS).tenantId }}

jobs:
  plan:
    name: Terraform Plan
=======
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
>>>>>>> 09ab011fd74f9934b02a5d2b8cc5928b1dfb7e1b
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    permissions:
      contents: read
<<<<<<< HEAD
      pull-requests: write

    steps:
      - uses: actions/checkout@v4
=======
      id-token: write
      pull-requests: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
>>>>>>> 09ab011fd74f9934b02a5d2b8cc5928b1dfb7e1b

      - name: Login Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
<<<<<<< HEAD
          terraform_version: "1.9.0"
          terraform_wrapper: false

      - name: Terraform Init
        working-directory: ${{ env.TF_WORKING_DIR }}
        run: terraform init -reconfigure

      - name: Terraform Validate
        id: validate
        working-directory: ${{ env.TF_WORKING_DIR }}
=======
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
>>>>>>> 09ab011fd74f9934b02a5d2b8cc5928b1dfb7e1b
        run: terraform validate -no-color

      - name: Terraform Plan
        id: plan
<<<<<<< HEAD
        working-directory: ${{ env.TF_WORKING_DIR }}
        env:
          TF_VAR_ssh_public_key: ${{ secrets.SSH_PUBLIC_KEY }}
        run: |
          set +e
          terraform plan -no-color -detailed-exitcode -out=tfplan 2>&1 | tee /tmp/plan_output.txt
          code=$?
          echo "exitcode=$code" >> "$GITHUB_OUTPUT"
          set -e
          if [ "$code" -eq 1 ]; then exit 1; fi
        continue-on-error: true

      - name: Comment PR with plan
=======
        working-directory: ${{ steps.tf_dir.outputs.dir }}
        run: |
          terraform plan -no-color -out=tfplan 2>&1 | tee /tmp/plan_output.txt
          echo "exitcode=${PIPESTATUS[0]}" >> "$GITHUB_OUTPUT"
        continue-on-error: true

      - name: Poster le résultat du Plan sur la PR
>>>>>>> 09ab011fd74f9934b02a5d2b8cc5928b1dfb7e1b
        uses: actions/github-script@v7
        if: always()
        with:
          script: |
            const fs = require('fs');
<<<<<<< HEAD
            let out = 'Sortie non disponible';
            try { out = fs.readFileSync('/tmp/plan_output.txt', 'utf8').slice(-3500); } catch (e) {}
            const ok = '${{ steps.plan.outcome }}' === 'success';
            const body = [
              `## ${ok ? '✅' : '❌'} Terraform Plan — infra-provisioned`,
              '',
              '| Étape | Résultat |',
              '|-------|----------|',
              `| validate | ${{ steps.validate.outcome }} |`,
              `| plan | ${{ steps.plan.outcome }} |`,
              '',
              '<details><summary>Plan (extrait)</summary>',
              '',
              '```',
              out,
              '```',
              '</details>',
              '',
              '> Merge sur `main` pour lancer **terraform apply**.'
=======
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
>>>>>>> 09ab011fd74f9934b02a5d2b8cc5928b1dfb7e1b
            ].join('\\n');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body
            });

<<<<<<< HEAD
      - name: Fail if plan errored
        if: steps.plan.outputs.exitcode == '1'
        run: exit 1

  apply:
    name: Terraform Apply
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main' || github.event_name == 'workflow_dispatch'
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4
=======
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
>>>>>>> 09ab011fd74f9934b02a5d2b8cc5928b1dfb7e1b

      - name: Login Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
<<<<<<< HEAD
          terraform_version: "1.9.0"
          terraform_wrapper: false

      - name: Terraform Init
        working-directory: ${{ env.TF_WORKING_DIR }}
        run: terraform init -reconfigure

      - name: Terraform Plan
        working-directory: ${{ env.TF_WORKING_DIR }}
        env:
          TF_VAR_ssh_public_key: ${{ secrets.SSH_PUBLIC_KEY }}
        run: terraform plan -out=tfplan -no-color

      - name: Terraform Apply
        working-directory: ${{ env.TF_WORKING_DIR }}
        run: terraform apply -auto-approve -no-color tfplan

      - name: Résumé
        if: always()
        working-directory: ${{ env.TF_WORKING_DIR }}
        run: |
          {
            echo "## Apply infra-provisioned"
            terraform output -json 2>/dev/null | head -c 2000 || echo "Pas de outputs"
          } >> "$GITHUB_STEP_SUMMARY"
=======
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

      - name: Terraform Init
        if: steps.tf_dir.outputs.dir != ''
        working-directory: ${{ steps.tf_dir.outputs.dir }}
        run: terraform init -backend=false

      - name: Terraform Apply
        if: steps.tf_dir.outputs.dir != ''
        working-directory: ${{ steps.tf_dir.outputs.dir }}
        run: |
          terraform apply -auto-approve -no-color 2>&1 | tee /tmp/apply_output.txt
          echo "✅ Terraform Apply terminé"
          grep -E "^(Apply complete|Error)" /tmp/apply_output.txt || tail -5 /tmp/apply_output.txt
>>>>>>> 09ab011fd74f9934b02a5d2b8cc5928b1dfb7e1b
"""


def get_standard_pipeline() -> str:
    return STANDARD_PIPELINE
