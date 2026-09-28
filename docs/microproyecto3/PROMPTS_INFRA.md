# Prompts para opencode — Infraestructura (Juan)

Cinco sesiones, en orden, más prompts cortos de operación. Cada sesión arranca en frío y lee los archivos, así que puede ser una sesión nueva de opencode o la misma si el contexto no está pesado. Al cerrar cada sesión, pedir la skill `handoff` y guardar el resumen en `docs/microproyecto3/`.

## Preparación (una vez, a mano)

1. En la rama `feature/azureml-pipeline`, copiar en `docs/microproyecto3/`: `PLAN_INFRA.md`, `ENTREGA_EQUIPO.md`, `PROMPTS_INFRA.md` y **reemplazar** `REGLAS_AGENTE.md` por la versión nueva.
2. `opencode.json` sigue igual (carga `REGLAS_AGENTE.md`).
3. Commit: `docs(mp3): plan de infraestructura con Terraform y reglas actualizadas`.

---

## Sesión 1 — Alinear la documentación y cerrar B7 (I0)

Antes de pegarlo: escribe la clave real de Groq en el Key Vault, en tu terminal (reemplaza todo lo que está entre `< >`, incluidos los signos):

```text
az keyvault secret set --vault-name mlwsirenkeyvault18607254 --name groq-api-key --value "<pega aquí tu clave gsk_...>"
```

```text
Cambió el alcance. El equipo se dividió el trabajo y yo soy el responsable de la infraestructura en Azure. Lee, en este orden: docs/microproyecto3/REGLAS_AGENTE.md (versión nueva), docs/microproyecto3/PLAN_INFRA.md, docs/microproyecto3/PROGRESO.md y el handoff de B7.

Parte 1, documentación (sin tocar Azure):
1. En PLAN_MP3.md, al inicio de las Fases 7 y 8, agrega una nota: "Reemplazada por PLAN_INFRA.md (VM con Terraform, tickets I1 a I6)". No borres su contenido.
2. En PLAN_MP3.md, corrige la fila del disco en la tabla de costos: Standard SSD 32 GiB es E4 LRS a 2,40/mes en westus, no E1 a 0,30. Recalcula la columna del demo (1,12) y la de 24/7 (2,40) y los totales.
3. En PROGRESO.md registra H17: H16 estaba mal. E1 es de 4 GiB, E4 es de 32 GiB y 256 GiB es E15; el precio original (2,4/mes) era el correcto. Verificado en prices.azure.com (skuName eq 'E4 LRS', westus: 2,40) y en la doc de tipos de disco. Anota también que yo aprobé la corrección de H16 sin verificarla.
4. En PROGRESO.md agrega las decisiones I-D1 a I-D8 y los tickets I0 a I8 de PLAN_INFRA.md, todos pendientes. Marca D1–D5 de la Etapa D (VM manual) como reemplazados por I1–I6.
5. Commit de documentación.

Parte 2, I0:
1. Ya escribí la clave real. Verifica el formato SIN imprimir el valor:
   az keyvault secret show --vault-name mlwsirenkeyvault18607254 --name groq-api-key --query "starts_with(value, 'gsk_')" -o tsv
   Si no devuelve true, detente y avísame.
2. Muéstrame el comando para relanzar la corrida corta con limite=5 y los mismos inputs de la vez anterior, y espera mi confirmación.
3. Sigue el job paso por paso y repórtame cada paso al terminar. Al final: métricas de los dos modelos, decisión de comparar y versión de sirena-extractor con sus tags.
```

## Sesión 2 — Código de Terraform (I1, sin tocar Azure)

```text
Lee docs/microproyecto3/REGLAS_AGENTE.md (sección Terraform) y docs/microproyecto3/PLAN_INFRA.md (secciones 3, 4, 5 y 10). Trabaja el ticket I1: escribir infra/terraform/ e infra/scripts/. En esta sesión NO corras plan ni apply, ni ningún comando que escriba en Azure.

1. Verifica si Terraform está instalado (terraform version). Si no, dame el comando winget para instalarlo y espera.
2. Escribe los archivos de la sección 5 exactamente con los nombres, recursos y atributos de la tabla. Puntos que no se negocian:
   - Lo existente (grupo, workspace, Key Vault) va como bloques data, nunca como resource ni import.
   - azurerm ~> 4.0, subscription_id por variable, resource_provider_registrations = "none".
   - Ninguna variable con un identificador de la suscripción como default.
   - NSG: 22 solo para ips_admin; 8000 y 8501 para concat(ips_admin, ips_equipo). Nada más de entrada.
   - OS disk StandardSSD_LRS de 32 GiB; identidad SystemAssigned; auto-apagado 23:00 "SA Pacific Standard Time"; lifecycle { ignore_changes = [custom_data] } en la VM, para que un cambio de cloud-init nunca la recree.
   - Dos azurerm_role_assignment para la identidad de la VM: Key Vault Secrets User sobre el Key Vault y AzureML Data Scientist sobre el workspace, con principal_type = "ServicePrincipal".
   - cloud-init.yaml.tftpl instala Docker con el plugin de Compose, Azure CLI con la extensión ml y clona repo_url en repo_branch. Sin secretos.
   - .gitignore de infra/terraform/ según la sección 5; .terraform.lock.hcl sí se versiona.
3. Scripts en infra/scripts/:
   - cargar_secretos.sh: az login --identity; lee groq-api-key y telegram-bot-token del Key Vault a variables; escribe .env en la raíz del repo clonado con GROQ_API_KEY, TELEGRAM_BOT_TOKEN e INFERENCE_MODELO (default openai/gpt-oss-20b si no existe); chmod 600. Nunca hace echo de un valor, no usa set -x, y falla con mensaje claro si algún secreto no existe o si groq-api-key no empieza por gsk_.
   - desplegar_config.sh: la versión de la Fase 8 de PLAN_MP3.md, adaptada a las rutas de la VM (az login --identity, última versión de sirena-extractor, tags.modelo, reemplaza INFERENCE_MODELO en .env, docker compose up -d inference).
   - salud.sh: curl a /health de bff 8000, crud 8001, process 8002, inference 8003, geo 8004 dentro de la VM; sale con error si alguno falla.
4. Puertas: terraform init, terraform fmt -check -recursive, terraform validate, bash -n en los tres scripts. Confirma con git status que no aparece ningún tfstate ni terraform.tfvars.
5. Crea terraform.tfvars.example con marcadores entre < >. Después dime exactamente qué valores tengo que poner en mi terraform.tfvars (que NO se versiona) y cómo sacar cada uno: subscription_id, ruta de mi llave pública SSH (si no tengo, el comando ssh-keygen para Windows), mi IP pública.
6. Commit por partes: terraform, scripts, docs. Actualiza PROGRESO.md.
```

## Sesión 3 — Secreto de Telegram, plan y aplicación (I2, I3)

Antes de pegarlo: crea tu `infra/terraform/terraform.tfvars` con los valores que te pidió la sesión 2, y escribe el token del bot en el Key Vault:

```text
az keyvault secret set --vault-name mlwsirenkeyvault18607254 --name telegram-bot-token --value "<pega aquí el token del bot>"
```

```text
Lee docs/microproyecto3/REGLAS_AGENTE.md y docs/microproyecto3/PLAN_INFRA.md (tickets I2 e I3). Ya creé terraform.tfvars y escribí telegram-bot-token en el Key Vault.

1. Verifica, sin imprimir valores, que telegram-bot-token existe y está habilitado, y que Microsoft.Compute y Microsoft.Network están Registered.
2. Corre terraform plan -out tfplan y muéstrame el resumen: lista de recursos a crear y la línea Plan: X to add, Y to change, Z to destroy. Si Y o Z no son 0, detente y explícame recurso por recurso.
3. Espera mi confirmación y corre terraform apply tfplan. Si falla con AADSTS50076, dime qué az login tengo que correr (el mismo que funcionó en B2) y espera.
4. Guarda los outputs y verifica según I3: estado de la VM, los dos roles con sus alcances exactos (az role assignment list --assignee <vm_principal_id> --all -o table), que puedo conectarme por SSH, y cloud-init status --wait en done (con az vm run-command invoke, con mi confirmación).
5. Actualiza PROGRESO.md con los outputs (sin datos sensibles) y haz commit. Recuérdame apagar la VM si no seguimos hoy.
```

## Sesión 4 — Desplegar los contenedores y cerrar el ciclo (I4, I5)

```text
Lee docs/microproyecto3/REGLAS_AGENTE.md y docs/microproyecto3/PLAN_INFRA.md (I4 e I5). La VM está creada. Si está apagada, pídeme confirmación para az vm start.

Todo lo que se ejecute dentro de la VM va con az vm run-command invoke --command-id RunShellScript, en bloques pequeños y con mi confirmación, o me das los comandos para correrlos yo por SSH si son largos o interactivos.

1. cargar_secretos.sh. Verifica que .env existe con permisos 600 y que tiene las tres claves, mostrando solo los nombres de las variables (cut -d= -f1), nunca los valores.
2. docker compose build --parallel 1. Si falla por memoria, detente y propón la escalera de PLAN_INFRA.md (riesgos).
3. docker compose up -d bff telegram-source crud process inference geo frontend (sin mlflow).
4. salud.sh y docker compose ps. Los 5 /health en ok y ningún contenedor reiniciándose.
5. I5: desplegar_config.sh y confirma con docker compose exec inference env | grep INFERENCE_MODELO que quedó el modelo registrado en I0.
6. Confirma que el tablero abre en http://<IP>:8501 desde mi IP.
7. PROGRESO.md, commit, y recuérdame apagar la VM.
```

## Sesión 5 — Prueba de humo y entrega al equipo (I6, I7)

```text
Lee docs/microproyecto3/PLAN_INFRA.md (I6 e I7) y docs/microproyecto3/ENTREGA_EQUIPO.md.

1. I6: guíame para la prueba de humo. Yo envío un mensaje al bot de Telegram; tú verificas que aparece en GET /reportes con tipo de evento y comuna. Después haz un POST /mensajes con un id_externo nuevo y el cuerpo de ENTREGA_EQUIPO.md, y confirma 202. Por último dime cómo verificar desde datos móviles que 8000 y 8501 no responden.
2. I7: completa ENTREGA_EQUIPO.md con los valores reales: IP, URLs, fecha, rama y commit desplegados, modelo activo. Sin subscription_id, sin claves, sin la IP de nadie en la lista de autorizados (solo nombres).
3. Cuando te pase las IP de mis compañeros, agrégalas a ips_equipo en terraform.tfvars y pasa por plan y apply con mi confirmación. El plan solo puede cambiar el NSG.
4. PROGRESO.md, commit, push. Dame un mensaje corto listo para mandarle al equipo con el enlace a ENTREGA_EQUIPO.md.
```

---

## Operación (prompts cortos)

**Encender para una sesión de pruebas:**

```text
Pídeme confirmación y enciende vm-sirena. Cuando esté arriba, corre salud.sh con run-command y dime si los 5 servicios están en ok. Si alguno no, docker compose up -d y repite.
```

**Ventana de prueba de carga:**

```text
El equipo va a hacer una prueba de carga sostenida. Cambia vm_size a Standard_D2as_v4 en terraform.tfvars, muéstrame el plan (solo debe cambiar el tamaño de la VM) y aplica con mi confirmación. Después salud.sh. Al terminar la prueba te aviso para volver a Standard_B2s de la misma forma.
```

**Autorizar una IP nueva:**

```text
Agrega <IP> a ips_equipo en terraform.tfvars para <nombre>. Plan (solo debe cambiar el NSG), mi confirmación, apply. Actualiza la lista de nombres autorizados en ENTREGA_EQUIPO.md.
```

**Apagar:**

```text
Pídeme confirmación y desasigna vm-sirena (az vm deallocate). Confirma que quedó en VM deallocated.
```

**Desplegar una versión nueva del código:**

```text
Mis compañeros subieron cambios a <rama>. En la VM: git fetch, git checkout <rama> si es otra, git pull, docker compose build --parallel 1, docker compose up -d, salud.sh. No toques repo_branch en Terraform: solo aplica al crear la VM, y la VM ignora cambios de custom_data para no recrearse y perder la base SQLite.
```
