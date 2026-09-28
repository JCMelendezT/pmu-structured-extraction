resource "azurerm_linux_virtual_machine" "vm" {
  name                = "vm-sirena"
  location            = var.location
  resource_group_name = data.azurerm_resource_group.rg.name
  size                = var.vm_size
  admin_username      = "azureuser"
  network_interface_ids = [
    azurerm_network_interface.nic.id,
  ]

  admin_ssh_key {
    username   = "azureuser"
    public_key = file(var.ssh_public_key_path)
  }

  os_disk {
    name                 = "osdisk-sirena"
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 32
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  identity {
    type = "SystemAssigned"
  }

  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml.tftpl", {
    repo_url    = var.repo_url
    repo_branch = var.repo_branch
  }))

  lifecycle {
    ignore_changes = [custom_data]
  }
}

# azurerm_dev_test_global_vm_shutdown_schedule fue descartado: el servicio
# Microsoft.DevTestLab/schedules no está disponible en chilecentral, y el
# schedule debe estar en la misma región que la VM. El apagado es manual
# con `az vm deallocate`. Ver PROGRESO.md, hallazgo H19.
