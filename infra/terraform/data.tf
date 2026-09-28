data "azurerm_resource_group" "rg" {
  name = var.resource_group_name
}

data "azurerm_machine_learning_workspace" "mlw" {
  name                = var.workspace_name
  resource_group_name = data.azurerm_resource_group.rg.name
}

data "azurerm_key_vault" "kv" {
  name                = var.key_vault_name
  resource_group_name = data.azurerm_resource_group.rg.name
}
