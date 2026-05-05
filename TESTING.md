# Guide de test complet — Agent IA DevOps

Ce guide explique comment tester que l'agent fonctionne dans votre infrastructure Azure (et pas seulement en local).

---

## 📋 Prérequis

- Azure CLI installé et connecté : `az login`
- Terraform installé (>= 1.5)
- Git installé
- Clé SSH privée configurée pour la VM
- Ticket Jira en `To Do` dans votre projet
- Secrets GitHub configurés : `AZURE_CREDENTIALS`, `SSH_PUBLIC_KEY`

---

## Phase 1 — Déployer l'infrastructure Terraform

### 1.1 Sélectionner la bonne subscription Azure

```powershell
az account show
az account set --subscription "<AZURE_SUBSCRIPTION_ID>"
az account show
```

### 1.2 Initialiser et tester Terraform

```powershell
cd terraform
terraform init
terraform validate
terraform fmt -check -recursive
```

### 1.3 Créer le fichier de variables

```powershell
cp terraform.tfvars.example terraform.tfvars
# Éditer terraform/terraform.tfvars avec vos valeurs réelles :
# - location: région Azure (ex: swedencentral)
# - ssh_public_key: contenu de votre clé publique SSH (~/.ssh/id_rsa.pub)
# - admin_ip_cidr: votre IP pour SSH (ex: 203.0.113.0/32)
# - create_openai: true si vous avez le quota, sinon false
```

### 1.4 Exécuter le plan

```powershell
terraform plan -out=tfplan
```

Vérifier que le plan crée :
- ✅ Resource Group
- ✅ Virtual Network + subnets
- ✅ VM Agent
- ✅ Key Vault + Private Endpoint
- ✅ Zones DNS privées

### 1.5 Appliquer le plan

```powershell
terraform apply tfplan
```

Attendre 5-10 minutes que tout soit créé.

### 1.6 Récupérer les outputs

```powershell
terraform output
```

Vous devez voir :
- `resource_group_name`
- `vm_agent_id`
- `vm_public_ip` (adresse IP publique de la VM)
- `ssh_command` (commande SSH prête à utiliser)

Sauvegardez l'IP publique pour plus tard.

---

## Phase 2 — Se connecter à la VM et configurer l'agent

### 2.1 SSH sur la VM

```powershell
ssh -i ~/.ssh/id_rsa azureuser@<PUBLIC_IP>
```

Remplacez `<PUBLIC_IP>` par la valeur récupérée dans `terraform output`.

### 2.2 Vérifier que l'agent est bien installé

```bash
cd ~/agent-repo
ls -la
pwd
```

Vous devez voir :
- `run_agent.py`
- `agent/` (dossier)
- `requirements.txt`
- `.venv/` (environnement virtuel)

### 2.3 Vérifier le fichier `.env`

```bash
cat .env
```

Actuellement, seul `GITHUB_OWNER=Lsabir` est configuré. Vous devez ajouter :

```bash
# Copier l'exemple
cp .env.example .env

# Éditer .env avec vos vraies valeurs
nano .env
```

Insérez (remplacez les valeurs par les vôtres) :

```dotenv
AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o
GITHUB_TOKEN=github_pat_...
GITHUB_OWNER=your-github-username
GITHUB_INFRA_REPO=infra-provisioned
JIRA_URL=https://your-jira.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-jira-token
JIRA_PROJECT_KEY=PM
```

Sauvegardez (Ctrl+X, Y, Entrée si vous utilisez nano).

### 2.4 Activer l'environnement virtuel

```bash
source .venv/bin/activate
python --version
```

Vous devez voir `Python 3.11.x` ou similaire.

---

## Phase 3 — Tester l'agent dans la VM

### 3.1 Créer un ticket Jira en `To Do`

Dans Jira, créez un ticket avec :
- **Project** : PM (ou votre projet)
- **Status** : To Do
- **Summary** : `Test Agent IA — VNet avec 2 subnets et OpenAI`
- **Description** :
  ```
  Créer une infrastructure Azure avec :
  - Un Virtual Network 10.0.0.0/16
  - Subnet 1 (agent) : 10.0.1.0/24
  - Subnet 2 (private endpoints) : 10.0.2.0/24
  - Key Vault avec accès privé
  - Endpoint privé Azure OpenAI
  ```

Notez la clé du ticket (ex : PM-123).

### 3.2 Lancer l'agent sur la VM

```bash
cd ~/agent-repo
source .venv/bin/activate
python run_agent.py
```

### 3.3 Suivre l'exécution

L'agent demande :

1. **Choisir un ticket** : sélectionnez le numéro du ticket que vous venez de créer
2. **Confirmation de la description** : tapez `oui`
3. **Confirmation de l'analyse** : tapez `oui`
4. **Approbation du déploiement** : tapez `non` pour l'instant (test de la PR uniquement)

L'agent créera alors :
- une branche GitHub `feature/PM-123-...`
- des fichiers Terraform
- une Pull Request

---

## Phase 4 — Vérifier le résultat sur GitHub

### 4.1 Aller sur GitHub

1. Ouvrez votre repo `infra-provisioned`
2. Vérifiez que la PR est créée
3. Regardez les checks CI/CD (`terraform plan`, `terraform fmt`, etc.)

Attendez que les checks passent au vert (✅).

### 4.2 Examiner le fichier Terraform généré

1. Cliquez sur la PR
2. Allez dans **Files changed**
3. Vérifiez que le dossier du projet contient :
   - `providers.tf`
   - `variables.tf`
   - `main.tf`
   - `outputs.tf`
   - `terraform.tfvars.example`
   - `README.md`
   - `.github/workflows/terraform-...yml`

### 4.3 Vérifier le commentaire du plan

La PR doit avoir un commentaire montrant le résultat de `terraform plan`.

---

## Phase 5 — Merger et déclencher le `apply`

### 5.1 Approuver la PR manuellement

1. Cliquez sur **Approve** sur GitHub
2. Cliquez sur **Merge pull request**
3. Confirmez le merge

### 5.2 Attendre le `terraform apply`

1. Allez dans **Actions**
2. Attendez que le workflow `apply` se termine
3. Vérifiez que `terraform apply` a réussi

### 5.3 Vérifier sur Azure

```powershell
az resource list --resource-group "<RESOURCE_GROUP_NAME>" --query "[].type" --output table
```

Vous devez voir des ressources du projet créées (VM, réseau, etc.).

---

## Phase 6 — Vérifier que l'agent a bien fonctionné dans Azure

### 6.1 Vérifier le ticket Jira

1. Retournez sur Jira
2. Le ticket initial `PM-123` doit être passé en **Done**
3. Des commentaires doivent montrer l'exécution

### 6.2 Vérifier les logs de l'agent sur la VM

Si vous êtes toujours connecté à la VM :

```bash
history
# Vous verrez les commandes exécutées par l'agent
```

Si vous avez fermé la connexion, reconnectez-vous :

```powershell
ssh -i ~/.ssh/id_rsa azureuser@<PUBLIC_IP>
```

---

## Phase 7 — Arrêter et nettoyer

### 7.1 Supprimer l'infrastructure Terraform

Si vous voulez arrêter de payer pour les ressources Azure :

```powershell
cd terraform
terraform destroy
```

Confirmez avec `yes`.

### 7.2 Vérifier sur Azure Portal

```powershell
az resource list --resource-group "<RESOURCE_GROUP_NAME>"
```

La liste doit être vide ou quasi vide.

---

## ✅ Signes que tout fonctionne correctement

- ✅ Terraform déploie la VM sans erreur
- ✅ SSH sur la VM fonctionne
- ✅ L'agent Python se lance sans erreur dans la VM
- ✅ Une PR est créée sur GitHub
- ✅ Le plan Terraform s'exécute dans GitHub Actions
- ✅ Après merge, `terraform apply` s'exécute
- ✅ Le ticket Jira passe en `Done`
- ✅ Des ressources Azure sont créées via GitHub Actions

---

## ❌ Dépannage

### L'agent ne trouve pas de tickets Jira

- Vérifiez que `JIRA_API_TOKEN` est valide
- Vérifiez que le ticket est bien en `To Do`
- Vérifiez que `JIRA_PROJECT_KEY` est correct

### SSH échoue

- Vérifiez que `admin_ip_cidr` dans `terraform.tfvars` inclut votre IP
- Vérifiez que la clé SSH privée correspond à la clé publique utilisée
- Attendez 2-3 minutes après `terraform apply`

### Terraform plan échoue dans GitHub Actions

- Vérifiez le secret `AZURE_CREDENTIALS` dans GitHub
- Vérifiez que le service principal a le rôle `Contributor`
- Vérifiez que la clé SSH publique est bien passée en secret `SSH_PUBLIC_KEY`

### L'agent dit "Configuration incomplète"

- Vérifiez le `.env` sur la VM
- Vérifiez que toutes les valeurs sont présentes (pas de lignes vides)
- Source à nouveau : `source .venv/bin/activate`

---

## Notes finales

- **Agent local** : test avec `python run_agent.py` sur votre machine
- **Agent en infra** : test avec `python run_agent.py` sur la VM Azure créée par Terraform
- Pour tester vraiment en infra, vous devez deployer Terraform d'abord
- Le déploiement réel de nouvelles infras se fait via GitHub Actions, pas en local
