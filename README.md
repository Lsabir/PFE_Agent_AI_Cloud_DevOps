# Infra Agent IA Azure

Ce dépôt contient l'infrastructure Terraform pour déployer un Agent IA DevOps autonome sur Azure.

## Structure du projet

- `terraform/` : configuration principale
- `terraform/modules/` : modules modulaires pour réseau, VM, Key Vault, OpenAI
- `.github/workflows/terraform.yml` : workflow GitHub Actions pour OIDC et exécution Terraform

## Prérequis

- Azure CLI installé
- Terraform >= 1.5
- Accès à une subscription Azure valide
- Clé SSH publique pour l'accès SSH à la VM
- Compte GitHub avec repository et GitHub Actions activés

## 1. Connexion à Azure

```powershell
az login
az account set --subscription "<AZURE_SUBSCRIPTION_ID>"
```

## 2. Commencer avec un backend local (recommandé pour débuter)

Pour commencer simplement, nous utilisons un backend local. Le fichier `terraform.tfstate` sera stocké localement.

### Déploiement initial avec backend local

```powershell
cd terraform
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply -auto-approve tfplan
```


## 3. Modifier les variables si besoin

Variables importantes dans `terraform/variables.tf` :

- `location`
- `resource_group_name`
- `naming_prefix`
- `admin_ip_cidr`
- `ssh_public_key`
- `vm_size`
- `github_actions_principal_id`

Un exemple de fichier de variables est disponible dans `terraform/terraform.tfvars.example`.
Copiez-le en `terraform/terraform.tfvars` et adaptez les valeurs à votre environnement.

Vous pouvez aussi passer des variables en CLI :

```powershell
terraform plan -var="ssh_public_key=$(Get-Content ~/.ssh/id_rsa.pub -Raw)" \
  -var="admin_ip_cidr=203.0.113.0/32"
```

## 4. Déploiement local

Pour un usage simple en local, utilisez l’exemple de variables et vérifiez toujours le format avant le plan.

```powershell
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Éditer terraform/terraform.tfvars avec vos valeurs
terraform fmt -check -recursive
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply -auto-approve tfplan
```

> Pour une équipe, utilisez un backend distant Azure Storage et évitez de stocker l’état localement.
> Configurez le backend lors de `terraform init` avec `-backend-config` si nécessaire.

## 5. Configurer GitHub Actions avec OIDC

### 5.1 Créer une application Azure AD et lier GitHub OIDC

1. Créez une application Azure AD (App Registration)
2. Dans la section **Federated credentials**, ajoutez GitHub Actions :
   - Audience : `api://AzureADTokenExchange`
   - Subject : `repo:<ORG>/<REPO>:ref:refs/heads/main`

### 5.2 Donner les droits RBAC

Attribuez au principal Azure AD (service principal) le rôle `Contributor` sur :

- le Resource Group cible, ou
- la subscription si nécessaire

### 5.3 Ajouter les secrets GitHub

Dans le repository GitHub, ajoutez les secrets suivants :

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

## 6. CI/CD GitHub Actions

Le workflow existe déjà dans `.github/workflows/terraform.yml`.

Il exécute :

- `actions/checkout@v4`
- `azure/login@v1` avec OIDC
- `hashicorp/setup-terraform@v2`
- `terraform init`
- `terraform fmt -check`
- `terraform validate`
- `terraform plan`
- `terraform apply` sur `main`


## 7. Déployer depuis GitHub

1. Poussez vos changements dans `main`
2. Le workflow démarrera automatiquement
3. Surveillez l'exécution dans l'onglet Actions

## 8. Vérifier l'infrastructure

Après déploiement :

```powershell
cd terraform
terraform output
```

## 9. Bonnes pratiques

- Ne mettez jamais de secrets réels dans les fichiers Terraform.
- Gérer les secrets Key Vault séparément après déploiement.
- Utiliser un `admin_ip_cidr` restreint.
- Conserver `ssh_public_key` sous forme de variable sécurisée.
