data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "agent_key_vault" {
  name                            = "${var.name_prefix}-kv${var.kv_unique_suffix}"
  resource_group_name             = var.resource_group_name
  location                        = var.location
  tenant_id                       = data.azurerm_client_config.current.tenant_id
  sku_name                        = "standard"
  soft_delete_retention_days      = 90
  purge_protection_enabled        = false
  rbac_authorization_enabled      = true
  enabled_for_disk_encryption     = false
  enabled_for_deployment          = false
  enabled_for_template_deployment = false

  network_acls {
    default_action = "Deny"
    bypass         = "None"
  }

  tags = var.tags
}

resource "azurerm_key_vault_secret" "jira_api_token" {
  name         = "jira-api-token"
  value        = "PLACEHOLDER"
  key_vault_id = azurerm_key_vault.agent_key_vault.id



 # a supprimer apres test
   count        = var.enable_secrets ? 1 : 0
}

resource "azurerm_key_vault_secret" "gitlab_token" {
  name         = "gitlab-token"
  value        = "PLACEHOLDER"
  key_vault_id = azurerm_key_vault.agent_key_vault.id


 # a supprimer apres test
   count        = var.enable_secrets ? 1 : 0
}

resource "azurerm_key_vault_secret" "github_token" {
  name         = "github-token"
  value        = "PLACEHOLDER"
  key_vault_id = azurerm_key_vault.agent_key_vault.id

  # a supprimer apres test
   count        = var.enable_secrets ? 1 : 0
}

resource "azurerm_key_vault_secret" "azure_openai_key" {
  name         = "azure-openai-key"
  value        = "PLACEHOLDER"
  key_vault_id = azurerm_key_vault.agent_key_vault.id


 # a supprimer apres test
   count        = var.enable_secrets ? 1 : 0
}

resource "azurerm_private_endpoint" "key_vault_pe" {
  name                = "${var.name_prefix}-kv-pe"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.subnet_id

  private_service_connection {
    name                           = "kv-psc"
    private_connection_resource_id = azurerm_key_vault.agent_key_vault.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "kv-dns"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }
}

resource "azurerm_role_assignment" "vm_key_vault" {
  scope                = azurerm_key_vault.agent_key_vault.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = var.vm_identity_principal_id
  principal_type       = "ServicePrincipal"
}
