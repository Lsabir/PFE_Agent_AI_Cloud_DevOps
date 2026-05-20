# ── Script PowerShell pour lancer l'Agent en mode AUTONOME ────────────────────
# Ce script configure l'environnement pour une exécution 100% automatique
# L'agent validera automatiquement les plans et mergera les PRs

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  🤖 AGENT IA DEVOPS — MODE AUTONOME COMPLET" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  ✓ AGENT_CI_MODE = true (mode CI activé)" -ForegroundColor Green
Write-Host "  ✓ AGENT_SKIP_VALIDATION = true (validation automatique)" -ForegroundColor Green
Write-Host "  ✓ AGENT_AUTO_VALIDATE_PLAN = true (plan validé automatiquement)" -ForegroundColor Green
Write-Host ""
Write-Host "Comportement attendu:" -ForegroundColor Yellow
Write-Host "  1. L'agent récupère un ticket Jira en 'To Do'" -ForegroundColor Cyan
Write-Host "  2. Analyse la description et génère le code Terraform" -ForegroundColor Cyan
Write-Host "  3. Crée une Pull Request sur GitHub" -ForegroundColor Cyan
Write-Host "  4. Attend la fin du pipeline (plan validation)" -ForegroundColor Cyan
Write-Host "  5. Valide automatiquement et merge la PR" -ForegroundColor Cyan
Write-Host "  6. Déclenche le terraform apply automatiquement" -ForegroundColor Cyan
Write-Host "  7. Clôt le ticket Jira en 'Done'" -ForegroundColor Cyan
Write-Host ""

# Activer l'environnement virtuel Python
$venvPath = ".\.venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    Write-Host "Activation de l'environnement virtuel..." -ForegroundColor Yellow
    & $venvPath
    Write-Host "✅ Environnement virtuel activé" -ForegroundColor Green
} else {
    Write-Host "⚠️  Environnement virtuel non trouvé!" -ForegroundColor Red
}

# Variables d'environnement pour le mode autonome
$env:AGENT_CI_MODE = "true"
$env:AGENT_SKIP_VALIDATION = "true"
$env:AGENT_AUTO_VALIDATE_PLAN = "true"

Write-Host ""
Write-Host "Lancement de l'agent autonome..." -ForegroundColor Yellow
Write-Host "═" * 60 -ForegroundColor Cyan
Write-Host ""

# Lancer l'agent
python run_agent.py

Write-Host ""
Write-Host "═" * 60 -ForegroundColor Cyan
Write-Host "✅ Exécution terminée" -ForegroundColor Green
