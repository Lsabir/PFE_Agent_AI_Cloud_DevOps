#!/bin/bash
# Script de déploiement rapide de l'infra Terraform

set -e

echo "════════════════════════════════════════════════════════════"
echo "  Agent IA DevOps — Script de déploiement Terraform"
echo "════════════════════════════════════════════════════════════"

# Étape 1 : Vérifier Azure CLI
echo ""
echo "▶ Étape 1 : Vérification d'Azure CLI"
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI non installé. Installez-le depuis https://docs.microsoft.com/cli/azure/install-azure-cli"
    exit 1
fi
echo "✅ Azure CLI trouvé"

# Étape 2 : Connexion Azure
echo ""
echo "▶ Étape 2 : Connexion à Azure"
CURRENT_ACCOUNT=$(az account show --query name -o tsv 2>/dev/null || echo "")
if [ -z "$CURRENT_ACCOUNT" ]; then
    echo "ℹ Lancez 'az login' pour vous connecter"
    az login
fi
echo "✅ Connecté à : $CURRENT_ACCOUNT"

# Étape 3 : Vérifier Terraform
echo ""
echo "▶ Étape 3 : Vérification de Terraform"
if ! command -v terraform &> /dev/null; then
    echo "❌ Terraform non installé. Installez-le depuis https://www.terraform.io/downloads"
    exit 1
fi
TERRAFORM_VERSION=$(terraform -version | head -1)
echo "✅ $TERRAFORM_VERSION"

# Étape 4 : Aller dans le dossier terraform
echo ""
echo "▶ Étape 4 : Initialisation de Terraform"
cd terraform
terraform init
echo "✅ Terraform initialisé"

# Étape 5 : Valider la configuration
echo ""
echo "▶ Étape 5 : Validation de la configuration"
terraform validate
echo "✅ Configuration valide"

# Étape 6 : Vérifier le format
echo ""
echo "▶ Étape 6 : Vérification du format"
terraform fmt -check -recursive && echo "✅ Format valide" || echo "⚠ Reformatage nécessaire (terraform fmt -recursive)"

# Étape 7 : Créer le plan
echo ""
echo "▶ Étape 7 : Création du plan Terraform"
terraform plan -out=tfplan
echo "✅ Plan créé"

# Étape 8 : Demander confirmation
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Plan Terraform prêt à être appliqué."
echo "════════════════════════════════════════════════════════════"
echo ""
read -p "Voulez-vous appliquer ce plan maintenant ? (oui/non) : " response

if [ "$response" = "oui" ] || [ "$response" = "yes" ] || [ "$response" = "y" ]; then
    echo ""
    echo "▶ Étape 8 : Application du plan"
    terraform apply tfplan
    echo ""
    echo "✅ Infrastructure déployée avec succès !"
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  Outputs Terraform :"
    echo "════════════════════════════════════════════════════════════"
    terraform output
    echo ""
    echo "Prochaines étapes :"
    echo "  1. Récupérez l'IP publique de la VM ci-dessus (vm_public_ip)"
    echo "  2. Connectez-vous : ssh -i ~/.ssh/id_rsa azureuser@<PUBLIC_IP>"
    echo "  3. Configurez le .env sur la VM"
    echo "  4. Lancez l'agent : python run_agent.py"
    echo ""
else
    echo "Plan non appliqué. Vous pouvez l'appliquer plus tard avec :"
    echo "  cd terraform && terraform apply tfplan"
fi
