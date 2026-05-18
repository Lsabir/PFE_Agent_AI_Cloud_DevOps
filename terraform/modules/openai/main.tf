resource "azurerm_cognitive_account" "openai" {
  name                          = "${var.name_prefix}-openai"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  sku_name                      = "S0"
  kind                          = "OpenAI"
  public_network_access_enabled = true
  custom_subdomain_name         = "${var.name_prefix}-openai"
  tags                          = var.tags
}


resource "time_sleep" "wait_for_openai_provisioning" {
  depends_on      = [azurerm_cognitive_account.openai]
  create_duration = "300s"
}

resource "azurerm_cognitive_deployment" "gpt" {
  name                 = var.deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.model_name
    version = var.model_version
  }

  sku {
    name     = "Standard"
    capacity = var.capacity
  }

  depends_on = [time_sleep.wait_for_openai_provisioning]
}

resource "azurerm_private_endpoint" "openai_pe" {
  name                = "${var.name_prefix}-openai-pe"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.subnet_id

  private_service_connection {
    name                           = "openai-psc"
    private_connection_resource_id = azurerm_cognitive_account.openai.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "openai-dns"
    private_dns_zone_ids = [var.private_dns_zone_id]
  }

  depends_on = [time_sleep.wait_for_openai_provisioning]
}
