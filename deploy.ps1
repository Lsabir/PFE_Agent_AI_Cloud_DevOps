# Script de déploiement rapide de l'infra Terraform (Windows PowerShell)

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Agent IA DevOps — Script de déploiement Terraform" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan

# Étape 1 : Vérifier Azure CLI
Write-Host ""
Write-Host "▶ Étape 1 : Vérification d'Azure CLI"
if (-Not (Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Azure CLI non installé." -ForegroundColor Red
    Write-Host "   Installez-le depuis https://docs.microsoft.com/cli/azure/install-azure-cli"
    exit 1
}
Write-Host "✅ Azure CLI trouvé" -ForegroundColor Green

# Étape 2 : Connexion Azure
Write-Host ""
Write-Host "▶ Étape 2 : Vérification de la connexion Azure"
$account = az account show --query name -o tsv -ErrorAction SilentlyContinue
if (-Not $account) {
    Write-Host "ℹ Vous n'êtes pas connecté. Exécution de 'az login'..."
    az login
    $account = az account show --query name -o tsv
}
Write-Host "✅ Connecté à : $account" -ForegroundColor Green

# Étape 3 : Vérifier Terraform
Write-Host ""
Write-Host "▶ Étape 3 : Vérification de Terraform"
if (-Not (Get-Command terraform -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Terraform non installé." -ForegroundColor Red
    Write-Host "   Installez-le depuis https://www.terraform.io/downloads"
    exit 1
}
$tfVersion = terraform -version | Select-Object -First 1
Write-Host "✅ $tfVersion" -ForegroundColor Green

# Étape 4 : Aller dans le dossier terraform
Write-Host ""
Write-Host "▶ Étape 4 : Initialisation de Terraform"
Push-Location terraform
terraform init
Write-Host "✅ Terraform initialisé" -ForegroundColor Green

# Étape 5 : Valider la configuration
Write-Host ""
Write-Host "▶ Étape 5 : Validation de la configuration"
terraform validate
Write-Host "✅ Configuration valide" -ForegroundColor Green

# Étape 6 : Vérifier le format
Write-Host ""
Write-Host "▶ Étape 6 : Vérification du format Terraform"
$fmtCheck = terraform fmt -check -recursive
if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Format valide" -ForegroundColor Green
} else {
    Write-Host "⚠️  Reformatage nécessaire. Exécutez : terraform fmt -recursive" -ForegroundColor Yellow
}

# Étape 7 : Créer le plan
Write-Host ""
Write-Host "▶ Étape 7 : Création du plan Terraform"
Write-Host "   (Cela peut prendre 1-2 minutes...)" -ForegroundColor Gray
terraform plan -out=tfplan
Write-Host "✅ Plan créé" -ForegroundColor Green

# Étape 8 : Demander confirmation
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Plan Terraform prêt à être appliqué." -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
$response = Read-Host "Voulez-vous appliquer ce plan maintenant ? (oui/non)"

if ($response -eq "oui" -or $response -eq "yes" -or $response -eq "y") {
    Write-Host ""
    Write-Host "▶ Étape 8 : Application du plan (cela peut prendre 10-15 minutes...)" -ForegroundColor Yellow
    terraform apply tfplan
    
    Write-Host ""
    Write-Host "✅ Infrastructure déployée avec succès !" -ForegroundColor Green
    Write-Host ""
    Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  Outputs Terraform :" -ForegroundColor Cyan
    Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
    terraform output
    
    Write-Host ""
    Write-Host "Prochaines étapes :" -ForegroundColor Yellow
    Write-Host "  1. Récupérez l'IP publique de la VM ci-dessus (vm_public_ip)" -ForegroundColor Gray
    Write-Host "  2. Connectez-vous : ssh -i ~/.ssh/id_rsa azureuser@<PUBLIC_IP>" -ForegroundColor Gray
    Write-Host "  3. Configurez le .env sur la VM avec vos secrets" -ForegroundColor Gray
    Write-Host "  4. Lancez l'agent : python run_agent.py" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host "❌ Plan non appliqué." -ForegroundColor Yellow
    Write-Host "   Vous pouvez l'appliquer plus tard avec :" -ForegroundColor Gray
    Write-Host "   cd terraform; terraform apply tfplan" -ForegroundColor Gray
}

Pop-Location
