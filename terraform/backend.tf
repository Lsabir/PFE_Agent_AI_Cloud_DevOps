# Backend local pour conserver l'état Terraform en local.
# Pour un usage en équipe, privilégiez un backend distant avec Azure Storage.
# Exemple d'initialisation distante : terraform init -backend-config="storage_account_name=..." \
#   -backend-config="container_name=..." -backend-config="key=terraform.tfstate" \
#   -backend-config="resource_group_name=..." -backend-config="subscription_id=..."
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
