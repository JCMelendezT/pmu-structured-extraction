# Plan de infraestructura — Microproyecto 3 (responsable: Juan)

Juan monta y opera la infraestructura de SIRENA en Azure: cierra el pipeline de Azure ML que ya está casi listo, levanta con Terraform una VM que corre los 7 contenedores, y entrega al equipo la IP y las reglas para que hagan las pruebas de carga. Lo demás (pruebas de carga, análisis, documento y presentación) es del resto del equipo.

Este plan reemplaza las Fases 7 y 8 de `PLAN_MP3.md` (VM creada a mano con `az vm create`). El resto de `PLAN_MP3.md` sigue siendo el contexto general del microproyecto.

## 1. Alcance

| Es de Juan | No es de Juan | A coordinar con el equipo |
| --- | --- | --- |
| Cerrar B7: corrida corta `limite=5` del pipeline en verde | Pruebas de carga y su análisis | Quién lanza la corrida completa de 340 mensajes (C4) |
| Terraform de la VM, la red y los permisos (`infra/terraform/`) | Cambios a la lógica de los microservicios | Horarios en que la VM debe estar encendida para las pruebas |
| Desplegar los contenedores en la VM y dejarlos sanos | Documento de requerimientos, costos finales y diapositivas | Si las pruebas de carga usan Groq real o un modo simulado |
| Cerrar el ciclo MLOps: la VM toma el modelo del registro de Azure ML | Extras de la Fase 9 (Designer, endpoint por lotes) | Qué IP públicas hay que autorizar en el NSG |
| Entregar `ENTREGA_EQUIPO.md` con IP, URLs, accesos y restricciones | | |
| Operar la infraestructura: encender, apagar, redimensionar, autorizar IP, y limpieza final | | |

## 2. Punto de partida

Todo esto ya existe, creado con Azure CLI en las etapas A y B (último commit `ab6f11c` en `feature/azureml-pipeline`, fork `JCMelendezT/pmu-structured-extraction`).

| Recurso | Nombre | Estado |
| --- | --- | --- |
| Suscripción | Azure for Students `1ba330a0-5897-4ef6-8fd1-d304b0e766d1`, tenant `693cbea0-4ef9-4254-8977-76e05cb5f556` | Activa |
| Grupo de recursos | `rg-sirena-mp3` (`westus`) | Succeeded |
| Presupuesto | `presupuesto-sirena-mp3`, USD 30/mes, alertas 50 % y 80 % | Activo (solo alerta, no corta) |
| Workspace de Azure ML | `mlw-sirena` | Succeeded |
| Key Vault | `mlwsirenkeyvault18607254` (RBAC) | Succeeded |
| Container Registry | `f1f0a3...` (Basic), creado por el build del Environment | Succeeded |
| Data asset | `gold_v1` v1 | Creado |
| Environment | `sirena-eval` v1 | Build Completed |
| Clúster | `cpu-sirena`, `Standard_DS2_v2`, 0–2 nodos, identidad `a9efd341-1dc2-4aff-9dc5-11717d40ae17` | Succeeded |
| Roles del clúster | Key Vault Secrets User (Key Vault) y AzureML Data Scientist (workspace) | Asignados |
| Rol de Juan | Key Vault Secrets Officer | Asignado |
| Secreto `groq-api-key` | Existe, **pero su valor es el marcador `TU_CLAVE_DE_GROQ`** | **Bloquea B7** |

El pipeline `elated_branch_htpynmndk1` llegó hasta los pasos de evaluación: leyó el secreto con la identidad del clúster (el acceso funciona) y falló con 401 de Groq porque el valor es el marcador. No hay nada que corregir en el código para esto; solo hay que escribir la clave real.

## 3. Decisiones de infraestructura

| ID | Decisión | Por qué |
| --- | --- | --- |
| I-D1 | Una sola VM `Standard_B2s` con Docker Compose, como en el plan original | Cuota y crédito de estudiante; el `docker-compose.yml` ya existe; 1 IP pública de 3 |
| I-D2 | Terraform gestiona **solo lo nuevo**: red, NSG, IP pública, VM, auto-apagado y los roles de la VM. Lo creado con CLI se referencia con bloques `data` | Importar el workspace, el Key Vault o el clúster a Terraform arriesga que un `apply` los reemplace o los destruya, y se perderían corridas y permisos. Referenciarlos da el mismo resultado sin ese riesgo |
| I-D3 | El estado de Terraform es local, en la máquina de Juan, y **no se versiona** | Solo Juan aplica cambios. El `.tfstate` puede contener datos sensibles. Lo que se comparte con el equipo es el código `.tf`, el `.terraform.lock.hcl` y un `terraform.tfvars.example` |
| I-D4 | Ningún secreto entra en Terraform. La VM lee `groq-api-key` y `telegram-bot-token` del Key Vault con su identidad administrada, mediante `infra/scripts/cargar_secretos.sh` | Un secreto en `.tf`, `tfvars`, `cloud-init` o en un output queda escrito en el estado y en los metadatos de la VM. El Key Vault ya existe y es la fuente única de la clave de Groq |
| I-D5 | El NSG abre solo 22 (IP de Juan) y 8000 y 8501 (IP de Juan y del equipo), con listas en `terraform.tfvars` | BFF y Frontend no tienen autenticación. CRUD, Process, Inference y Geo (8001–8004) nunca se exponen: CRUD acepta `PATCH` sin credenciales. Autorizar una IP nueva es editar `tfvars` y aplicar |
| I-D6 | El tamaño de la VM es una variable. Para las ventanas de prueba de carga se sube a `Standard_D2as_v4` y después se baja | La serie B es de ráfaga: con carga sostenida agota créditos de CPU y baja a su línea base, lo que ensucia la medición. `standardDASv4Family` tiene 4 vCPU libres, familia distinta de la del clúster (`DSv2`) |
| I-D7 | Auto-apagado diario a las 23:00 hora de Bogotá con `azurerm_dev_test_global_vm_shutdown_schedule` | Una VM olvidada encendida es el gasto más probable. El presupuesto solo avisa; el auto-apagado corta |
| I-D8 | La VM clona el repo definido por variables (`repo_url`, `repo_branch`). Por defecto el fork con `feature/azureml-pipeline`, que ya tiene `INFERENCE_MODELO` en el Compose | `repo_url` y `repo_branch` solo cuentan al **crear** la VM: cambiar `custom_data` obliga a recrearla y se perdería la base SQLite. Por eso la VM lleva `lifecycle { ignore_changes = [custom_data] }`, y cambiar de rama después se hace con `git checkout` dentro de la VM |

## 4. Arquitectura de la infraestructura

```text
Internet
  │   22   solo desde ips_admin (Juan)
  │ 8000   BFF        desde ips_admin + ips_equipo
  │ 8501   Frontend   desde ips_admin + ips_equipo
  ▼
pip-sirena (IP pública Standard, estática)
  │
nsg-sirena ── snet-sirena (10.10.1.0/24) ── vnet-sirena (10.10.0.0/16)
  │
vm-sirena (Ubuntu 22.04, Standard_B2s, disco Standard SSD 32 GiB, identidad SystemAssigned)
  ├── Docker Compose: bff, telegram-source, crud(+volumen SQLite), process, inference, geo, frontend
  ├── cargar_secretos.sh ──(identidad de la VM, Key Vault Secrets User)──▶ mlwsirenkeyvault18607254
  ├── desplegar_config.sh ─(identidad de la VM, AzureML Data Scientist)─▶ mlw-sirena / sirena-extractor
  ├── salida HTTPS ──▶ API de Groq y API de Telegram (long polling, sin puerto de entrada)
  └── auto-apagado 23:00 (SA Pacific Standard Time)

Ya existente (bloques data, Terraform no lo modifica):
  rg-sirena-mp3 · mlw-sirena · mlwsirenkeyvault18607254 · cpu-sirena · ACR · Storage · App Insights
```

## 5. Terraform: estructura y recursos

```text
infra/
├── terraform/
│   ├── versions.tf               terraform >= 1.9, azurerm ~> 4.0
│   ├── providers.tf              subscription_id por variable, resource_provider_registrations = "none"
│   ├── variables.tf              todo lo que cambia entre personas o suscripciones
│   ├── data.tf                   grupo, workspace y Key Vault existentes
│   ├── network.tf                vnet, subnet, nsg + reglas, asociación, IP pública, NIC
│   ├── vm.tf                     VM, auto-apagado
│   ├── roles.tf                  roles de la identidad de la VM
│   ├── outputs.tf                IP, URLs, comando SSH, principal_id
│   ├── cloud-init.yaml.tftpl     Docker, Azure CLI + extensión ml, clonado del repo. Sin secretos
│   ├── terraform.tfvars.example  valores de ejemplo, versionado
│   └── .terraform.lock.hcl       versionado (fija las versiones del proveedor)
└── scripts/
    ├── cargar_secretos.sh        Key Vault → .env (chmod 600), sin imprimir valores
    ├── desplegar_config.sh       registro de modelos → INFERENCE_MODELO → reinicia inference
    └── salud.sh                  curl a /health de los 5 servicios dentro de la VM
```

| Recurso Terraform | Nombre | Atributos que importan |
| --- | --- | --- |
| `data.azurerm_resource_group` | `rg-sirena-mp3` | Todo se crea aquí |
| `data.azurerm_machine_learning_workspace` | `mlw-sirena` | Alcance del rol AzureML Data Scientist |
| `data.azurerm_key_vault` | `mlwsirenkeyvault18607254` | Alcance del rol Key Vault Secrets User |
| `azurerm_virtual_network` + `azurerm_subnet` | `vnet-sirena`, `snet-sirena` | `10.10.0.0/16`, `10.10.1.0/24` |
| `azurerm_network_security_group` | `nsg-sirena` | Reglas: `ssh` 22 desde `ips_admin`; `bff` 8000 y `frontend` 8501 desde `ips_admin + ips_equipo`. Nada más de entrada |
| `azurerm_subnet_network_security_group_association` | — | NSG aplicado a la subred |
| `azurerm_public_ip` | `pip-sirena` | `sku = "Standard"`, `allocation_method = "Static"` |
| `azurerm_network_interface` | `nic-sirena` | IP pública asociada |
| `azurerm_linux_virtual_machine` | `vm-sirena` | `size = var.vm_size` (por defecto `Standard_B2s`); `admin_username = "azureuser"`; `admin_ssh_key` desde `var.ssh_public_key_path`; `disable_password_authentication = true`; `os_disk`: `StandardSSD_LRS`, 32 GiB; imagen `Canonical / 0001-com-ubuntu-server-jammy / 22_04-lts-gen2 / latest`; `identity { type = "SystemAssigned" }`; `custom_data = base64encode(templatefile(...))`; `lifecycle { ignore_changes = [custom_data] }` |
| `azurerm_dev_test_global_vm_shutdown_schedule` | — | `daily_recurrence_time = "2300"`, `timezone = "SA Pacific Standard Time"`, notificación desactivada |
| `azurerm_role_assignment` | — | Identidad de la VM → `Key Vault Secrets User` sobre el Key Vault |
| `azurerm_role_assignment` | — | Identidad de la VM → `AzureML Data Scientist` sobre el workspace |

Variables mínimas: `subscription_id`, `resource_group_name`, `location` (`westus`), `workspace_name`, `key_vault_name`, `vm_size`, `ssh_public_key_path`, `ips_admin` (lista), `ips_equipo` (lista), `repo_url`, `repo_branch`, `apagado_hora`. Ninguna con valor por defecto que sea un identificador de la suscripción: el repo es público.

Outputs: `ip_publica`, `url_tablero` (`http://<ip>:8501`), `url_bff` (`http://<ip>:8000`), `url_docs_bff` (`http://<ip>:8000/docs`), `ssh` (`ssh azureuser@<ip>`), `vm_principal_id`.

`.gitignore` de `infra/terraform/`: `.terraform/`, `*.tfstate`, `*.tfstate.*`, `*.tfplan`, `terraform.tfvars`, `crash.log`. El `.terraform.lock.hcl` **sí** se versiona.

## 6. Tickets

Cada ticket termina con una verificación concreta y se registra en `PROGRESO.md`.

### I0 — Cerrar B7 (pipeline de Azure ML)

1. Juan escribe la clave real en el Key Vault (la clave empieza por `gsk_`):
   `az keyvault secret set --vault-name mlwsirenkeyvault18607254 --name groq-api-key --value "<clave real>"`
2. Verificación sin revelar el valor: `az keyvault secret show --vault-name mlwsirenkeyvault18607254 --name groq-api-key --query "starts_with(value, 'gsk_')" -o tsv` debe devolver `true`.
3. Relanzar la corrida corta con los mismos inputs de la vez anterior y `limite=5`.

Verificación: los 5 pasos en verde, `metricas.json` de los dos modelos, `decision.json`, y `sirena-extractor` versión 1 con sus tags en el registro.

### I1 — Código Terraform (sin tocar Azure)

Escribir `infra/terraform/` y `infra/scripts/` según la sección 5. Instalar Terraform en Windows con `winget install Hashicorp.Terraform`.

Verificación: `terraform init`, `terraform fmt -check -recursive` y `terraform validate` en verde; `.gitignore` probado con `git status` (ningún `.tfstate` ni `terraform.tfvars` aparece); `shellcheck` sobre los scripts si está disponible.

### I2 — Secreto de Telegram en el Key Vault (Juan)

`az keyvault secret set --vault-name mlwsirenkeyvault18607254 --name telegram-bot-token --value "<token del bot>"`

Verificación: `az keyvault secret show ... --name telegram-bot-token --query "attributes.enabled"` devuelve `true`.

### I3 — Plan y aplicación

1. `terraform plan -out tfplan` y mostrar el resumen al humano. Debe decir `to add` para los recursos nuevos y **`0 to change, 0 to destroy`**.
2. Con confirmación, `terraform apply tfplan`.
3. Guardar los outputs.

Verificación: `az vm show -g rg-sirena-mp3 -n vm-sirena --query "{estado:provisioningState, tamaño:hardwareProfile.vmSize}"`; `az role assignment list --assignee <vm_principal_id> --all -o table` muestra exactamente los dos roles con sus alcances; conectar por SSH desde la IP de Juan; `cloud-init status --wait` en la VM devuelve `done`.

### I4 — Desplegar los contenedores en la VM

1. `bash infra/scripts/cargar_secretos.sh` (crea `.env` con permisos 600, sin imprimir valores).
2. `docker compose build --parallel 1` (en serie: la B2s tiene 4 GB).
3. `docker compose up -d bff telegram-source crud process inference geo frontend` (sin `mlflow`).
4. `bash infra/scripts/salud.sh`.

Verificación: los 5 `/health` responden `ok`; `docker compose ps` sin reinicios; el tablero abre en `http://<ip>:8501` desde la IP de Juan.

### I5 — Cerrar el ciclo MLOps

`bash infra/scripts/desplegar_config.sh` (lee la última versión de `sirena-extractor`, fija `INFERENCE_MODELO` en `.env`, reinicia solo `inference`).

Verificación: `docker compose exec inference env | grep INFERENCE_MODELO` muestra el modelo ganador de I0.

### I6 — Prueba de humo externa

1. Un mensaje real al bot de Telegram aparece en el tablero con tipo de evento y comuna.
2. `curl -X POST http://<ip>:8000/mensajes` con un `id_externo` nuevo responde `202`.
3. Desde una red no autorizada (datos móviles), 8000 y 8501 no responden.

### I7 — Entrega al equipo

Completar `docs/microproyecto3/ENTREGA_EQUIPO.md` con los valores reales y compartirlo. Agregar al NSG las IP que manden los compañeros.

### I8 — Operación durante las pruebas y limpieza

| Acción | Comando |
| --- | --- |
| Encender | `az vm start -g rg-sirena-mp3 -n vm-sirena` (luego `docker compose up -d` si algún contenedor no arrancó) |
| Apagar y dejar de pagar cómputo | `az vm deallocate -g rg-sirena-mp3 -n vm-sirena` |
| Autorizar una IP | Agregarla a `ips_equipo` en `terraform.tfvars`, `terraform plan`, `terraform apply` |
| Ventana de prueba de carga | `vm_size = "Standard_D2as_v4"` en `tfvars`, plan y apply (reinicia la VM); al terminar, volver a `Standard_B2s` |
| Nueva versión del código | En la VM: `git fetch`, `git checkout <rama>` si cambia, `git pull`, `docker compose build --parallel 1`, `docker compose up -d`. No se toca `repo_branch` en Terraform |
| Limpieza final, después de la sustentación y solo si Juan lo pide | `terraform destroy` para lo de Terraform y luego `az group delete -n rg-sirena-mp3` para el resto. Rotar la clave de Groq y revocar el token del bot |

## 7. Costos de la infraestructura

Precios de lista en `westus`, Linux, pago por uso, verificados en `prices.azure.com` el 2026-09-27.

| Recurso | Precio unitario (USD) | Demo: 2 semanas | Operación 24/7: mes |
| --- | --- | --- | --- |
| VM `Standard_B2s` | 0,0496 / hora | 2,78 (56 h) | 36,21 |
| VM `Standard_D2as_v4`, solo en ventanas de carga | 0,112 / hora | 0,90 (8 h) | — |
| Disco del SO, Standard SSD 32 GiB (**E4 LRS**) | 2,40 / mes, se cobra aunque la VM esté apagada | 1,12 | 2,40 |
| IP pública Standard estática | 0,005 / hora, se cobra mientras exista | 1,68 | 3,65 |
| VNet, subred, NSG, auto-apagado | 0 | 0 | 0 |
| **Total de la VM** | | **≈ 6,5** | **≈ 42** |

**Corrección a `PLAN_MP3.md` y `REGLAS_AGENTE.md` (H17).** El hallazgo H16 cotizó el disco de 32 GB como `E1 LRS` a 0,30/mes. Es incorrecto: `E1` es de 4 GiB y `E4` es de 32 GiB, y `E4 LRS` cuesta 2,40/mes en `westus`. La imagen de Ubuntu necesita al menos 30 GiB, así que el disco es `E4`. El precio original del plan era el correcto.

## 8. Lo que el equipo debe saber antes de las pruebas de carga

Esto va resumido en `ENTREGA_EQUIPO.md`; aquí está el porqué.

- **Groq es el cuello de botella de `POST /mensajes`, no Azure.** Cada mensaje accionable hace dos llamadas al LLM. El plan gratuito de Groq tiene límites de peticiones por minuto y responde 429; el plan de pago cobra por token. Una prueba de carga masiva sobre `POST /mensajes` mide a Groq y gasta la cuota del equipo. Conviene separar las pruebas: lectura (`GET /reportes`, `GET /reportes/resumen`, `GET /health`) para medir la infraestructura, y escritura con volumen bajo y controlado.
- **Cada `POST /mensajes` necesita un `id_externo` único.** Si se repite, BFF responde `409`. Un script de carga que reutiliza el mismo cuerpo mide 409, no el pipeline. Además, BFF responde `202` antes de procesar: la latencia de `POST /mensajes` no incluye el pipeline.
- **CRUD usa SQLite, con un solo escritor.** Con escritura concurrente va a ser el primer límite. Es un hallazgo esperable para el análisis, no un error de la infraestructura.
- **La serie B es de ráfaga.** Para pruebas sostenidas hay que pedirle a Juan la ventana con `Standard_D2as_v4`; con la B2s los resultados caen cuando se agotan los créditos de CPU.
- **Solo 8000 (BFF) y 8501 (Frontend) están expuestos, y solo a IP autorizadas.** Nadie prueba contra 8001–8004.
- **Métricas disponibles:** las métricas de plataforma de la VM en el portal (CPU, red, disco) sin costo, y `docker stats` dentro de la VM, que corre Juan.
- **La VM se apaga sola a las 23:00.** Las pruebas se coordinan con Juan para encenderla antes.

## 9. Riesgos y plan B

| Riesgo | Señal | Plan B |
| --- | --- | --- |
| Terraform no puede escribir por MFA | `AADSTS50076` en `apply` (Terraform usa el token de la Azure CLI) | Repetir el `az login --tenant 693cbea0-... --scope "https://management.core.windows.net//.default"` que ya funcionó en B2, con el claims challenge completo si lo pide |
| El proveedor intenta registrar resource providers | Error de registro al primer `plan` | Ya está resuelto con `resource_provider_registrations = "none"`; verificar que `Microsoft.Compute` y `Microsoft.Network` estén `Registered` |
| `plan` quiere cambiar o destruir algo existente | `to change` o `to destroy` distinto de 0 | No aplicar. Revisar: algo que debía ser `data` quedó como `resource` |
| Sin capacidad para `Standard_B2s` en `westus` | `SkuNotAvailable` | `Standard_B2s_v2` (cuota Bsv2 10 vCPU, 0,0992/h); la región no se cambia porque el Key Vault y el workspace están en `westus` |
| Sin RAM al construir las imágenes | Build lento o contenedores reiniciando | Construir en serie; si no alcanza, `vm_size = "Standard_B2s_v2"` temporalmente |
| Se pierde el `.tfstate` | Terraform quiere crear todo de nuevo | Bloques `import` para los recursos de Terraform (no para los `data`). Por eso el estado no se borra ni se comparte |
| IP dinámica de un compañero | Deja de poder entrar | Pedir la IP nueva y aplicar; nunca abrir a `0.0.0.0/0` |
| Un secreto termina en un archivo | Aparece en `git diff` o en el estado | Rotarlo de inmediato en Groq o BotFather y reescribirlo en el Key Vault |

## 10. Cambios al repositorio

| Archivo | Tipo |
| --- | --- |
| `infra/terraform/*.tf`, `cloud-init.yaml.tftpl`, `terraform.tfvars.example`, `.terraform.lock.hcl`, `.gitignore` | Nuevo |
| `infra/scripts/cargar_secretos.sh`, `desplegar_config.sh`, `salud.sh` | Nuevo (reemplaza `azureml/scripts/desplegar_config.sh` del plan original) |
| `docs/microproyecto3/PLAN_INFRA.md`, `ENTREGA_EQUIPO.md`, `PROMPTS_INFRA.md` | Nuevo |
| `docs/microproyecto3/PLAN_MP3.md` | Fases 7 y 8 marcadas como reemplazadas por este plan; fila del disco corregida (H17) |
| `docs/microproyecto3/REGLAS_AGENTE.md` | Sección de Terraform, alcance de infraestructura, regla del disco corregida |
| `docs/microproyecto3/PROGRESO.md` | Tickets I0–I8, decisiones I-D1 a I-D8 y hallazgo H17 |

## 11. Lista de verificación

- [ ] I0: clave real de Groq, corrida `limite=5` en verde y `sirena-extractor:1` registrado
- [ ] I1: Terraform escrito, `fmt` y `validate` en verde, nada sensible en `git status`
- [ ] I2: `telegram-bot-token` en el Key Vault
- [ ] I3: `plan` con 0 cambios y 0 destrucciones sobre lo existente; `apply`; outputs guardados
- [ ] I4: 7 contenedores arriba y 5 `/health` en verde
- [ ] I5: la VM usa el modelo del registro
- [ ] I6: Telegram → tablero, `POST /mensajes` → 202, acceso bloqueado desde una IP no autorizada
- [ ] I7: `ENTREGA_EQUIPO.md` completo y enviado; IP del equipo autorizadas
- [ ] I8: VM apagada al terminar cada sesión; limpieza final cuando Juan lo decida
