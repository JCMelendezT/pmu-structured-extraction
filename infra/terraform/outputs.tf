output "ip_publica" {
  description = "IP pública de la VM."
  value       = azurerm_public_ip.pip.ip_address
}

output "url_tablero" {
  description = "URL del tablero (Frontend)."
  value       = "http://${azurerm_public_ip.pip.ip_address}:8501"
}

output "url_bff" {
  description = "URL del BFF."
  value       = "http://${azurerm_public_ip.pip.ip_address}:8000"
}

output "url_docs_bff" {
  description = "URL de la documentación del BFF."
  value       = "http://${azurerm_public_ip.pip.ip_address}:8000/docs"
}

output "ssh" {
  description = "Comando SSH para conectar a la VM."
  value       = "ssh azureuser@${azurerm_public_ip.pip.ip_address}"
}

output "vm_principal_id" {
  description = "Principal ID de la identidad administrada de la VM."
  value       = azurerm_linux_virtual_machine.vm.identity[0].principal_id
}
