variable "subscription_id" {
  description = "ID de la suscripción de Azure. No tiene default: el repo es público."
  type        = string
}

variable "resource_group_name" {
  description = "Grupo de recursos donde se crea la VM y la red."
  type        = string
  default     = "rg-sirena-mp3"
}

variable "location" {
  description = "Región de Azure. Debe ser una permitida por la política sys.regionrestriction."
  type        = string
  default     = "westus"
}

variable "workspace_name" {
  description = "Nombre del workspace de Azure ML existente."
  type        = string
  default     = "mlw-sirena"
}

variable "key_vault_name" {
  description = "Nombre del Key Vault existente."
  type        = string
  default     = "mlwsirenkeyvault18607254"
}

variable "vm_size" {
  description = "Tamaño de la VM. Standard_B2s por defecto; Standard_D2as_v4 solo en ventanas de carga."
  type        = string
  default     = "Standard_B2s"
}

variable "ssh_public_key_path" {
  description = "Ruta a la llave pública SSH. No tiene default: es local de cada persona."
  type        = string
}

variable "ips_admin" {
  description = "IPs con acceso SSH (puerto 22). Solo estas IPs."
  type        = list(string)
}

variable "ips_equipo" {
  description = "IPs del equipo con acceso a BFF (8000) y Frontend (8501). Se concatena con ips_admin."
  type        = list(string)
}

variable "repo_url" {
  description = "URL del repo a clonar en la VM."
  type        = string
  default     = "https://github.com/JCMelendezT/pmu-structured-extraction.git"
}

variable "repo_branch" {
  description = "Rama a clonar en la VM. Solo se usa al crear la VM (ver lifecycle ignore_changes)."
  type        = string
  default     = "feature/azureml-pipeline"
}

# apagado_hora fue eliminada: el auto-apagado con
# azurerm_dev_test_global_vm_shutdown_schedule no está disponible en
# chilecentral. El apagado es manual con `az vm deallocate`. Ver PROGRESO.md,
# hallazgo H19.
