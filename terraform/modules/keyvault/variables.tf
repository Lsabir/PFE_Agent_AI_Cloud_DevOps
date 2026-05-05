variable "resource_group_name" {
  description = "Resource group where Key Vault resources are created."
  type        = string
}

variable "location" {
  description = "Location for Key Vault resources."
  type        = string
}

variable "name_prefix" {
  description = "Prefix used for Key Vault resource names."
  type        = string
}

variable "kv_unique_suffix" {
  description = "Short unique suffix appended to the Key Vault name (globally unique constraint)."
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "Subnet ID used for Key Vault private endpoint."
  type        = string
}

variable "private_dns_zone_id" {
  description = "Private DNS zone ID linked to Key Vault private endpoint."
  type        = string
}

variable "vm_identity_principal_id" {
  description = "Principal ID of the VM system assigned managed identity."
  type        = string
}

variable "tags" {
  description = "Tags applied to Key Vault resources."
  type        = map(string)
}




# a supprimer apres test
variable "enable_secrets" {
  description = "Enable creation of Key Vault secrets (set false for initial infra deployment)."
  type        = bool
  default     = false
}
