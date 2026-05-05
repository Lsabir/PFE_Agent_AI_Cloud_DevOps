# Guide — Tester l'agent dans votre infrastructure Azure via Private Link

## Objectif

Vérifier que l'agent Python (exécuté sur la VM agent du subnet 1) peut accéder à Azure OpenAI via un Private Link situé dans le subnet 2.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│               Azure Virtual Network                     │
│               10.0.0.0/16                               │
├─────────────────────────┬───────────────────────────────┤
│                         │                               │
│  Subnet 1 (Agent)       │  Subnet 2 (Private Endpoints)│
│  10.0.1.0/24            │  10.0.2.0/24                 │
│                         │                               │
│  ┌──────────────────┐   │  ┌──────────────────────┐    │
│  │   VM Agent       │   │  │ Private Endpoint     │    │
│  │ (run_agent.py)   │   │  │ Azure OpenAI         │    │
│  └──────────────────┘   │  └──────────────────────┘    │
│         │               │           │                   │
│         └───────────────┼───────────┘                   │
│                         │ (Private Link)                │
│                         │                               │
│  ┌─────────────────────────────────────────┐            │
│  │  Zone DNS privée : privatelink.openai   │            │
│  │  *.openai.azure.com → Private IP        │            │
│  └─────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────┘
```

---

## Prérequis

- Terraform déployé avec `create_openai = true`
- VM agent créée et accessible via SSH
- Zone DNS privée pour `privatelink.openai.azure.com`
- Private Endpoint pour Azure OpenAI créé

---

## Étapes de test

### 1. Déployer l'infrastructure

```powershell
# Windows
.\deploy.ps1

# Linux/Mac
bash deploy.sh
```

Vérifiez que :
- Resource Group créé
- VNet avec 2 subnets créé
- VM agent créée
- Azure OpenAI créé (si `create_openai = true`)
- Private Endpoint créé pour OpenAI
- Zones DNS privées créées

### 2. Se connecter à la VM

```powershell
cd terraform
$VM_IP = terraform output -raw vm_public_ip

ssh -i ~/.ssh/id_rsa azureuser@$VM_IP
```

### 3. Configurer l'agent sur la VM

```bash
cd ~/agent-repo

# Copier le fichier .env example
cp .env.example .env

# Éditer avec vos vraies valeurs
nano .env
```

Remplissez :
```dotenv
AZURE_OPENAI_ENDPOINT=https://agent-devops-openai.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
GITHUB_TOKEN=github_pat_...
GITHUB_OWNER=your-username
GITHUB_INFRA_REPO=infra-provisioned
JIRA_URL=https://your-jira.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-jira-token
JIRA_PROJECT_KEY=PM
```

Sauvegardez (Ctrl+X, Y, Entrée).

### 4. Tester la connectivité au Private Link

```bash
# Activer l'environnement virtuel
source .venv/bin/activate

# Exécuter le script de test
bash test_private_endpoint.sh
```

Ou sur Windows PowerShell :
```powershell
.\test_private_endpoint.ps1
```

Le script vérifie :
- ✅ Python et dépendances
- ✅ Résolution DNS du Private Endpoint
- ✅ IP privée détectée (10.0.x.x)
- ✅ Connectivité HTTPS vers OpenAI
- ✅ Création du client Azure OpenAI

### 5. Lancer l'agent

```bash
source .venv/bin/activate
python run_agent.py
```

### 6. Suivre l'exécution

L'agent vous demandera :

1. **Choisir un ticket Jira** : Créez d'abord un ticket en `To Do` dans Jira
2. **Confirmer la description** : tapez `oui`
3. **Confirmer l'analyse** : tapez `oui`
4. **Approuver le déploiement** : tapez `oui` pour un vrai test

### 7. Vérifier le résultat sur GitHub

1. Allez sur votre repo `infra-provisioned`
2. Vérifiez que la PR est créée
3. Vérifiez que le plan Terraform s'exécute dans les checks
4. Après merge, vérifiez que `terraform apply` se déclenche

### 8. Vérifier que tout fonctionne

```powershell
# Depuis votre machine locale
cd terraform

# Afficher les outputs
terraform output

# Vérifier les ressources Azure créées
az resource list --resource-group "agent-devops-rg" --query "[].type"
```

---

## 🔍 Dépannage

### "Résolution DNS échouée"

La zone DNS privée n'est pas bien liée au VNet.

**Solution :**
```powershell
# Vérifier la liaison DNS
az network private-dns zone virtual-network-link list \
  --zone-name privatelink.openai.azure.com \
  --resource-group agent-devops-rg
```

### "IP publique détectée"

L'accès public à Azure OpenAI n'a pas été désactivé.

**Solution :**
```powershell
# Vérifier la configuration OpenAI
az cognitiveservices account show \
  --name agent-devops-openai \
  --resource-group agent-devops-rg \
  --query publicNetworkAccessEnabled
```

Devrait afficher `false`. Si c'est `true`, modifier Terraform :
```terraform
public_network_access_enabled = false
```

### "Configuration incomplète"

Le `.env` sur la VM n'a pas toutes les variables.

**Solution :**
```bash
cat .env
# Vérifier que toutes les lignes sont remplies
# Relancer l'agent
```

### "Quota OpenAI non disponible"

Azure OpenAI a besoin d'une approbation de quota.

**Solution :**
- Créer manuellement Azure OpenAI dans le portail Azure
- OU définir `create_openai = false` dans Terraform
- ET configurer `AZURE_OPENAI_ENDPOINT` et `AZURE_OPENAI_API_KEY` dans `.env`

---

## ✅ Signes que tout fonctionne correctement

- ✅ DNS privé résout le hostname vers une IP 10.0.x.x
- ✅ Connexion HTTPS réussie (HTTP 401/403)
- ✅ Client OpenAI créé sans erreur
- ✅ Agent lancé sur la VM sans erreur "Configuration incomplète"
- ✅ PR créée sur GitHub avec plan Terraform
- ✅ Ticket Jira mis à jour et marqué `Done`
- ✅ Nouvelles ressources Azure créées via `terraform apply`

---

## 📝 Notes importantes

- L'agent **ne fonctionne QUE sur la VM Azure**, pas en local
- Azure OpenAI doit avoir `public_network_access_enabled = false` pour vraiment tester le Private Link
- La zone DNS privée doit résoudre `*.openai.azure.com` vers le Private Endpoint
- Tous les tests doivent passer avant de lancer l'agent réel

