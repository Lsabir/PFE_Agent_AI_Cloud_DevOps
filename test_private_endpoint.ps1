# Script de test — Vérifier que l'agent peut accéder à Azure OpenAI via Private Link
# À exécuter sur la VM Azure depuis le répertoire agent-repo

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Test de connectivité — Azure OpenAI via Private Link" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Vérifier que le .env existe
if (-Not (Test-Path .env)) {
    Write-Host "❌ Fichier .env non trouvé." -ForegroundColor Red
    Write-Host "   Créez-le : cp .env.example .env et remplissez les valeurs." -ForegroundColor Gray
    exit 1
}

# Charger le .env
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2])
    }
}

$AZURE_OPENAI_ENDPOINT = [Environment]::GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
$AZURE_OPENAI_API_KEY = [Environment]::GetEnvironmentVariable("AZURE_OPENAI_API_KEY")

Write-Host "▶ Configuration chargée depuis .env" -ForegroundColor Yellow
Write-Host "  AZURE_OPENAI_ENDPOINT: $AZURE_OPENAI_ENDPOINT" -ForegroundColor Gray
Write-Host ""

# Étape 1 : Vérifier Python
Write-Host "▶ Étape 1 : Vérification de Python" -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($pythonVersion -match "Python") {
    Write-Host "✅ $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "❌ Python non trouvé" -ForegroundColor Red
    exit 1
}

# Étape 2 : Activer l'environnement virtuel
Write-Host ""
Write-Host "▶ Étape 2 : Activation de l'environnement virtuel" -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1
Write-Host "✅ Environnement activé" -ForegroundColor Green

# Étape 3 : Vérifier les dépendances
Write-Host ""
Write-Host "▶ Étape 3 : Vérification des dépendances" -ForegroundColor Yellow
try {
    python -c "import requests; import openai" 2>&1 | Out-Null
    Write-Host "✅ Dépendances OK" -ForegroundColor Green
} catch {
    Write-Host "❌ Dépendances manquantes" -ForegroundColor Red
    Write-Host "   Installez avec : pip install -r requirements.txt" -ForegroundColor Gray
    exit 1
}

# Étape 4 : Résolution DNS
Write-Host ""
Write-Host "▶ Étape 4 : Résolution DNS du Private Endpoint" -ForegroundColor Yellow
$OPENAI_HOST = $AZURE_OPENAI_ENDPOINT -replace "https://", "" -replace "/", ""
Write-Host "  Hôte à résoudre : $OPENAI_HOST" -ForegroundColor Gray

try {
    $dnsResult = Resolve-DnsName $OPENAI_HOST -ErrorAction Stop
    $resolvedIP = $dnsResult.IPAddress
    Write-Host "✅ Résolution DNS réussie : $resolvedIP" -ForegroundColor Green
    
    if ($resolvedIP -match "^(10|172|192)\.") {
        Write-Host "✅ IP privée détectée — Private Link fonctionne !" -ForegroundColor Green
    } else {
        Write-Host "⚠️  IP publique détectée : $resolvedIP (private link non actif)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Résolution DNS échouée pour $OPENAI_HOST" -ForegroundColor Red
    Write-Host "   Vérifiez que les zones DNS privées sont bien liées au VNet" -ForegroundColor Gray
    exit 1
}

# Étape 5 : Test HTTPS avec curl
Write-Host ""
Write-Host "▶ Étape 5 : Tester la connectivité HTTPS" -ForegroundColor Yellow
$curlResult = curl -s -o $null -w "%{http_code}" -H "api-key: test-key" `
    "$AZURE_OPENAI_ENDPOINT/openai/deployments?api-version=2024-02-01" 2>&1

if ($curlResult -eq "401" -or $curlResult -eq "403" -or $curlResult -eq "200") {
    Write-Host "✅ Connectivité HTTPS OK (HTTP $curlResult)" -ForegroundColor Green
} else {
    Write-Host "⚠️  Code HTTP inattendu : $curlResult" -ForegroundColor Yellow
}

# Étape 6 : Test avec OpenAI Python
Write-Host ""
Write-Host "▶ Étape 6 : Test avec la bibliothèque Python OpenAI" -ForegroundColor Yellow
python << 'PYTHON_TEST'
import os
from openai import AzureOpenAI

try:
    client = AzureOpenAI(
        api_version="2024-02-01",
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    )
    print("✅ Client Azure OpenAI créé avec succès")
    print(f"   Endpoint : {os.getenv('AZURE_OPENAI_ENDPOINT')}")
    
except Exception as e:
    print(f"❌ Erreur création client : {e}")
    exit(1)

PYTHON_TEST

# Résumé
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ✅ Test de connectivité terminé" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Si tous les tests sont passés, vous pouvez lancer l'agent :" -ForegroundColor Yellow
Write-Host "  python run_agent.py" -ForegroundColor Gray
Write-Host ""
