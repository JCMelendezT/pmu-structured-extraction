resource "azurerm_linux_virtual_machine" "vm" {
  name                = "vm-sirena"
  location            = data.azurerm_resource_group.rg.location
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

resource "azurerm_dev_test_global_vm_shutdown_schedule" "auto_apagado" {
  virtual_machine_id = azurerm_linux_virtual_machine.vm.id
  location           = data.azurerm_resource_group.rg.location

  daily_recurrence_time = var.apagado_hora
  timezone              = "SA Pacific Standard Time"

  notification_settings {
    enabled = false
  }
}
