variable "resource_group_name" {
  description = "Resource group for the VM agent."
  type        = string
}

variable "location" {
  description = "Location for the VM agent."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for VM-related resources."
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID for the agent VM."
  type        = string
}

variable "vm_size" {
  description = "Size of the VM."
  type        = string



  default     = "Standard_B2ms"
}

variable "admin_username" {
  description = "Admin username for the Linux VM."
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key for VM access."
  type        = string
}

variable "custom_data" {
  description = "Cloud-init configuration for the VM."
  type        = string
}

variable "image_publisher" {
  description = "Image publisher for the Linux VM."
  type        = string
  default     = "Canonical"
}

variable "image_offer" {
  description = "Image offer for the Linux VM."
  type        = string
  default     = "0001-com-ubuntu-server-jammy"
}

variable "image_sku" {
  description = "Image SKU for the Linux VM."
  type        = string
  default     = "22_04-lts"
}

variable "tags" {
  description = "Tags to apply to the VM and NIC."
  type        = map(string)
}
