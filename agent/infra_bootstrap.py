"""
infra_bootstrap.py — Fichiers de démarrage pour le repo GitHub infra-provisioned.
Poussés une seule fois quand le repo est vide ou sans dossier terraform/.
"""

# Version du bootstrap (incrémenter si la structure change)
BOOTSTRAP_VERSION = "1"

# Dossier racine Terraform dans infra-provisioned (aligné avec le pipeline CI)
TF_ROOT = "terraform"


def get_bootstrap_files() -> dict[str, str]:
    """Retourne {chemin_relatif: contenu} pour initialiser infra-provisioned."""
    return {
        f"{TF_ROOT}/backend.tf": _BACKEND_TF,
        f"{TF_ROOT}/providers.tf": _PROVIDERS_TF,
        f"{TF_ROOT}/variables.tf": _VARIABLES_TF,
        f"{TF_ROOT}/main.tf": _MAIN_TF,
        f"{TF_ROOT}/network.tf": _NETWORK_TF,
        f"{TF_ROOT}/outputs.tf": _OUTPUTS_TF,
        f"{TF_ROOT}/terraform.tfvars.example": _TFVARS_EXAMPLE,
        "README.md": _README,
    }


_BACKEND_TF = """\
terraform {
  backend "azurerm" {
    resource_group_name  = "tf-state-rg"
    storage_account_name = "tfstateagentdevops"
    container_name       = "tfstate"
    key                  = "infra-provisioned.tfstate"
  }
}
"""

_PROVIDERS_TF = """\
terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.90"
    }
  }
}

provider "azurerm" {
  features {}
}
"""

_VARIABLES_TF = """\
variable "location" {
  description = "Azure region."
  type        = string
  default     = "swedencentral"
}

variable "resource_group_name" {
  description = "Resource group name."
  type        = string
  default     = "infra-provisioned-rg"
}

variable "naming_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "infra-prov"
}

variable "environment" {
  description = "Environment tag."
  type        = string
  default     = "dev"
}

variable "common_tags" {
  description = "Tags applied to all resources."
  type        = map(string)
  default = {
    managed_by = "agent-ia-devops"
    repo       = "infra-provisioned"
  }
}

variable "ssh_public_key" {
  description = "SSH public key (required when creating Linux VMs)."
  type        = string
  default     = ""
  sensitive   = true
}
"""

_MAIN_TF = """\
# Projet de base — l'agent ajoute des fichiers .tf supplémentaires dans ce dossier.

resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location
  tags = merge(var.common_tags, {
    environment = var.environment
  })
}
"""

_NETWORK_TF = """\
# Réseau minimal pour VMs créées par l'agent (tickets Jira).

resource "azurerm_virtual_network" "vnet" {
  name                = "${var.naming_prefix}-vnet"
  address_space       = ["10.1.0.0/16"]
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.common_tags
}

resource "azurerm_subnet" "agent" {
  name                 = "${var.naming_prefix}-subnet"
  resource_group_name  = azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.vnet.name
  address_prefixes     = ["10.1.1.0/24"]
}

resource "azurerm_network_security_group" "agent" {
  name                = "${var.naming_prefix}-nsg"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tags                = var.common_tags

  security_rule {
    name                       = "SSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "agent" {
  subnet_id                 = azurerm_subnet.agent.id
  network_security_group_id = azurerm_network_security_group.agent.id
}
"""

_OUTPUTS_TF = """\
output "resource_group_name" {
  value = azurerm_resource_group.rg.name
}

output "resource_group_id" {
  value = azurerm_resource_group.rg.id
}

output "location" {
  value = azurerm_resource_group.rg.location
}
"""

_TFVARS_EXAMPLE = """\
location             = "swedencentral"
resource_group_name  = "infra-provisioned-rg"
naming_prefix        = "infra-prov"
environment          = "dev"
# ssh_public_key = "ssh-ed25519 AAAA... votre_cle.pub"
"""

_README = """\
# infra-provisioned

Dépôt d'infrastructure géré par l'**Agent IA DevOps**.

- Tous les fichiers Terraform sont dans `terraform/`.
- Le pipeline `.github/workflows/terraform-standard.yml` exécute **plan** (PR) puis **apply** (merge sur `main`).
- L'état Terraform est stocké dans Azure Storage : clé `infra-provisioned.tfstate`.

## Secrets GitHub requis

| Secret | Description |
|--------|-------------|
| `AZURE_CREDENTIALS` | JSON service principal Azure |
| `SSH_PUBLIC_KEY` | Clé SSH publique (si VM) |
| `GH_ACTIONS_PRINCIPAL_ID` | Object ID du SP GitHub Actions (optionnel) |
| `ADMIN_OBJECT_ID` | Object ID admin Key Vault (optionnel) |

## Test manuel

```bash
cd terraform
terraform init
terraform plan
```
"""
