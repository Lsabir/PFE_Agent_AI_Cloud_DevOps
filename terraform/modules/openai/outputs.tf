output "openai_account_name" {
  description = "Name of the Azure OpenAI account."
  value       = azurerm_cognitive_account.openai.name
}

output "openai_account_id" {
  description = "ID of the Azure OpenAI account."
  value       = azurerm_cognitive_account.openai.id
}


output "openai_private_endpoint_id" {
  description = "Private endpoint ID for Azure OpenAI."
  value       = azurerm_private_endpoint.openai_pe.id
}

output "openai_endpoint" {
  description = "Endpoint URL for the Azure OpenAI account."
  value       = azurerm_cognitive_account.openai.endpoint
}

output "openai_deployment_name" {
  description = "Name of the deployed model."
  value       = azurerm_cognitive_deployment.gpt.name
}

output "openai_primary_key" {
  description = "Primary access key for the Azure OpenAI account."
  value       = azurerm_cognitive_account.openai.primary_access_key
  sensitive   = true
}
