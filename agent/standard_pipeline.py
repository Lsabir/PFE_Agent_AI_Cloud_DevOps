"""
standard_pipeline.py — Pipeline Terraform pour le repo infra-provisioned.
Installé automatiquement par l'agent via ensure_standard_pipeline().
"""

PIPELINE_VERSION = "2"

STANDARD_PIPELINE = """\
# pipeline-version: 2
name: Terraform — infra-provisioned

on:
  pull_request:
    branches: [main]
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
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    permissions:
      contents: read
      pull-requests: write

    steps:
      - uses: actions/checkout@v4

      - name: Login Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.0"
          terraform_wrapper: false

      - name: Terraform Init
        working-directory: ${{ env.TF_WORKING_DIR }}
        run: terraform init -reconfigure

      - name: Terraform Validate
        id: validate
        working-directory: ${{ env.TF_WORKING_DIR }}
        run: terraform validate -no-color

      - name: Terraform Plan
        id: plan
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
        uses: actions/github-script@v7
        if: always()
        with:
          script: |
            const fs = require('fs');
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
            ].join('\\n');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body
            });

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

      - name: Login Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
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
"""


def get_standard_pipeline() -> str:
    return STANDARD_PIPELINE
