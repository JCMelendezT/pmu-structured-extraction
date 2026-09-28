resource "azurerm_role_assignment" "vm_kv_secrets_user" {
  scope                = data.azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_virtual_machine.vm.identity[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "vm_ml_data_scientist" {
  scope                = data.azurerm_machine_learning_workspace.mlw.id
  role_definition_name = "AzureML Data Scientist"
  principal_id         = azurerm_linux_virtual_machine.vm.identity[0].principal_id
  principal_type       = "ServicePrincipal"
}
