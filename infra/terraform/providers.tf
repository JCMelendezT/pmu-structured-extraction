provider "azurerm" {
  subscription_id = var.subscription_id
  features {}

  resource_provider_registrations = "none"
}
