variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "germanywestcentral"
}




variable "resource_group_name" {
  description = "Name of the Azure Resource Group."
  type        = string
  default     = "agent-devops-rg"
}

variable "naming_prefix" {
  description = "Prefix used for resource names."
  type        = string
  default     = "agent-devops"
}

variable "project" {
  description = "Project tag value."
  type        = string
  default     = "agent-ai-devops"
}

variable "environment" {
  description = "Environment tag value."
  type        = string
  default     = "production"
}

variable "owner" {
  description = "Owner tag value."
  type        = string
  default     = "devops-team"
}

variable "common_tags" {
  description = "Common tags merged on all resources."
  type        = map(string)
  default     = {}
}

variable "vnet_address_space" {
  description = "Address space for the Azure Virtual Network."
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "agent_subnet_prefix" {
  description = "Subnet prefix for the VM Agent subnet."
  type        = string
  default     = "10.0.1.0/24"
}

variable "pe_subnet_prefix" {
  description = "Subnet prefix for private endpoints."
  type        = string
  default     = "10.0.2.0/24"
}

variable "admin_ip_cidr" {
  description = "CIDR range allowed to SSH into the VM."
  type        = string
  default     = "203.0.113.0/32"
}

variable "vm_size" {
  description = "Azure VM size for the Linux agent."
  type        = string
  default     = "Standard_B2s"
}

variable "admin_username" {
  description = "Admin username for the Linux VM."
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key" {
  description = "SSH public key for Linux VM access."
  type        = string
  default     = ""

  validation {
    condition     = length(trimspace(var.ssh_public_key)) > 0 && can(regex("^ssh-(rsa|ed25519|ecdsa)\\s+[A-Za-z0-9+/=]+", trimspace(var.ssh_public_key)))
    error_message = "ssh_public_key doit être une clé publique SSH valide, par exemple le contenu de ~/.ssh/id_rsa.pub."
  }
}

variable "github_actions_principal_id" {
  description = "Object ID of the GitHub Actions service principal or workload identity for RBAC."
  type        = string
  default     = ""
}

variable "openai_location" {
  description = "Azure region for the OpenAI resource (use a region with quota, e.g. swedencentral)."
  type        = string
  default     = "swedencentral"
}

variable "openai_model_capacity" {
  description = "Capacity in thousands of tokens per minute for the OpenAI deployment."
  type        = number
  default     = 1
}

variable "create_openai" {
  description = "Set to true to deploy Azure OpenAI via Terraform (requires quota approval on the subscription)."
  type        = bool
  default     = false
}

variable "kv_unique_suffix" {
  description = "Short unique suffix for the Key Vault name (globally unique constraint, e.g. '-pfe')."
  type        = string
  default     = "-pfe"
}

variable "custom_data" {
  description = "Placeholder cloud-init data injected into the Linux VM."
  type        = string
  default     = <<-EOT
    #cloud-config
    package_update: true
    package_upgrade: true
    packages: [python3.11, python3.11-venv, python3-pip, git, curl, unzip]
    runcmd:
      - update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
      - cd /home/azureuser && git clone https://github.com/Lsabir/PFE_Agent_AI_Cloud_DevOps.git agent-repo
      - cd /home/azureuser/agent-repo && python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
      - echo "GITHUB_OWNER=Lsabir" >> /home/azureuser/agent-repo/.env
      - chown -R azureuser:azureuser /home/azureuser/agent-repo
  EOT
}
