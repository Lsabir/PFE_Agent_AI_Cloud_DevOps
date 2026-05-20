variable "resource_group_name" {
  description = "Resource group where OpenAI account is created."
  type        = string
}

variable "location" {
  description = "Location for the OpenAI account."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for OpenAI resources."
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID used for OpenAI private endpoint."
  type        = string
}

variable "private_dns_zone_id" {
  description = "Private DNS zone ID for the OpenAI private endpoint."
  type        = string
}

variable "tags" {
  description = "Tags to apply to the OpenAI account."
  type        = map(string)
}

variable "deployment_name" {
  description = "Name for the model deployment."
  type        = string
  default     = "gpt-4o"
}

variable "model_name" {
  description = "OpenAI model to deploy."
  type        = string
  default     = "gpt-4o"
}

variable "model_version" {
  description = "Model version to deploy."
  type        = string
  default     = "2024-11-20"
}

variable "capacity" {
  description = "Capacity in thousands of tokens per minute for the model deployment."
  type        = number
  default     = 1
}
