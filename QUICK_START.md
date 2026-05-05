# Guide d'exécution rapide du projet

## 🚀 Option 1 : Test local (sans Azure)

Si vous voulez juste tester que l'agent Python fonctionne **localement** sans déployer d'infrastructure.

### Étapes

1. **Se connecter à Jira et créer un ticket en `To Do`**
   - Allez sur votre Jira
   - Créez un ticket avec description de l'infra souhaitée
   - Mettez le statut à `To Do`

2. **Configurer le `.env`**
   ```powershell
   # Copier l'exemple
   cp .env.example .env
   
   # Éditer .env avec vos vraies valeurs
   # AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, GITHUB_TOKEN, JIRA_*, etc.
   notepad .env
   ```

3. **Installer les dépendances**
   ```powershell
   python -m pip install -r requirements.txt
   ```

4. **Lancer l'agent**
   ```powershell
   python run_agent.py
   ```

5. **Suivre les prompts**
   - Choisir un ticket Jira `To Do`
   - Confirmer la description
   - Confirmer l'analyse IA
   - Approuver le déploiement (tapez `non` pour test)

6. **Vérifier sur GitHub**
   - Une PR doit être créée sur `infra-provisioned`
   - Le `terraform plan` doit s'exécuter dans les checks

---

## 🏗️ Option 2 : Test complet dans Azure (infra + agent)

Si vous voulez tester que l'agent **fonctionne dans votre infrastructure Azure**.

### Étape 1 : Préparer les secrets GitHub

Allez dans votre repo GitHub `infra-provisioned` → Settings → Secrets and variables → Actions

Ajoutez les secrets :
- `AZURE_CREDENTIALS` : JSON avec `clientId`, `clientSecret`, `subscriptionId`, `tenantId`
- `SSH_PUBLIC_KEY` : contenu de `~/.ssh/id_rsa.pub`

### Étape 2 : Déployer l'infrastructure Terraform

**Windows :**
```powershell
.\deploy.ps1
```

**Linux/Mac :**
```bash
bash deploy.sh
```

Cela va :
- Vérifier Azure CLI
- Initialiser Terraform
- Valider la configuration
- Créer un plan
- Demander confirmation
- Déployer la VM agent sur Azure

Attendez 10-15 minutes que tout se crée.

### Étape 3 : Récupérer l'IP publique

Après le déploiement :
```powershell
cd terraform
terraform output
```

Copiez la valeur de `vm_public_ip`.

### Étape 4 : Se connecter à la VM

```powershell
ssh -i ~/.ssh/id_rsa azureuser@<PUBLIC_IP>
```

Remplacez `<PUBLIC_IP>` par la valeur obtenue ci-dessus.

### Étape 5 : Configurer l'agent sur la VM

```bash
cd ~/agent-repo
cp .env.example .env
nano .env
# Insérez vos vraies valeurs :
# AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, GITHUB_TOKEN, JIRA_*, etc.
# Sauvegardez : Ctrl+X, Y, Entrée
```

### Étape 6 : Activer l'environnement virtuel

```bash
source .venv/bin/activate
python --version
```

### Étape 7 : Créer un ticket Jira en `To Do`

Dans Jira, créez un ticket avec description de l'infra que vous voulez déployer.

### Étape 8 : Lancer l'agent sur la VM

```bash
python run_agent.py
```

### Étape 9 : Suivre les prompts

- Sélectionnez le numéro du ticket
- Confirmez la description
- Confirmez l'analyse IA
- Approuvez le déploiement (tapez `oui` pour un vrai déploiement)

### Étape 10 : Vérifier sur GitHub

1. Une PR est créée sur `infra-provisioned`
2. `terraform plan` s'exécute dans les checks (via GitHub Actions)
3. Après approbation humaine et merge sur `main`, `terraform apply` se déclenche automatiquement
4. Le ticket Jira passe en `Done`

---

## 📋 Checklist pour lancer le projet

### Configuration initiale

- [ ] `.env` ou `.env.example` rempli avec les bonnes valeurs
- [ ] Clé SSH configurée (`~/.ssh/id_rsa` et `id_rsa.pub`)
- [ ] Compte GitHub avec repo `infra-provisioned`
- [ ] Compte Jira avec un projet et des tickets
- [ ] Azure CLI connecté : `az login`
- [ ] Terraform installé : `terraform --version`

### Pour Option 1 (local)

- [ ] `python run_agent.py` s'exécute sans erreur
- [ ] Un ticket Jira `To Do` existe
- [ ] Une PR est créée sur GitHub

### Pour Option 2 (Azure infra)

- [ ] `./deploy.ps1` ou `bash deploy.sh` s'exécute
- [ ] `terraform apply` crée la VM
- [ ] SSH sur la VM fonctionne
- [ ] L'agent tourne sur la VM avec `python run_agent.py`
- [ ] Une nouvelle infra est déployée sur Azure

---

## 🆘 Problèmes courants

| Problème | Solution |
|----------|----------|
| `Configuration incomplète` | Vérifiez le `.env` — toutes les variables doivent être remplies |
| `Aucun ticket To Do trouvé` | Créez un ticket Jira en `To Do` d'abord |
| `SSH échoue` | Vérifiez `admin_ip_cidr` dans `terraform.tfvars` inclut votre IP |
| `terraform init` échoue | Lancez `az login` et sélectionnez la bonne subscription |
| `Erreur Azure OpenAI` | Vérifiez `AZURE_OPENAI_ENDPOINT` et `AZURE_OPENAI_API_KEY` |

---

## 💡 Conseil

Pour **vraiment tester** que le projet fonctionne :

1. **Testez d'abord en local** (Option 1) pour vérifier que le code Python marche
2. **Ensuite testez dans Azure** (Option 2) pour vérifier que l'infra fonctionne
