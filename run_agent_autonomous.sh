#!/bin/bash
# ── Script Bash pour lancer l'Agent en mode AUTONOME ────────────────────
# Ce script configure l'environnement pour une exécution 100% automatique
# L'agent validera automatiquement les plans et mergera les PRs

echo "════════════════════════════════════════════════════════════"
echo "  🤖 AGENT IA DEVOPS — MODE AUTONOME COMPLET"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Configuration:"
echo "  ✓ AGENT_CI_MODE = true (mode CI activé)"
echo "  ✓ AGENT_SKIP_VALIDATION = true (validation automatique)"
echo "  ✓ AGENT_AUTO_VALIDATE_PLAN = true (plan validé automatiquement)"
echo ""
echo "Comportement attendu:"
echo "  1. L'agent récupère un ticket Jira en 'To Do'"
echo "  2. Analyse la description et génère le code Terraform"
echo "  3. Crée une Pull Request sur GitHub"
echo "  4. Attend la fin du pipeline (plan validation)"
echo "  5. Valide automatiquement et merge la PR"
echo "  6. Déclenche le terraform apply automatiquement"
echo "  7. Clôt le ticket Jira en 'Done'"
echo ""

# Activer l'environnement virtuel Python
VENV_PATH=".venv/bin/activate"
if [ -f "$VENV_PATH" ]; then
    echo "Activation de l'environnement virtuel..."
    source "$VENV_PATH"
    echo "✅ Environnement virtuel activé"
else
    echo "⚠️  Environnement virtuel non trouvé!"
    exit 1
fi

# Variables d'environnement pour le mode autonome
export AGENT_CI_MODE="true"
export AGENT_SKIP_VALIDATION="true"
export AGENT_AUTO_VALIDATE_PLAN="true"

echo ""
echo "Lancement de l'agent autonome..."
echo "════════════════════════════════════════════════════════════"
echo ""

# Lancer l'agent
python run_agent.py

echo ""
echo "════════════════════════════════════════════════════════════"
echo "✅ Exécution terminée"
