# 🚀 Guide — Exécuter l'agent depuis votre machine locale

## Prérequis

- Python 3.12+ installé (vous avez Python 3.14.3)
- Fichier `.env` configuré avec vos vraies valeurs
- Accès internet pour les APIs (Jira, GitHub, Azure OpenAI)

---

## Étapes d'exécution

### 1. Préparer l'environnement

```powershell
# Créer l'environnement virtuel (si pas déjà fait)
py -m venv .venv

# Activer l'environnement virtuel
.venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt
```

### 2. Vérifier la configuration

```powershell
# Vérifier que .env est bien configuré
type .env
```

Votre `.env` contient déjà :
- ✅ JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY
- ✅ AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT
- ✅ GITHUB_TOKEN, GITHUB_OWNER, GITHUB_INFRA_REPO
- ✅ USE_KEYVAULT=false (optionnel)

### 3. Créer un ticket Jira de test

1. Allez sur https://abdessamad1sabir.atlassian.net
2. Créez un nouveau ticket dans le projet `PM`
3. Statut : `To Do`
4. Description : "Déployer un VNet avec 2 subnets, un Key Vault et un compte de stockage"

### 4. Lancer l'agent

```powershell
# Activer l'environnement virtuel
.venv\Scripts\activate

# Lancer l'agent
python run_agent.py
```

### 5. Suivre l'exécution

L'agent va :

1. **Scanner Jira** : Chercher les tickets `To Do`
2. **Vous demander confirmation** : Tapez `oui` pour continuer
3. **Analyser avec Azure OpenAI** : Générer le plan Terraform
4. **Créer une PR sur GitHub** : Dans le repo `infra-provisioned`
5. **Attendre l'approbation** : Tapez `oui` pour merger la PR
6. **Déclencher GitHub Actions** : `terraform apply` sur la branche main

---

## 🔍 Que vérifier pendant l'exécution

### Console de l'agent

```
Agent DevOps AI - Infrastructure as Code
═════════════════════════════════════════

Tickets Jira trouvés :
1. PM-1 : Déployer un VNet avec 2 subnets...

Choisir un ticket (numéro) : 1
Confirmer la description ? (oui/non) : oui
Analyser avec Azure OpenAI... ✅
Plan Terraform généré ✅
Créer PR sur GitHub... ✅
PR #42 créée : https://github.com/Lsabir/infra-provisioned/pull/42
Attendre le plan Terraform... ✅
Plan réussi ! Voulez-vous merger ? (oui/non) : oui
Merge en cours... ✅
Attendre terraform apply... ✅
Infrastructure déployée ! 🎉
```

### Sur GitHub

1. Repo `infra-provisioned` → Pull Requests
2. Vérifier que la PR est créée avec les fichiers Terraform
3. Vérifier les checks : `terraform plan` réussi
4. Après merge : `terraform apply` réussi

### Sur Jira

- Le ticket passe automatiquement à `Done`
- Commentaires ajoutés avec les détails

---

## 🛠️ Dépannage

### "Configuration incomplète"

**Cause** : Variable manquante dans `.env`

**Solution** :
```powershell
# Vérifier toutes les variables
type .env | findstr /v "^#" | findstr /v "^$"
```

Variables requises :
- JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY
- AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT
- GITHUB_TOKEN, GITHUB_OWNER, GITHUB_INFRA_REPO

### "Aucun ticket trouvé"

**Cause** : Pas de ticket en statut `To Do`

**Solution** :
- Créez un ticket Jira avec statut `To Do`
- OU modifiez le code pour chercher d'autres statuts

### "Erreur API GitHub"

**Cause** : Token GitHub invalide ou permissions insuffisantes

**Solution** :
- Vérifiez GITHUB_TOKEN dans `.env`
- Le token doit avoir permissions `repo` et `workflow`

### "Erreur Azure OpenAI"

**Cause** : Endpoint ou clé API invalide

**Solution** :
- Vérifiez AZURE_OPENAI_ENDPOINT et AZURE_OPENAI_API_KEY
- Testez avec un curl :
```powershell
curl -H "api-key: $AZURE_OPENAI_API_KEY" $AZURE_OPENAI_ENDPOINT/openai/deployments/gpt-4o/chat/completions?api-version=2024-02-15-preview -d '{"messages":[{"role":"user","content":"Hello"}]}' -H "Content-Type: application/json"
```

---

## 📝 Notes importantes

- **Test local = validation du code** : L'agent fonctionne mais déploie sur GitHub (pas localement)
- **Pour tester l'infra complète** : Utilisez `TEST_PRIVATE_LINK.md` après déploiement Azure
- **Premier test** : Commencez par un ticket simple pour valider le workflow
- **Nettoyage** : Supprimez les PRs de test après validation

---

## ✅ Signes de succès

- ✅ Agent se lance sans erreur "Configuration incomplète"
- ✅ Ticket Jira trouvé et affiché
- ✅ Analyse Azure OpenAI réussie (pas d'erreur API)
- ✅ PR créée sur GitHub avec fichiers Terraform valides
- ✅ GitHub Actions exécute `terraform plan` sans erreur
- ✅ Après merge, `terraform apply` déploie les ressources

