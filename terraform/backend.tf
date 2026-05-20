
terraform {
  backend "azurerm" {
    resource_group_name  = "tf-state-rg"
    storage_account_name = "tfstateagentdevops"
    container_name       = "tfstate"
    key                  = "agent-devops.tfstate"
  }
}
