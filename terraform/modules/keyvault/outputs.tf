output "key_vault_id" {
  description = "Key Vault resource ID."
  value       = azurerm_key_vault.agent_key_vault.id
}

output "key_vault_uri" {
  description = "Key Vault URI."
  value       = azurerm_key_vault.agent_key_vault.vault_uri
}

output "key_vault_name" {
  description = "Name of the Key Vault."
  value       = azurerm_key_vault.agent_key_vault.name
}

output "key_vault_private_endpoint_id" {
  description = "Private endpoint ID for the Key Vault."
  value       = azurerm_private_endpoint.key_vault_pe.id
}
