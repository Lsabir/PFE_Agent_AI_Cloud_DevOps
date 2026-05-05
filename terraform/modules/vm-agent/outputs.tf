output "vm_id" {
  description = "ID of the agent VM."
  value       = azurerm_linux_virtual_machine.agent.id
}

output "vm_name" {
  description = "Name of the agent VM."
  value       = azurerm_linux_virtual_machine.agent.name
}

output "system_assigned_identity_principal_id" {
  description = "Principal ID of the system assigned managed identity."
  value       = azurerm_linux_virtual_machine.agent.identity[0].principal_id
}

output "private_ip_address" {
  description = "Private IP address assigned to the agent VM."
  value       = azurerm_network_interface.agent_nic.ip_configuration[0].private_ip_address
}

output "public_ip_address" {
  description = "Public IP address of the agent VM (for SSH)."
  value       = azurerm_public_ip.agent.ip_address
}
