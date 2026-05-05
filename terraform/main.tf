locals {
  tags = merge({
    project     = var.project
    environment = var.environment
    owner       = var.owner
  }, var.common_tags)
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
  custom_data         = var.custom_data
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
  tags                     = local.tags
}

# OpenAI est optionnel — activé via create_openai=true une fois le quota approuvé
# En attendant le quota Azure OpenAI, créer la ressource manuellement via le portail Azure
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
