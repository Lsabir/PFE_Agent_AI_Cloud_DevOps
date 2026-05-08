output "resource_group_name" {
  description = "Resource group where the infrastructure is deployed."
  value       = azurerm_resource_group.rg.name
}

output "virtual_network_id" {
  description = "Virtual Network ID."
  value       = module.network.vnet_id
}

output "agent_subnet_id" {
  description = "Subnet ID used by the agent VM."
  value       = module.network.agent_subnet_id
}

output "private_endpoint_subnet_id" {
  description = "Subnet ID reserved for private endpoints."
  value       = module.network.pe_subnet_id
}

output "vm_agent_id" {
  description = "Agent VM resource ID."
  value       = module.vm_agent.vm_id
}

output "key_vault_uri" {
  description = "URI of the deployed Key Vault."
  value       = module.keyvault.key_vault_uri
}

output "key_vault_name" {
  description = "Name of the deployed Key Vault."
  value       = module.keyvault.key_vault_name
}

output "openai_account_name" {
  description = "Azure OpenAI account name (only when create_openai=true)."
  value       = var.create_openai ? module.openai[0].openai_account_name : "not deployed via Terraform — create manually in Azure Portal"
}

output "vm_public_ip" {
  description = "Public IP address of the agent VM (use for SSH)."
  value       = module.vm_agent.public_ip_address
}

output "openai_endpoint" {
  description = "Azure OpenAI endpoint URL (only when create_openai=true)."
  value       = var.create_openai ? module.openai[0].openai_endpoint : "set AZURE_OPENAI_ENDPOINT manually in .env on the VM"
}

output "openai_deployment_name" {
  description = "Deployed model name (only when create_openai=true)."
  value       = var.create_openai ? module.openai[0].openai_deployment_name : "gpt-4o-mini"
}

output "openai_primary_key" {
  description = "Primary API key for Azure OpenAI (only when create_openai=true)."
  value       = var.create_openai ? module.openai[0].openai_primary_key : "set AZURE_OPENAI_API_KEY manually in .env on the VM"
  sensitive   = true
}

output "ssh_command" {
  description = "SSH command to connect to the agent VM."
  value       = "ssh -i ~/.ssh/id_ed25519 azureuser@${module.vm_agent.public_ip_address}"
}
