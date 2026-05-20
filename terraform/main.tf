data "azurerm_client_config" "current" {}

locals {
  tags = merge({
    project     = var.project
    environment = var.environment
    owner       = var.owner
  }, var.common_tags)


  agent_custom_data = <<-EOT
    #cloud-config
    package_update: true
    package_upgrade: true
    packages: [python3.11, python3.11-venv, python3-pip, git, curl, unzip]
    runcmd:
      - update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
      - cd /home/azureuser && git clone https://github.com/Lsabir/PFE_Agent_AI_Cloud_DevOps.git agent-repo
      - cd /home/azureuser/agent-repo && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
      - echo "GITHUB_OWNER=${var.github_owner != "" ? var.github_owner : "Lsabir"}" >> /home/azureuser/agent-repo/.env
      - echo "USE_KEYVAULT=true" >> /home/azureuser/agent-repo/.env
      - echo "AZURE_KEYVAULT_URL=${module.keyvault.key_vault_uri}" >> /home/azureuser/agent-repo/.env
      - chown -R azureuser:azureuser /home/azureuser/agent-repo
  EOT
}

resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.tags
}

module "network" {
  source              = "./modules/network"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  vnet_name           = "${var.naming_prefix}-vnet"
  address_space       = var.vnet_address_space
  agent_subnet_prefix = var.agent_subnet_prefix
  pe_subnet_prefix    = var.pe_subnet_prefix
  admin_ip_cidr       = var.admin_ip_cidr
  tags                = local.tags
}

resource "azurerm_private_dns_zone" "openai" {
  name                = "privatelink.openai.azure.com"
  resource_group_name = azurerm_resource_group.rg.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone" "vault" {
  name                = "privatelink.vaultcore.azure.net"
  resource_group_name = azurerm_resource_group.rg.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "openai" {
  name                  = "${var.naming_prefix}-openai-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.openai.name
  virtual_network_id    = module.network.vnet_id
  registration_enabled  = false
}

resource "azurerm_private_dns_zone_virtual_network_link" "vault" {
  name                  = "${var.naming_prefix}-vault-link"
  resource_group_name   = azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.vault.name
  virtual_network_id    = module.network.vnet_id
  registration_enabled  = false
}

module "vm_agent" {
  source              = "./modules/vm-agent"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  name_prefix         = var.naming_prefix
  subnet_id           = module.network.agent_subnet_id
  vm_size             = var.vm_size
  admin_username      = var.admin_username
  ssh_public_key      = var.ssh_public_key
  custom_data         = local.agent_custom_data
  tags                = local.tags
}

module "keyvault" {
  source                   = "./modules/keyvault"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  name_prefix              = var.naming_prefix
  kv_unique_suffix         = var.kv_unique_suffix
  subnet_id                = module.network.pe_subnet_id
  private_dns_zone_id      = azurerm_private_dns_zone.vault.id
  vm_identity_principal_id = module.vm_agent.system_assigned_identity_principal_id
  allowed_ip_cidrs         = var.kv_allowed_ips
  tags                     = local.tags
}


module "openai" {
  count               = var.create_openai ? 1 : 0
  source              = "./modules/openai"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.openai_location
  name_prefix         = var.naming_prefix
  subnet_id           = module.network.pe_subnet_id
  private_dns_zone_id = azurerm_private_dns_zone.openai.id
  capacity            = var.openai_model_capacity
  tags                = local.tags
}

resource "azurerm_role_assignment" "vm_openai_user" {
  count                = var.create_openai ? 1 : 0
  scope                = module.openai[0].openai_account_id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = module.vm_agent.system_assigned_identity_principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "github_actions" {
  count                = var.github_actions_principal_id != "" ? 1 : 0
  scope                = azurerm_resource_group.rg.id
  role_definition_name = "Contributor"
  principal_id         = var.github_actions_principal_id
  principal_type       = "ServicePrincipal"
}


# Utilisateurs admin fixes (Object ID Entra ID) → lecture + écriture depuis le portail
resource "azurerm_role_assignment" "kv_admin_users" {
  for_each             = toset(var.kv_admin_object_ids)
  scope                = module.keyvault.key_vault_id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = each.value
}

# SP GitHub Actions → écriture des secrets dans le pipeline CI/CD
resource "azurerm_role_assignment" "github_actions_kv" {
  count                = var.github_actions_principal_id != "" ? 1 : 0
  scope                = module.keyvault.key_vault_id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.github_actions_principal_id
  principal_type       = "ServicePrincipal"
}
