variable "resource_group_name" {
  description = "Resource group where network resources are created."
  type        = string
}

variable "location" {
  description = "Location for network resources."
  type        = string
}

variable "vnet_name" {
  description = "Virtual Network name."
  type        = string
}

variable "address_space" {
  description = "Address space for the VNet."
  type        = list(string)
}

variable "agent_subnet_prefix" {
  description = "CIDR prefix for the agent subnet."
  type        = string
}

variable "pe_subnet_prefix" {
  description = "CIDR prefix for the private endpoint subnet."
  type        = string
}

variable "admin_ip_cidr" {
  description = "CIDR range allowed to SSH into the agent VM."
  type        = string
}

variable "tags" {
  description = "Tags to apply to network resources."
  type        = map(string)
}
