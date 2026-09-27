# Reglas para el agente — Microproyecto 3 (SIRENA en Azure ML)

Estas reglas aplican a cualquier agente (opencode u otro) que trabaje en el Microproyecto 3. Se suman a `AGENTS.md` de la raíz; si chocan, gana este archivo solo en lo que toca a Azure y al microproyecto.

## Fuente de verdad

- El plan es `docs/microproyecto3/PLAN_MP3.md`. No se inventan componentes, nombres ni pasos que no estén ahí.
- Nombres fijos: grupo `rg-sirena-mp3`, workspace `mlw-sirena`, clúster `cpu-sirena`, VM `vm-sirena`, Data asset `gold_v1`, Environment `sirena-eval`, pipeline `sirena-eval`, experimento `sirena-evaluacion`, modelo `sirena-extractor`, rama `feature/azureml-pipeline`.
- El avance se lleva en `docs/microproyecto3/PROGRESO.md`: una línea por ticket con estado (pendiente, en curso, hecho, bloqueado), fecha y evidencia (commit, id de job, salida de comando). Se actualiza al terminar cada ticket.
- Si el plan tiene un error o algo no funciona como dice, se anota en `PROGRESO.md` con la evidencia y se propone el cambio; no se corrige el plan en silencio.
- Las "Preguntas abiertas" del plan las decide el humano. Si un paso depende de una, el agente se detiene y pregunta.

## Azure: puertas de confirmación (obligatorias)

La suscripción es Azure for Students: crédito limitado, 3 IP públicas, regiones restringidas y poca cuota.

- **Permitido sin preguntar:** comandos de solo lectura (`az ... list`, `az ... show`, `az vm list-usage`, `az ml compute list-usage`, `az policy assignment show`, consultas del MCP de Azure que solo leen).
- **Requiere confirmación explícita del humano, una por comando o por bloque:** todo lo que crea, modifica, inicia, borra o cuesta dinero (`create`, `update`, `set`, `delete`, `start`, `deallocate`, `role assignment`, `keyvault secret set`, `az ml job create`). Antes de ejecutarlo, mostrar el comando exacto, qué recurso toca y el costo aproximado según el plan.
- **Las asignaciones de rol son una categoría aparte:** `az role assignment create` no crea ni factura un recurso, pero **cambia los permisos** de una identidad sobre un alcance. Siempre requieren confirmación explícita, aunque el recurso de destino ya exista y aunque el alcance esté acotado a `rg-sirena-mp3`. Antes de ejecutarla hay que mostrar el `--assignee`, el `--role` y el `--scope` exactos, y verificar después con `az role assignment list --scope <id> --query "[].{principal:principalName, rol:roleDefinitionName}" -o table` que el alcance es el esperado y no un nivel superior.
- Nunca borrar el grupo de recursos ni recursos existentes sin que el humano lo pida con esas palabras.
- Nunca crear recursos fuera de las regiones permitidas por la política (Fase 0 del plan) ni fuera de `rg-sirena-mp3`.
- Nunca subir `max-instances` del clúster por encima de 2 ni crear endpoints en línea (descartados en el plan).
- Ante `OutOfQuota`, `SkuNotAvailable` o `RequestDisallowedByPolicy`: detenerse, reportar y proponer la alternativa de la tabla de Riesgos. No probar tamaños o regiones al azar.

## Secretos

- `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN` y cualquier credencial nunca se escriben en archivos versionados, en YAML de Azure ML, en logs ni en la salida del chat.
- Los valores los escribe el humano (en `.env` local, en Key Vault o en el `.env` de la VM). El agente usa marcadores como `<GROQ_API_KEY>`.
- Verificar antes de cada commit que `.env` no esté en el índice.

## Código y repositorio

- Se trabaja en `feature/azureml-pipeline`. Nunca push directo a `main` ni a `develop`; la integración va por PR con la plantilla del repo.
- Gestor de paquetes: `uv`, como dice `AGENTS.md`. Única excepción: el `pip install` dentro de `azureml/env/Dockerfile`, que corre en la imagen de Azure ML y no en el workspace de uv.
- Alcance: solo los archivos de la tabla "Cambios que hay que hacer en el repositorio" del plan. No se toca la lógica de BFF, CRUD, Process, Geo, Frontend ni del servicio Inference. Excepción acotada y ya decidida: el ajuste a `registro.py` para no llamar `mlflow.set_experiment` cuando exista `MLFLOW_RUN_ID` se hace en la etapa A con su prueba, porque la Fase 6 lo va a necesitar sí o sí (decisión D2 en `PROGRESO.md`).
- Todo script nuevo en `azureml/src/` lleva docstrings estilo Google y pruebas en `tests/azureml/` con patrón AAA.
- Antes de cada commit: `make lint`, `make format-check` y `make test` en verde. Un ticket no se marca como hecho con pruebas fallando.
- Commits pequeños, uno por ticket, con mensaje que diga qué y por qué.

## Edición de archivos

Estas reglas existen porque un `Set-Content` de PowerShell 5.1 dejó un archivo del repo con todos los acentos convertidos en mojibake (`Sesión` → `SesiÃ³n`), 142 líneas modificadas y un BOM, en un cambio que debería haber tocado tres líneas. Se recuperó con `git checkout` y se rehízo. Cada sesión arranca en frío, así que la regla queda escrita acá y no en la memoria de una conversación.

- **Todo archivo de texto del repo se edita con la herramienta de edición, nunca con la shell.** Está prohibido `Set-Content`, `Add-Content`, `Out-File`, `echo >>`, `>>` y cualquier redirección de PowerShell o bash sobre un archivo del repo, incluso para un reemplazo puntual de una línea.
- La razón es técnica, no de estilo: PowerShell 5.1 lee y escribe con la codificación por defecto del sistema, no con UTF-8. Sobre un archivo con acentos eso no agrega caracteres: los destroza.
- **Todo archivo de texto es UTF-8 sin BOM.**
- Si un `git diff --stat` crece mucho más que el cambio pedido, **algo está mal**: es casi siempre BOM o fines de línea. Revertir con `git checkout -- <archivo>` y rehacer con la herramienta de edición. No intentar reparar el archivo a mano.
- Comprobación rápida tras editar texto con acentos, antes de commitear: los primeros bytes deben ser los del primer carácter del archivo, y el archivo no debe contener `Ã` ni `â€`.

## Comandos verificados en este entorno

Descubiertos a pulso en esta máquina, con los que respondieron y los que no. La memoria de una conversación no sobrevive entre sesiones, así que lo que costó tiempo queda escrito acá. Un comando que se cuelga no es un detalle: hace perder minutos de timeout y, peor, invita a concluir sin dato.

- **`az vm list-skus` se cuelga. No usarlo.** Probado con `--all` y con `--size Standard_DS2_v2` y `--size Standard_B2s_v2`: más de 120 s sin respuesta, y con `--all` pasó de cinco minutos. Se corta con Ctrl+C.
  - **Para cuota por familia:** `az vm list-usage --location <region> --query "[?contains(name.value, 'PREFIJO')].{familia:name.value, limite:limit, enUso:currentValue}" -o tsv | Sort-Object`. Responde en segundos. Filtrar por prefijo devuelve **todas** las familias que matchean, que es justo lo que hace visible un nombre mal escrito.
  - **Para el catálogo y el campo `family`:** `az rest --method get --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Compute/skus?api-version=2021-07-01`$filter=location%20eq%20'<region>'"`. Devuelve una fila por juego de capabilities, así que hay que acotar con `starts_with(name, 'Standard_B2s')` en el `--query`.
  - `quota_usage_check` del MCP de Azure responde al instante para cuota **por SKU**, pero su tabla no lista todos los SKUs: omitió `Standard_DS2_v2`, que sí existe y sí tiene cuota (H15). **La ausencia en esa tabla no prueba falta de cuota.**

- **El nombre de la familia de un SKU se lee SIEMPRE del catálogo, nunca de un documento, un plan ni de la memoria.** `Standard_D2as_v4` factura en `standardDASv4Family`; `Standard_Da_v4` factura en `standardDAv4Family`. Una letra de diferencia y son dos familias con cuotas distintas. Copiar el nombre de la familia desde el plan que se pretende verificar es como consultar la fuente equivocada: devuelve un 0 muy convincente (H14).

- **En `az vm list-usage`, `name` es un objeto y `limit` es un string.** Filtrar por `name.value`, no por `name`. Y `limit` / `currentValue` son cadenas planas: usar `limit.localValue` devuelve `None`, que se lee como "sin cuota" cuando la cuota es real. Esto ya costó una tabla entera de ceros falsos.

- **`az policy assignment show`: el parámetro de la política de regiones es `listOfAllowedLocations`, no `listOfAllowedRegions`.** Con el nombre equivocado la consulta devuelve `null`, que se lee como "sin restricción" si no se mira el JSON crudo.

- **La API de precios devuelve un precio por MEDIDOR, no por SKU, y un SKU de VM tiene varios medidores legítimos.** `Standard_B2s_v2` en `westus` devuelve ocho filas. La única correcta es la de `productName` con el nombre de la **serie** (`Virtual Machines Bsv2 Series`), sin `Windows`, sin `Low Priority`, sin `Spot` y sin `Cloud Services`. Tomar la primera fila, o la más barata, da un número plausible y equivocado: la más barata es 0,0198 (Low Priority) contra 0,0992 de la real. Mismo cuidado con `isPrimaryMeterRegion`.
- **Los discos no tienen un precio único: tienen bandas, y el tamaño decide.** `Standard SSD` va de `E1` a `E80`. Un disco de 32 GB es `E1 LRS` a **0,30/mes**; el 2,4/mes es `E4 LRS`, la banda de hasta 256 GiB. Cotizar "Standard SSD 32 GB" como un solo precio es como consultar la fuente equivocada (H16).
- **El MCP de Azure no sirve para esto.** `pricing_get` con `service: "Virtual Machines Disks"` o `"Container Registry"` devuelve `items: []`, y exige `--sku` con nombres de SKU que no existen para discos ni registries. Para la tabla de costos hay que ir a `prices.azure.com` crudo:
  ```bash
  # precio de un medidor, filtrando por región y servicio
  az rest --method get --url "https://prices.azure.com/api/retail/prices?currencyCode='USD'&`$filter=armRegionName%20eq%20'westus'%20and%20serviceName%20eq%20'Storage'%20and%20contains(meterName,'Standard%20SSD')"
  ```
  `serviceName` para discos y registry es `Storage` y `Container Registry`. Para IP pública es `Virtual Network`. Con `productName` el MCP **rechaza** el argumento: no existe.
- **Un recurso que existe factura mientras existe, no mientras corre.** La IP pública estática y el disco se cobran aunque la VM esté apagada. Calcular el costo del demo con las horas de cómputo de la VM subestima esas dos líneas.

- **Un Key Vault con RBAC (`enableRbacAuthorization: true`) necesita roles de plano de datos para operaciones de secretos.** Owner de la suscripción **no da acceso al plano de datos**: Owner no incluye `dataActions`, y escribir un secreto es una `dataAction`. El comando `az keyvault set-policy` no funciona con RBAC. Los roles correctos son:
  - **`Key Vault Secrets User`** (lectura de secretos) para la identidad del clúster.
  - **`Key Vault Secrets Officer`** (escritura de secretos) para el usuario que necesita `az keyvault secret set`.
  Se asignan con `az role assignment create --assignee-object-id <id> --assignee-principal-type <tipo> --role "Key Vault ..." --scope <id del Key Vault>`.
- **Las asignaciones de rol a identidades administradas van con `--assignee-object-id` + `--assignee-principal-type ServicePrincipal`.** Con `--assignee` a secas, la CLI intenta resolver el id contra Graph y puede fallar o colgarse sin motivo claro. Las asignaciones tardan unos minutos en propagarse: si da `Forbidden` justo después de asignar, espera y reintenta antes de cambiar nada.

## Entorno del humano

- El equipo trabaja en Windows. Los bloques bash del plan se corren en Git Bash, WSL o Azure Cloud Shell; si el agente propone un comando para PowerShell, lo traduce (variables, continuación de línea con acento grave, comillas).
- La Azure CLI local ya está autenticada contra "Azure for Students". El MCP de Azure está disponible para consultas.
- Para ejecutar cosas dentro de la VM sin sesión SSH interactiva, usar `az vm run-command invoke --command-id RunShellScript` (también requiere confirmación, porque cambia la VM).

## Cómo reportar

- Al terminar cada ticket: qué se hizo, archivos tocados, evidencia (salida resumida de pruebas o de Azure) y siguiente paso.
- Si algo falla dos veces con el mismo error, detenerse y pedir indicaciones en vez de seguir probando.
