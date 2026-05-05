output "vnet_id" {
  description = "Virtual Network resource ID."
  value       = azurerm_virtual_network.vnet.id
}

output "agent_subnet_id" {
  description = "Subnet ID for the agent VM."
  value       = azurerm_subnet.agent.id
}

output "pe_subnet_id" {
  description = "Subnet ID for private endpoints."
  value       = azurerm_subnet.private_endpoints.id
}

output "nsg_id" {
  description = "Network Security Group ID protecting the agent subnet."
  value       = azurerm_network_security_group.agent_nsg.id
}
