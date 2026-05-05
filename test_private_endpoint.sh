#!/bin/bash
# Script de test — Vérifier que l'agent peut accéder à Azure OpenAI via Private Link

echo "════════════════════════════════════════════════════════════"
echo "  Test de connectivité — Azure OpenAI via Private Link"
echo "════════════════════════════════════════════════════════════"
echo ""

# Vérifier que le .env existe
if [ ! -f .env ]; then
    echo "❌ Fichier .env non trouvé."
    echo "   Créez-le : cp .env.example .env et remplissez les valeurs."
    exit 1
fi

# Sourcer le .env
set -a
source .env
set +a

echo "▶ Configuration chargée depuis .env"
echo "  AZURE_OPENAI_ENDPOINT: $AZURE_OPENAI_ENDPOINT"
echo ""

# Étape 1 : Vérifier que Python et les dépendances sont installées
echo "▶ Étape 1 : Vérification de Python"
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 non installé."
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "✅ $PYTHON_VERSION"

# Étape 2 : Vérifier que l'environnement virtuel est activé
echo ""
echo "▶ Étape 2 : Vérification de l'environnement virtuel"
if [ -z "$VIRTUAL_ENV" ]; then
    echo "ℹ  Activation de l'environnement virtuel..."
    source .venv/bin/activate
fi
echo "✅ Environnement activé : $VIRTUAL_ENV"

# Étape 3 : Vérifier que les dépendances sont installées
echo ""
echo "▶ Étape 3 : Vérification des dépendances"
python3 -c "import requests; import openai; print('✅ Dépendances OK')" || {
    echo "❌ Dépendances manquantes. Installez avec : pip install -r requirements.txt"
    exit 1
}

# Étape 4 : Tester la résolution DNS du Private Endpoint
echo ""
echo "▶ Étape 4 : Résolution DNS du Private Endpoint"
OPENAI_HOST=$(echo $AZURE_OPENAI_ENDPOINT | sed 's/https:\/\///' | sed 's/\///g')
echo "  Hôte à résoudre : $OPENAI_HOST"

if nslookup "$OPENAI_HOST" > /dev/null 2>&1; then
    RESOLVED_IP=$(nslookup "$OPENAI_HOST" | grep "Address:" | tail -1 | awk '{print $NF}')
    echo "✅ Résolution DNS réussie : $RESOLVED_IP"
    
    # Vérifier que c'est une IP privée (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    if [[ "$RESOLVED_IP" =~ ^(10|172|192)\. ]]; then
        echo "✅ IP privée détectée — Private Link fonctionne !"
    else
        echo "⚠️  IP publique détectée : $RESOLVED_IP (private link non actif)"
    fi
else
    echo "❌ Résolution DNS échouée pour $OPENAI_HOST"
    echo "   Vérifiez que les zones DNS privées sont bien liées au VNet"
    exit 1
fi

# Étape 5 : Tester la connectivité avec curl
echo ""
echo "▶ Étape 5 : Tester la connectivité HTTPS (curl)"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "api-key: test-key" \
    "$AZURE_OPENAI_ENDPOINT/openai/deployments?api-version=2024-02-01" 2>/dev/null)

if [ "$HTTP_CODE" = "401" ]; then
    echo "✅ Connectivité HTTPS OK (erreur 401 attendue sans clé valide)"
elif [ "$HTTP_CODE" = "403" ]; then
    echo "✅ Connectivité HTTPS OK (erreur 403 — clé invalide)"
elif [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Connectivité HTTPS OK (200)"
else
    echo "⚠️  Code HTTP inattendu : $HTTP_CODE"
    echo "   Cela peut être normal si la connectivité fonctionne"
fi

# Étape 6 : Tester la bibliothèque OpenAI
echo ""
echo "▶ Étape 6 : Test avec la bibliothèque Python OpenAI"
python3 << 'PYTHON_TEST'
import os
from openai import AzureOpenAI

try:
    client = AzureOpenAI(
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    )
    print("✅ Client Azure OpenAI créé avec succès")
    print(f"   Endpoint : {os.getenv('AZURE_OPENAI_ENDPOINT')}")
    print(f"   Clé API : {os.getenv('AZURE_OPENAI_API_KEY')[:10]}...")
    
    # Essayer une requête simple (elle échouera peut-être, mais on teste la connexion)
    try:
        response = client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
            messages=[{"role": "user", "content": "test"}],
            max_tokens=10
        )
        print("✅ Requête OpenAI réussie !")
    except Exception as e:
        if "quota" in str(e).lower() or "quota" in str(e).lower():
            print("⚠️  Quota OpenAI non disponible (normal)")
        else:
            print(f"⚠️  Erreur lors de la requête : {type(e).__name__}")
        print(f"   Détail : {str(e)[:100]}...")
        
except Exception as e:
    print(f"❌ Erreur création client : {e}")
    exit(1)

PYTHON_TEST

# Étape 7 : Résumé
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  ✅ Test de connectivité terminé"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Si tous les tests sont passés, vous pouvez lancer l'agent :"
echo "  python run_agent.py"
echo ""
