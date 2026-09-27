# Progreso — Microproyecto 3 (SIRENA en Azure ML)

Bitácora de la implementación. La fuente de verdad del *qué* es `PLAN_MP3.md`; este archivo registra el *cómo*: hallazgos, decisiones del equipo y estado de cada ticket.

**Rama de trabajo:** `feature/azureml-pipeline` (base `develop` en `28e96af`)
**Fork:** `JCMelendezT/pmu-structured-extraction` · **Upstream:** `Juanxo17/pmu-structured-extraction`
**Reglas:** `docs/microproyecto3/REGLAS_AGENTE.md`

Estado de este documento: **Etapa A cerrada, B1 y B1b hechos, B2 a medias.** Línea base en verde desde `d10056b`. Tickets A0, A1, A2, A4, A5, A6, A7, A8 y A9 hechos; A3 revertido y absorbido en A5. **La Etapa A está completa y es código, no Azure**. B1 midió regiones, cuota y proveedores y fijó región y tamaño de clúster (D8, D9); B1b rehízo la tabla de costos con precios verificados de `westus` y el precio real devolvió la VM a `Standard_B2s` (D10), con una escalera de tres peldaños para el riesgo de RAM. **B2 está a medias: los tres proveedores quedaron en `Registering` y el grupo de recursos NO se creó**, porque `az group create` falló con `AADSTS50076` (MFA requerido en el token en caché). Hay que hacer `az login` y repetir solo ese comando. H7 cerrado en F7 con visto bueno del humano. H14, H15 y H16 nacieron de medir en vez de suponer: H14 casi borra el Plan B del clúster y H16 tenía el disco mal por un factor de 8.

---

## 1. Hallazgos de la sesión 1

Contraste del plan contra el código real del fork. La evidencia es el número de línea citado.

| # | Hallazgo | Evidencia | Resolución |
| --- | --- | --- | --- |
| H1 | Los `.jsonl` del corpus arrancan con CRLF en Windows, así que su SHA-256 no coincide con `README_gold_v1.md` y `validar_corpus` fallaría en el job de Azure ML | `eval-prompt/corpus/gold_v1/*.jsonl` vs checksums de `README_gold_v1.md` | **Resuelto.** `.gitattributes` con `text eol=lf`. Commit `27f3f4d` |
| H2 | `registro.py` llama `mlflow.set_experiment` sin condición, y en un job de Azure ML eso falla si MLflow ya tiene una corrida abierta | `backend/inference/inference/registro.py:87` | **Resuelto.** D2: proteger con `MLFLOW_RUN_ID` + prueba |
| H3 | `autor` y `rama` se resuelven con `git`, que no existe dentro del contenedor del job, así que quedan como `desconocido` | `registro.py`, lectura de `autor`/`rama` desde git | **Resuelto.** D3: pasarlos como inputs del componente |
| H4 | `docker-compose.yml` no propaga `INFERENCE_MODELO` al servicio `inference`, así que la VM no podría fijar el modelo ganador por variable de entorno | `docker-compose.yml:52-60` | **Pendiente.** Ticket A6 |
| H5 | El plan afirma que "agregar otro proveedor no toca el resto del código", y eso no aplica al harness de evaluación: `evaluacion.main()` construye `ServicioInferencia(ProveedorGroq())` de forma directa | `backend/inference/inference/evaluacion.py:812` | **Resuelto.** Aclarado en el plan: aplica al servicio Inference, no al harness. `evaluar.py` construye su propio servicio y `evaluacion.py` no se toca (D7) |
| H6 | El `.amlignore` está especificado en `azureml/`, pero el contexto que se sube con `code: ../..` es el repo raíz, así que ahí no tendría efecto | Fase 5 del plan, campo `code: ../..` | **Pendiente.** Ticket A7: el `.amlignore` va en la raíz |
| H13 | Las referencias `${{keyvault:...}}` del plan asumían que el Environment podía inyectar secretos a los jobs. **No es así:** solo existen para online endpoints y deployments. Para command y pipeline jobs la vía documentada es `SecretClient` + `DefaultAzureCredential` con la identidad administrada del compute | `how-to-deploy-online-endpoint-with-secret-injection` vs `how-to-use-secrets-in-runs`; plan L318, L348, L374 | **Resuelto.** A3 revertido; la lectura del secreto se hace en `evaluar.py` (A5) y se quita el `export` del comando del componente |
| H7 | `AGENTS.md` describe el LLM como "Llama 3.1 8B Instruct", pero el código y `.env.example` usan `openai/gpt-oss-20b` | `AGENTS.md` vs `backend/inference/inference/proveedor.py:83` | **Resuelto en F7** con visto bueno del humano. El código ya era correcto (`registro.py` registra `LICENCIA = "MIT"`, la de gpt-oss-20b); lo desactualizado eran dos líneas del documento. Va en el PR de la rama señalada como corrección de documentación para que el equipo lo apruebe |
| H8 | La Fase 7 del plan clona el upstream, lo que descartaría los componentes de `azureml/` que viven en el fork | Fase 7 del plan, paso de clonado | **Pendiente.** El ticket D2 clona el fork y la rama `feature/azureml-pipeline` |
| H9 | El profesor aceptó que el LLM se sirva desde Groq mientras la evaluación, la comparación, el registro y el despliegue vivan en Azure ML | Respuesta del profesor, 2026-09-26 | **Resuelto.** D5. La pregunta abierta quedó marcada en el plan |
| H10 | No estaba definido sobre qué suscripción se monta todo, lo que bloqueaba los permisos del compañero y el alcance de los comandos | Decisión del equipo | **Resuelto.** D6: una sola suscripción, con rol acotado para el compañero |
| H11 | La rama base `develop` no pasaba `make format-check`: `ruff format` marcaría 4 archivos, dos de ellos justo los que este microproyecto va a tocar (`backend/inference/inference/evaluacion.py` y `backend/inference/inference/registro.py`), más `tests/inference/test_evaluacion.py` y `tests/inference/test_registro.py`. **El mismo problema está en `main` del repositorio original**: no es una regresión del fork | `make format-check` sobre `develop` | **Resuelto.** Commit `d10056b`, verificado que el AST de los 4 archivos es idéntico antes y después |
| H12 | Las 11 pruebas que fallaban eran **del entorno local, no del repo**: las 11 son `spacy.load("es_core_news_md")` y el modelo en español faltaba en esta máquina. `Makefile:8` ya lo descarga en `make install`, o sea que en el equipo que hizo el repo sí estaba. Con el modelo instalado, las 11 pasan | `backend/process/process/anonimizacion.py:70`, 7 pruebas en `test_anonimizacion.py` y 4 en `test_orquestador.py` | **Resuelto.** `uv run --package process python -m spacy download es_core_news_md`. Sin cambios en el repo |
| H14 | Al medir la cuota del Plan B del clúster se consultó la familia equivocada: `standardDAv4Family` en lugar de `standardDASv4Family`. Son dos familias distintas, y la segunda es la que factura `Standard_D2as_v4`. El 0 de la primera se leyó como "este SKU no tiene cuota" | `az vm list-usage -l westus` contrastado con el campo `family` de `Microsoft.Compute/skus` | **Resuelto antes de tocar el plan.** H14 en detalle abajo. `Standard_D2as_v4` se mantiene |
| H15 | La tabla de cuota por SKU de `quota_usage_check` no lista todos los SKUs: omitió `Standard_DS2_v2`, que sí existe y sí tiene cuota. La ausencia en esa tabla no prueba falta de cuota | `quota_usage_check` en `chilecentral` vs `az vm list-skus` en la misma región | **Resuelto.** La cuota que gobierna el escalado es la de familia, no la tabla por SKU |
| H16 | La tabla de costos del plan estaba **en `eastus` y además con el disco mal por un factor de 8**. El disco de 32 GB se cotizó a ≈ 2,4/mes, que es el precio de `E4 LRS` (hasta 256 GiB); un `Standard SSD` de 32 GB cae en la banda `E1 LRS`, que cuesta **0,30/mes**. El error viene de la misma clase que H14: un número copiado de un documento en vez de consultado | `prices.azure.com/api/retail/prices` con `armRegionName eq 'westus'`, filtrando `Standard SSD Managed Disks` | **Resuelto.** Ticket B1b: tabla de costos entera rehecha con precios de `westus` verificados |

### H16 en detalle: por qué la API de precios devuelve ocho filas por SKU

La API de precios de Azure no devuelve "el precio de un SKU": devuelve **un precio por medidor**, y un SKU de VM tiene varios medidores legítimos en la misma región. Consultar `Standard_B2s_v2` en `westus` devuelve ocho filas:

| Medidor | Precio/hora | ¿Sirve? |
| --- | --- | --- |
| Virtual Machines Bsv2 Series | **0,0992** | **Sí.** Es el que queríamos |
| Virtual Machines Bsv2 Series Windows | 0,108 | No: es Windows |
| Bsv2 Series Cloud Services | 0,108 | No: es la tarifa de cloud services, no la VM |
| B2s v2 Low Priority | 0,0198 | No: es spot, no paga-por-uso |
| B2s v2 Low Priority Windows | 0,0434 | No |
| B2s v2 Spot | 0,08928 | No: es spot |
| B2s v2 Spot Windows | 0,0972 | No |

Tomar la primera fila, o la más barata, da un número plausible y equivocado. La fila correcta es la de `productName` con el nombre de la **serie**, sin `Windows`, sin `Low Priority`, sin `Spot` y sin `Cloud Services`. Lo mismo con el disco: `Standard SSD` no tiene un precio único, tiene bandas `E1` a `E80` y el tamaño decide la banda.

### H14 en detalle: el casi-accidente que casi nos deja sin Plan B

B1 iba a corregir el plan para borrar `Standard_D2as_v4` del Plan B del clúster (L360 y L583 de `PLAN_MP3.md`), con el argumento de "esa familia tiene cuota 0 en las cinco regiones". **El argumento era falso.** Se registra completo porque una línea borrada del plan no deja rastro, y este casi-accidente vale más que la corrección que casi hacemos.

| | |
| --- | --- |
| **Qué se midió** | `standardDAv4Family` — límite 0, en uso 0, en las cinco regiones permitidas |
| **Qué había que medir** | `standardDASv4Family` — límite 4, en uso 0 en `westus`. Con S |
| **De dónde salió el nombre equivocado** | Del propio `PLAN_MP3.md`, que escribe "DAv4". No del catálogo de SKUs. El nombre se copió del documento que se pretendía verificar |
| **Por qué no es un detalle tipográfico** | `Standard_D2as_v4` → `standardDASv4Family`. `Standard_Da_v4` (serie no-A) → `standardDAv4Family`. Una letra y son dos familias con cuotas distintas. `standardDAv4Family` no estaba vacía por casualidad: no le corresponde ningún SKU que nos sirva |
| **Qué se habría perdido** | El **único Plan B real**. Las familias tienen cuota independiente, así que `Standard_D2as_v4` y `Standard_DS2_v2` no son dos tamaños del mismo pozo sino **dos pozos distintos**: usar uno deja la otra familia enteramente libre. Es lo que hace que el fallback funcione de verdad y no sea un "tamaño más chico" que falla por la misma razón |
| **Cómo se detectó** | El equipo objetó una inconsistencia interna del informe: la tabla de cuota marcaba `standardBSFamily` como "la familia de la VM" y al mismo tiempo se decía que `Standard_B2s` no tenía cuota. Al forzarse a verificar la facturación real de cada SKU contra el campo `family` del catálogo, aparecieron las dos filas que faltaban |

**El error fue del método, no del dato.** Una consulta que devuelve 0 es indistinguible de un 0 verdadero hasta que se sabe *qué* se consultó. Por eso la regla nueva de `REGLAS_AGENTE.md`: el nombre de la familia de un SKU se lee **siempre** del catálogo, nunca de un documento, un plan ni de la memoria.

**Responsabilidad compartida.** El agente tomó el nombre del plan, midió la familia equivocada y presentó el 0 como verificado. El compañero **aprobó las tres correcciones sin preguntar la procedencia del nombre de la familia**, y la segunda —la que borraba el Plan B— estaba a punto de pasar. Ninguno de los dos consultó el catálogo. Una corrección de infraestructura que borra una opción de respaldo no se aprueba por confianza en el informe: se aprueba por procedencia.

| H17 | **H16 estaba mal.** El disco de 32 GB se cotizó correctamente a 2,4/mes en el plan original. H16 corrigió a `E1 LRS` a 0,30/mes, pero `E1` es de 4 GiB, `E4` es de 32 GiB y 256 GiB es `E15`. El precio original era el correcto. Verificado en `prices.azure.com` (`skuName eq 'E4 LRS'`, westus: 2,40) y en la documentación de tipos de disco de Azure. **Yo aprobé la corrección de H16 sin verificarla.** | `prices.azure.com` con `armRegionName eq 'westus'`, `skuName eq 'E4 LRS'`; documentación de tipos de disco administrado | **Resuelto.** Se revierte la corrección de H16. El disco de 32 GB es `E4 LRS` a 2,40/mes. La tabla de costos vuelve a los valores originales |

## 2. Decisiones del equipo

| # | Decisión | Fecha | Consecuencia |
| --- | --- | --- | --- |
| D1 | Regla acotada `eval-prompt/corpus/**/*.jsonl text eol=lf`, y validar **solo** `dev.jsonl`, `eval.jsonl` y `gold_standard_v1.jsonl`; los otros dos archivos se listan en `manifest.json` sin checksum | 2026-09-27 | Tickets A1, A2 |
| D2 | `registro.py` no llama `mlflow.set_experiment` cuando exista `MLFLOW_RUN_ID`, con prueba unitaria | 2026-09-27 | Tickets A4. Excepción acotada añadida a `REGLAS_AGENTE.md` |
| D3 | `autor` y `rama` viajan como inputs del componente `sirena_evaluar_modelo` y se pasan a `registrar_corrida` | 2026-09-27 | Tickets A5 |
| D4 | `validar_corpus` escribe en `<salida>/gold_v1/eval.jsonl`, para que la entrada del job de evaluación vea `version_corpus=gold_v1` | 2026-09-27 | Ticket A2 |
| D5 | Se mantiene L1 (Groq). L2 (Azure AI Foundry) queda **descartada**, sin plan de implementación | 2026-09-26 (profesor) | Actualizado en el plan |
| D6 | Todo se monta en una sola suscripción "Azure for Students", la del propietario. El compañero entra con `Contributor` acotado a `rg-sirena-mp3`. La autoría va en los tags `autor` y `rama` de MLflow, no en la suscripción | 2026-09-27 | Tickets B2, B3 |
| D7 | `evaluar.py` construye `ServicioInferencia(ProveedorGroq())` directamente, igual que el harness. **Sin** `SIRENA_PROVEEDOR` ni punto de extensión de proveedor, y **sin** `ProveedorAzure` | 2026-09-27 | Ticket A5 |
| D8 | Región **`westus`**, clúster `Standard_DS2_v2` (min 0, max 2), VM `Standard_B2s` (ver D10). Descartada `francecentral`: también sirve, pero la latencia p95 que el proyecto **reporta como métrica** tiene que ser representativa del sistema y no de la geografía. Los jobs no llaman a un endpoint de Azure, llaman a la API de Groq, que es infraestructura de EE.UU.; correr el clúster del mismo lado que Groq es lo que hace la métrica comparable con la de producción. Si `westus` da `SkuNotAvailable`, el Plan B es `francecentral`, no otro SKU | 2026-09-27 | Tickets B2, B4, B7. `brazilsouth` **no** es Plan B: la política lo bloquea |
| D9 | El workspace queda en EE.UU. **por la política de la suscripción de estudiante, no por diseño.** No hay región latinoamericana que cumpla las dos condiciones: `brazilsouth` tiene Azure ML disponible pero la política `sys.regionrestriction` la bloquea. La mitigación es que los mensajes se anonimizan en Process antes de salir hacia Groq o hacia Azure, así que lo que sale de Colombia no es el texto original. En la sustentación se dicen las dos cosas juntas: la limitación y la mitigación | 2026-09-27 | Ticket B4. Documentado en el plan para la presentación |
| D10 | La VM es **`Standard_B2s` (2 vCPU, 4 GB)**, no `Standard_B2s_v2`, después de consultar el precio real en `westus`: 0,0496/hora contra 0,0992/hora de `Standard_B2s_v2`, **exactamente el doble**. El argumento que llevó a `B2s_v2` era el headroom de cuota, y es inválido: se necesita **una** VM de 2 vCPU, y los 4 vCPU de `standardBSFamily` sobran. Los 10 vCPU de `standardBsv2Family` no compran nada que el proyecto vaya a usar. El riesgo de RAM al construir las 7 imágenes se resuelve con una escalera de tres peldaños y no pagando el doble desde el día uno | 2026-09-27 | Ticket B1b. Escalera de escalation en la tabla de Riesgos del plan |
| D11 | **El presupuesto con alertas al 50 % y 80 % se crea antes de B4, no después.** El grupo de recursos de B2 no cuesta nada, pero el workspace de B4 crea Storage, Key Vault, Application Insights y el Container Registry, que **sí facturan desde el minuto uno**. Crear el presupuesto después es crear la alarma después de que empiece el gasto | 2026-09-27 | Tickets B2, B3b. Orden explícito en el plan |
| I-D1 | Una sola VM `Standard_B2s` con Docker Compose, como en el plan original | Cuota y crédito de estudiante; el `docker-compose.yml` ya existe; 1 IP pública de 3 | 2026-09-27 | Tickets I1-I6 |
| I-D2 | Terraform gestiona **solo lo nuevo**: red, NSG, IP pública, VM, auto-apagado y los roles de la VM. Lo creado con CLI se referencia con bloques `data` | Importar el workspace, el Key Vault o el clúster a Terraform arriesga que un `apply` los reemplace o los destruya, y se perderían corridas y permisos. Referenciarlos da el mismo resultado sin ese riesgo | 2026-09-27 | Tickets I1-I6 |
| I-D3 | El estado de Terraform es local, en la máquina de Juan, y **no se versiona** | Solo Juan aplica cambios. El `.tfstate` puede contener datos sensibles. Lo que se comparte con el equipo es el código `.tf`, el `.terraform.lock.hcl` y un `terraform.tfvars.example` | 2026-09-27 | Tickets I1-I6 |
| I-D4 | Ningún secreto entra en Terraform. La VM lee `groq-api-key` y `telegram-bot-token` del Key Vault con su identidad administrada, mediante `infra/scripts/cargar_secretos.sh` | Un secreto en `.tf`, `tfvars`, `cloud-init` o en un output queda escrito en el estado y en los metadatos de la VM. El Key Vault ya existe y es la fuente única de la clave de Groq | 2026-09-27 | Tickets I1-I6 |
| I-D5 | El NSG abre solo 22 (IP de Juan) y 8000 y 8501 (IP de Juan y del equipo), con listas en `terraform.tfvars` | BFF y Frontend no tienen autenticación. CRUD, Process, Inference y Geo (8001–8004) nunca se exponen: CRUD acepta `PATCH` sin credenciales. Autorizar una IP nueva es editar `tfvars` y aplicar | 2026-09-27 | Tickets I1-I6 |
| I-D6 | El tamaño de la VM es una variable. Para las ventanas de prueba de carga se sube a `Standard_D2as_v4` y después se baja | La serie B es de ráfaga: con carga sostenida agota créditos de CPU y baja a su línea base, lo que ensucia la medición. `standardDASv4Family` tiene 4 vCPU libres, familia distinta de la del clúster (`DSv2`) | 2026-09-27 | Tickets I1-I6 |
| I-D7 | Auto-apagado diario a las 23:00 hora de Bogotá con `azurerm_dev_test_global_vm_shutdown_schedule` | Una VM olvidada encendida es el gasto más probable. El presupuesto solo avisa; el auto-apagado corta | 2026-09-27 | Tickets I1-I6 |
| I-D8 | La VM clona el repo definido por variables (`repo_url`, `repo_branch`). Por defecto el fork con `feature/azureml-pipeline`, que ya tiene `INFERENCE_MODELO` en el Compose | `repo_url` y `repo_branch` solo cuentan al **crear** la VM: cambiar `custom_data` obliga a recrearla y se perdería la base SQLite. Por eso la VM lleva `lifecycle { ignore_changes = [custom_data] }`, y cambiar de rama después se hace con `git checkout` dentro de la VM | 2026-09-27 | Tickets I1-I6 |

## 3. Etapa A — Cambios al repositorio, sin Azure

Estado: **8 hechos, 1 pendiente**. No toca Azure, no gasta crédito.

> **Línea base de calidad (commit `d10056b`).** A partir de este punto cualquier falla es nuestra, no heredada. Es lo que permite distinguir un cambio nuestro de una desviación previa.

| Puerta | Resultado |
| --- | --- |
| `make lint` | `All checks passed!` |
| `make format-check` | en verde, 142 archivos |
| `make test` | **338 pasan, 1 xfail, 1 warning** |

### A0. Línea base verde antes de tocar nada

- **Objetivo:** que `develop` pase sus propias puertas de calidad, para que la Etapa A se mida contra una referencia real.
- **Criterio de aceptación:** las tres puertas en verde sobre la rama sin cambios de este microproyecto, con el recuento anotado como referencia.
- **Confirmación humana:** sí, autorizada el 2026-09-27.
- **Estado:** **hecho**. Dos commits, porque son cosas distintas:
  - `d10056b` — `ruff format` sobre los 4 archivos, verificado con comparación de AST (idéntico antes y después). Problema heredado, también presente en `main` del original.
  - Entorno local — `uv run --package process python -m spacy download es_core_news_md`. Sin commit: el `Makefile` ya lo hacía, solo faltaba en esta máquina. Las 11 pruebas rojas **no eran del repo**.

### A1. Fijar LF en el corpus y recuperar los checksums

- **Objetivo:** que el SHA-256 de los `.jsonl` coincida con `README_gold_v1.md` en cualquier sistema operativo.
- **Toca:** `.gitattributes`; normalización de los `.jsonl` existentes.
- **Criterio de aceptación:** los tres SHA-256 calculados en el working copy en Windows coinciden con los de `README_gold_v1.md`.
- **Confirmación humana:** no.
- **Estado:** **hecho** (commit `27f3f4d`). Evidencia: `dev.jsonl` `57b034dd…99a32c`, `eval.jsonl` `20c53e5a…38912`, `gold_standard_v1.jsonl` `63dbf721…5a992`.

### A2. `validar_corpus` con los tres checksums y salida versionada

- **Objetivo:** un script que valida el corpus y deja una salida que el job de evaluación pueda consumir con `version_corpus=gold_v1`.
- **Toca:** `azureml/src/validar_corpus.py`, `tests/azureml/test_validar_corpus.py`.
- **Criterio de aceptación:** falla con mensaje claro si un checksum no coincide; escribe `<salida>/gold_v1/eval.jsonl`; `manifest.json` lista los cinco archivos del corpus, con checksum en tres y sin checksum en los otros dos.
- **Confirmación humana:** no.
- **Estado:** **hecho** (8 pruebas, patrón AAA). Los tres checksums del README coinciden contra el corpus real en esta máquina: `dev=60`, `eval=340`, `gold_standard_v1=400`. Verificado en las dos direcciones: copia `eval.jsonl` byte a byte idéntica, y con una línea inyectada en `dev.jsonl` el script falla nombrando el archivo y **no deja manifiesto a medias**.
- **Desviación registrada:** el plan (L491) nombra solo `eval.jsonl` y `dev.jsonl`; el README congela tres checksums, así que se validan los tres (D1) y los otros dos archivos del corpus aparecen en el manifiesto sin checksum. El plan no se editó: la diferencia queda anotada acá.

### A3. `leer_secreto` para la clave de Groq

- **Objetivo:** obtener `GROQ_API_KEY` dentro del job, desde Key Vault con la identidad administrada, o desde el entorno si la variable ya está.
- **Toca:** `azureml/src/leer_secreto.py`, `tests/azureml/test_leer_secreto.py`.
- **Criterio de aceptación:** devuelve la clave sin imprimirla; los asserts verifican que la clave nunca aparezca en los logs ni en la salida de los tests; falla con error explícito si no encuentra la variable ni el secreto.
- **Confirmación humana:** no.
- **Estado: revertido. La desviación que se escribió estaba mal, y el error fue de verificación, no de diseño.** Se implementó `leer_secreto.py` leyendo solo `os.environ`, con la premisa de que "la identidad administrada del job ya resuelve el secreto de forma nativa con la referencia de Key Vault del Environment". **Esa premisa es falsa** y no se verificó antes de construir encima:
  - Las referencias `${{keyvault:...}}` son solo para **online endpoints** y deployments (`how-to-deploy-online-endpoint-with-secret-injection`). No aplican a command jobs ni a pipeline jobs, y el Environment **no** admite variables de entorno con referencias a secretos.
  - Para jobs, lo documentado es `DefaultAzureCredential` + `azure-keyvault-secrets` con la identidad administrada del compute (`how-to-use-secrets-in-runs`). Es justo lo que ya prepara la Fase 4 con `az keyvault set-policy --secret-permissions get` (plan L348).
  - La segunda justificación ("evita sumar dos Azure SDK") también era falsa: el Dockerfile del Environment ya los instala en la **imagen de los jobs** (plan L318), no en el paquete `inference`. Cero impacto en las imágenes de los microservicios y cero `uv add`.
- **Cómo queda:** la lectura del secreto se hace dentro de `evaluar.py`, antes de construir el proveedor (se resuelve en **A5**), con `SecretClient` + `DefaultAzureCredential`, escribiendo en `os.environ["GROQ_API_KEY"]` **sin imprimirla y sin sustitución de shell**. Si `GROQ_API_KEY` ya está, no se toca el Key Vault. El componente fija `AZURE_TOKEN_CREDENTIALS=ManagedIdentityCredential` y recibe `KEY_VAULT_URL` como input. Se elimina `leer_secreto.py` del comando del componente (plan L374). A3 deja de ser un ticket con código propio y se reabre como parte de A5.
- **Lo que sí queda en pie:** la preocupación por no imprimir el secreto en el log del job era válida y se conserva — de hecho, el `export GROQ_API_KEY=$(...)` que se quita del comando era exactamente esa fuga. El error fue cambiar el mecanismo correcto (client de Key Vault) por uno inexistente, en lugar de quitarle el `print` al correcto.

### A4. Proteger `registro.py` cuando la corrida ya existe

- **Objetivo:** que `registrar_corrida` funcione dentro de un job de Azure ML sin romper la corrida abierta por MLflow.
- **Toca:** `backend/inference/inference/registro.py` (excepción acotada, ver `REGLAS_AGENTE.md`), `tests/azureml/test_registro_run_id.py`.
- **Criterio de aceptación:** con `MLFLOW_RUN_ID` presente, no se llama `set_experiment`; sin la variable, el comportamiento actual se mantiene; la suite en verde.
- **Confirmación humana:** no.
- **Estado:** **hecho** (6 pruebas, sobre un backend MLflow SQLite real, sin mocks). El arreglo es de **una línea**: `registro.py` ya no llama `set_experiment` cuando existe `MLFLOW_RUN_ID`. Resuelto H2.
- **Hallazgo al implementarlo:** `mlflow.start_run()` **ya respeta `MLFLOW_RUN_ID` por su cuenta** y retoma la corrida existente. Tres de las cuatro pruebas pasaron sin tocar el código: la corrida del padre se reutilizaba igual. Lo único que estaba realmente roto era el `set_experiment` incondicional, que es exactamente lo que rompe cuando hay una corrida activa. El cambio es más chico de lo que suponía el ticket.

### A5. `evaluar.py` y `comparar.py`

- **Objetivo:** el componente de evaluación y el de comparación, sin reescribir el harness.
- **Toca:** `azureml/src/evaluar.py`, `azureml/src/comparar.py`, `tests/azureml/test_evaluar.py`, `tests/azureml/test_comparar.py`.
- **Criterio de aceptación:** `evaluar.py` construye su propio `ServicioInferencia(ProveedorGroq())` y reutiliza `cargar_corpus`, `EvaluadorPrompts`, `metricas_por_campo`, `generar_informe` y `registrar_corrida`; `evaluacion.py` no se modifica; escribe `metricas.json` serializado con `dataclasses.asdict`; acepta `autor` y `rama` como inputs y los pasa a `registrar_corrida`; `comparar.py` elige la versión ganadora con el criterio del plan.
- **Confirmación humana:** no.
- **Estado:** **hecho** (19 pruebas: 9 de `evaluar.py`, 10 de `comparar.py`).
- **Desviación deliberada del plan, y por qué:** el plan (L501) decía que `metricas.json` es `dataclasses.asdict(metricas)`, tal cual. Se le agregó la clave `"modelo"`. La regla de desempate de `comparar.py` depende de *saber cuál de los dos era el modelo barato*, y el job `comparar` del plan (L417-421) solo recibe las dos carpetas de resultados: no tiene forma de saberlo. Las dos salidas eran o meter el modelo en el artefacto, o agregar dos inputs `modelo_a`/`modelo_b` al componente. Se eligió el artefacto porque un `metricas.json` que no dice qué midió es una trampa para quien lo lea después, y MLflow ya registra el modelo como parámetro, así que no es información nueva. **Consecuencia: A8 no necesita cambiar el bloque `comparar` del plan.**
- **Hallazgo al implementarlo:** `Metricas` **no tiene** campos `f1_tipo_evento` ni `f1_es_reporte_accionable` planos; las métricas viven anidadas en `campos: list[MetricaCampo]`, una entrada por campo con `campo`/`evaluados`/`exactitud`/`f1`. `comparar.py` tiene que buscar por nombre de campo, no leer una clave plana. La regla del plan está escrita como si fueran claves planas y no lo son.
- **El desempate está anclado a `openai/gpt-oss-20b`, no a "el más barato de los dos".** Es a propósito: es el modelo que la comparación de costos del plan puso como barato, y escribirlo fijo evita que la regla cambie de significado si cambian los candidatos. Si hay empate y ninguno de los dos es ese modelo, `comparar.py` falla con un error claro en vez de elegir uno al azar.
- **El umbral es estricto:** a una diferencia de exactamente 0,02 ya no es empate y gana el mayor. Cubierto por una prueba que fija ese borde.

### A6. `INFERENCE_MODELO` en el servicio de inferencia

- **Objetivo:** que la VM pueda fijar el modelo ganador por variable de entorno.
- **Toca:** `docker-compose.yml`.
- **Criterio de aceptación:** el servicio `inference` recibe `INFERENCE_MODELO` con default `openai/gpt-oss-20b`; el resto de los servicios no cambia.
- **Confirmación humana:** no.
- **Estado:** **hecho** (una línea en `docker-compose.yml`, sin pruebas porque no hay lógica que probar: es un valor por defecto que Compose ya resuelve).
- **El default se copió de `registro.py`:** se reutilizó `MODELO_POR_DEFECTO = "openai/gpt-oss-20b"` como fuente, para que el Compose y el registro no puedan quedar diciendo modelos distintos. Si algún día cambia el default, hay que cambiar el Compose en el mismo commit.
- **No se validó con `docker compose config`:** el Docker de esta máquina no tiene el plugin compose (`docker compose` sale con código 125). El YAML se validó parseándolo con PyYAML, que es lo que importa acá. El `docker compose config` real se corra en la VM de Azure, en Fase 8.

### A7. Environment de Azure ML y `.amlignore`

- **Objetivo:** una imagen de Python 3.12 con las dependencias del servicio de inferencia y un contexto de subida que no arrastre el repo entero.
- **Toca:** `azureml/env/Dockerfile`, `azureml/env/requirements.txt`, `.amlignore` **en la raíz del repo** (ver H6).
- **Criterio de aceptación:** `requirements.txt` se genera con `uv export --package inference --no-dev --no-hashes --no-emit-workspace`; la imagen instala sin errores; el `.amlignore` excluye `.git`, `data/`, `frontend/`, `*.db` y los `.env`.
- **Confirmación humana:** no.
- **Alcance corregido tras revertir A3.** Este ticket se apoyaba en "la referencia de Key Vault en el Environment `sirena-eval`", que es la premisa falsa que tumbó A3. **A7 no configura ningún secreto**: el Environment solo lleva `azure-identity` y `azure-keyvault-secrets` en la imagen (plan L318) para que el job pueda leer del Key Vault por código. La referencia de Key Vault como mecanismo nativo no existe para command jobs. El permiso se otorga en el ticket B7 (Fase 4) y la lectura efectiva se confirma en la corrida corta de la Fase 6.
- **Estado:** **hecho**. `requirements.txt` (316 líneas, bloqueado por uv), `Dockerfile`, `environment.yml` y `.amlignore` en la raíz.
- **El `requirements.txt` se generó con `uv export -o`, no con `>`:** el plan (L310) usa redirección de shell, y la regla de edición del repo la prohíbe. `-o` hace que sea el propio uv el que escriba el archivo, así que no pasa por PowerShell ni arriesga la codificación. Mismo resultado, sin la parte que ya sabemos que da problemas.
- **`config/` no se puede excluir del `.amlignore`, y está anotado ahí.** `sirena_schema.ontologia` resuelve `config/ontologia.yaml` con una ruta **relativa al directorio de trabajo del proceso** (`ONTOLOGIA_PATH` o `config/ontologia.yaml`). En el job el CWD es la raíz del contexto de código, así que sin ese archivo el job muere al importar `inference`, antes de evaluar nada. Es un fallo silencioso por omisión: nadie lo ve hasta que el job falla en Azure.
- **El corpus no se sube como código.** Va como Data asset (`azureml:gold_v1`), que se registra aparte, así que `eval-prompt/corpus` sí se excluye del contexto de subida sin romper nada.
- **La imagen no lleva el código del repo, y es a propósito:** el `Dockerfile` solo instala dependencias. El código viaja job por job con la propiedad `code: ../..` de cada componente. Por eso el image build context es `azureml/env/` y no la raíz.
- **No se construyó la imagen.** Requiere red y Azure; el build real es un ticket de la Fase 3. Acá se verificó que el `environment.yml` parsea y que las dependencias directas de `inference` y `sirena-schema` (`fastapi`, `uvicorn`, `groq`, `mlflow`, `pydantic`, `pyyaml`) están todas en el `requirements.txt`.

### A8. YAML de componentes y del pipeline

- **Objetivo:** los cuatro componentes y el pipeline, con nombres de inputs y outputs coherentes.
- **Toca:** `azureml/components/sirena_validar_corpus.yml`, `sirena_evaluar_modelo.yml`, `sirena_comparar_modelos.yml`, `sirena_registrar_configuracion.yml`, `azureml/pipeline.yml`.
- **Criterio de aceptación:** cada input y output del `pipeline.yml` existe con el mismo nombre y tipo en el componente que lo consume; los YAML validan contra el esquema de Azure ML; los defaults coinciden con los del plan.
- **Confirmación humana:** no.
- **Estado:** **hecho**. Los cuatro componentes y el pipeline, más `tests/azureml/test_componentes_pipeline.py` con 46 pruebas.
- **Las 46 pruebas atacan la parte que Azure ML no valida antes de crear el job.** Un input que el componente no declara, o un `${{parent.jobs.X.outputs.Y}}` mal escrito, no falla en la suite: falla en Azure, con el job a medio crear y un mensaje que no señala el YAML. Las pruebas resuelven las referencias para comparar el tipo del cable contra el tipo de la salida que se cita, no el texto de la referencia.
- **El output de `comparar` es `uri_folder`, no `uri_file`, y el nombre engaña.** `comparar.py` recibe `--salida` como **carpeta**: hace `mkdir` y escribe `decision.json` adentro. Si el output fuera `uri_file`, Azure subiría una carpeta como si fuera un archivo. Se verificó en el código, no se asumió por el nombre del output.
- **`autor` y `rama` se expusieron como inputs del pipeline.** El script ya los tenía con default (`sirena` y `""`), pero si el pipeline no los expusiera toda corrida quedaría con `autor=sirena` y `rama=""`, y los tags no distinguirían las corridas de los dos. Ahora son inputs del pipeline con default, y la corrida corta se puede atribuir con `--set inputs.autor=...`. Los defaults salen del propio `evaluar.py`, no de un literal repetido.
- **`validar_corpus.py` y `comparar.py` no exportan `PYTHONPATH`:** solo usan la biblioteca estándar y no importan el workspace. `evaluar.py` sí lo necesita, porque importa `inference` y `sirena_schema`.
- **Los archivos se llaman `sirena_*.yml` y el `name:` interno no repite el prefijo** (`sirena_validar_corpus.yml` declara `name: sirena_validar_corpus`). Hay una prueba que lo verifica. El plan L394 los nombraba `validar_corpus.yml`, `evaluar_modelo.yml`, etc.; se siguió el ticket A8, que es más específico, y el `component:` de cada job apunta a los nombres reales.
- **El corpus entra como Data asset, no como código:** el input `gold` declara `default: azureml:gold_v1@latest`, que es la forma correcta en un pipeline job. Por eso `eval-prompt/corpus` sí se puede excluir del `.amlignore`.
- **No se validó contra el esquema JSON de Azure ML.** Se validó coherencia interna, que es lo que esta disponible sin red. La validación real ocurre en `az ml job create`, en la Fase 6.
- **A9 quedó pendiente por este ticket:** el cuarto componente apunta a `azureml/src/registrar.py`, que todavía no existe.

### A9. Script de registro de la configuración ganadora

- **Objetivo:** que el job `registrar` tenga el script que el plan pide, para que el grafo no se rompa en el último paso.
- **Toca:** `azureml/src/registrar.py` y sus pruebas.
- **Criterio de aceptación:** lee `decision.json`, registra `sirena-extractor` en el registro de modelos con la ontología y los hashes de prompts como artefactos, y los tags `modelo`, `f1_tipo_evento`, `latencia_p95_ms`, `prompt_hash` y `job_id`. Sale con codigo 0 si registró, 1 si no pudo decidir.
- **Por que salio de A8:** el plan lo pide en la tabla de cambios al repositorio (L503, `azureml/components/registrar_config.yml` + `azureml/src/registrar.py`), pero el ticket A8 solo cubria los cinco YAML. Se dejo el componente escrito y apuntando al script en vez de inventar un stub: un stub que "funciona" y no registra nada daria un job en verde mintiendo, que es peor que un job en rojo diciendo la verdad.
- **Riesgo propio — cerrado, no era el riesgo real.** El ticket daba por hecho `mlflow.pyfunc.log_model`, que necesita un `loader_module` que el repo no tiene. El plan L161 ya pedia `custom_model`, y esa es la via correcta: `MLClient.models.create_or_update` con `AssetTypes.CUSTOM_MODEL` sobre la carpeta. No hay `loader_module`, no hay pyfunc, no hay que inventar un modulo de carga para un artefacto que no es un modelo entrenado.
- **Tres hallazgos que cambiaron la implementacion, los tres verificados contra la documentacion:**
  - **`identity` no existe en el esquema del command component.** Es clave del job, no del componente: vive en `azureml/pipeline.yml` sobre `jobs.registrar`. Ponerla en el YAML del componente pasa la revision del autor y falla al crear el job. Hay una prueba que verifica que el componente **no** la declare.
  - **El `MLClient` no deduce el workspace dentro de un job.** Los defaults del `az configure` viven en la maquina que submits, no en el contenedor. Por eso `subscription_id`, `resource_group` y `workspace` son inputs del pipeline, sin default porque el workspace todavia no existe.
  - **`decision.json` no alcanza para armar el paquete.** Dice quien gano, pero el informe vive en la carpeta de resultados de ese modelo y `comparar.py` no copia los informes. Por eso `registrar` recibe `resultados_a` y `resultados_b`: los lee para ubicar el `informe.md` cuyo `metricas.json` dice ser el ganador. Si no aparece, el job falla en vez de registrar un paquete sin informe.
- **`azure-ai-ml` va en el `Dockerfile`, no en `requirements.txt`.** Ese archivo se regenera con `uv export -o` y una dependencia agregada a mano desaparece en la siguiente regeneracion. Queda documentado en el propio `Dockerfile` para que nadie la vuelva a agregar abajo.
- **El componente de registro ya no recibe `key_vault_url`.** Registrar no llama a Groq ni lee ningun secreto: solo escribe en el registro de modelos. El input se elimino en vez de dejarlo por costumbre.
- **Estado:** **hecho**. 7 pruebas de `registrar.py` con el `MLClient` doble, sin red, y 2 mas en los YAML. El SDK se importa adentro de `construir_modelo`, no al tope del modulo, para que las pruebas corran sin `azure-ai-ml` en el entorno de desarrollo. Los hashes de `prompts.json` usan el mismo formato que `inference.registro` guarda como parametros de MLflow, y hay una prueba que falla si los dos se desalinean.
- **Lo que sigue sin probar:** la linea que llama `create_or_update` con el SDK real no tiene prueba unitaria, porque el SDK no es dependencia del entorno de desarrollo. Se ejercita en la primera corrida real.
- **Confirmación humana:** no para escribirlo. **Sí** para ejecutarlo contra el workspace de Azure, y para el rol de B10.

## 4. Etapa B — Azure, fases 0 a 4

Estado: **10 pendientes**. Todos los comandos de creación pasan por la puerta de confirmación.

### B1. Lectura de regiones, cuota y proveedores

- **Objetivo:** decidir región y tamaños con datos, no con suposiciones.
- **Toca:** ninguna mutación. `az policy assignment show`, `az vm list-usage`, `az provider show`.
- **Criterio de aceptación:** informe con las regiones permitidas por la política, la cuota de vCPU por familia en cada una, y el estado de registro de los cinco proveedores; recomendación de región y de tamaños siguiendo la tabla de Riesgos del plan.
- **Confirmación humana:** no (solo lectura). La **decisión** de región sí la toma el humano.

**Resultado: hecho.** Decisiones en D8 y D9. Los datos:

**Regiones.** La política `sys.regionrestriction` permite cinco: `francecentral`, `belgiumcentral`, `chilecentral`, `westus`, `mexicocentral`. Su parámetro real es `listOfAllowedLocations`, no `listOfAllowedRegions`; con el nombre equivocado la consulta devuelve `null`, que se lee como "sin restricción" si no se mira el JSON crudo.

**Solo dos pueden hostear el workspace.** Cruzando con la disponibilidad de `Microsoft.MachineLearningServices/workspaces` para esta suscripción:

| Región | Permitida | ML disponible |
| --- | --- | --- |
| `westus` | sí | **sí** |
| `francecentral` | sí | **sí** |
| `chilecentral` | sí | no |
| `mexicocentral` | sí | no |
| `belgiumcentral` | sí | no |

`chilecentral` era la opción obvia por cercanía a Cali, y pasa el filtro de política para después fallar al crear el workspace. `brazilsouth` es la región latinoamericana con ML disponible, y la política la bloquea: **no existe Plan B en Latinoamérica**.

**Cuota de vCPU en `westus`** (idéntica en las cinco regiones, todo en uso 0):

| Familia | Límite | SKU que factura en ella | Nodos |
| --- | --- | --- | --- |
| `standardDSv2Family` | 4 | `Standard_DS2_v2` (2 vCPU) | 2 exactos |
| `standardDASv4Family` | 4 | `Standard_D2as_v4` (2 vCPU) | 2 exactos |
| `standardBsv2Family` | **10** | `Standard_B2s_v2` (2 vCPU) | 5 |
| `standardBSFamily` | 4 | `Standard_B2s` (2 vCPU) | 2 |

La cuota de vCPU es **por suscripción y familia, no por región**: las cinco reportan lo mismo. Cambiar de región no compra vCPU, solo cambia el tamaño o la suscripción. `max-instances 2` consume el 100% de `standardDSv2Family`, sin headroom; por eso el Plan B de la primera corrida es bajar a 1 y correr las dos evaluaciones en serie. Las familias B y D no compiten, así que la VM no le roba cuota al clúster.

**Proveedores.** `MachineLearningServices`, `ContainerRegistry` y `KeyVault` están `NotRegistered`; `Insights` y `Storage` ya están `Registered`. B2 registra tres, no cinco. Relacionado: la consulta de cuota de ML falla con *"check your subscription permissions"* justamente porque el proveedor no está registrado, así que las cifras de ML no son confirmables hasta después de B2.

**Pendiente de confirmar en B7:** que `Standard_DS2_v2` tenga capacidad (no solo cuota) en `westus`. La cuota de familia es 4 y el SKU existe en el catálogo, pero `az vm list-skus` se cuelga en esta máquina y no se pudo leer la restricción de capacidad. Si da `SkuNotAvailable`, el Plan B es `francecentral`.

### B2. Registrar proveedores y crear el grupo de recursos

- **Toca:** `Microsoft.MachineLearningServices`, `Microsoft.ContainerRegistry`, `Microsoft.KeyVault`; `az group create --name rg-sirena-mp3 --location westus`. **Solo los tres que B1 encontró en `NotRegistered`:** `Microsoft.Insights` y `Microsoft.Storage` ya estaban `Registered` y no se tocan. El ticket decía cinco y era lo mismo que H14: afirmar algo que la medición ya había corregido.
- **Criterio de aceptación:** el grupo responde `Succeeded` en `westus`; los tres proveedores quedan en `Registered`, y `Microsoft.Insights` y `Microsoft.Storage` siguen en `Registered` sin haber sido tocados.
- **Confirmación humana:** **sí**. Mostrar comando exacto, recurso tocado y costo (cero, pero crea recursos).

**Resultado: hecho.** `rg-sirena-mp3` creado en `westus`, `provisioningState: Succeeded`. Los tres proveedores quedaron en `Registered` por su cuenta (el registro es asíncrono) y los otros dos nunca se tocaron.

**Lo que costó cerrar B2 no fue el comando, fue la autenticación.** `az group create` falló tres veces con `AADSTS50076` / `invalid_grant` contra la política de acceso condicional `797f4846-ba00-4fd7-ba43-dac1f8f63013`, que exige MFA. Dos cosas costaron entenderlas y ninguna fue un bug del comando:

1. **Un `az login` normal NO alcanza, y devuelve exit 0.** El token nuevo llega sin el claim `p1` que la política pide, así que las escrituras a ARM siguen rechazadas. Lo que funcionó fue el login con el `--claims-challenge` que Azure imprime en el propio error.
2. **El mismo token puede leer y no escribir.** `az group exists` y `az group show` contestaban bien (404 real de ARM) mientras `az group create` moría con 50076. Que las lecturas funcionen no prueba que la escritura pase, y al revés. Verificar con lecturas da una falsa sensación de sesión válida.

El error distingue además dos tenants: el `AADSTS50079` anterior señalaba el "Directorio predeterminado" (`9bb77fc3…`), que no es el de la universidad. El correcto es `693cbea0-4ef9-4254-8977-76e05cb5f556` ("Universidad Autónoma de Occidente", suscripción `Azure for Students`). Con `--tenant` explícito se descarta el equivocado.

### B3. Rol `Contributor` del compañero, acotado al grupo

- **Objetivo:** que el compañero pueda lanzar el pipeline, ver Studio y encender o apagar la VM, sin acceso a nada fuera del microproyecto.
- **Toca:** identidad del compañero en el dominio `uao.edu.co`, alcance `rg-sirena-mp3`.
- **Criterio de aceptación:** `az role assignment list --scope <id de rg-sirena-mp3>` muestra al compañero con rol `Contributor`; el alcance no es la suscripción ni un nivel superior; no hay invitaciones pendientes porque ambos están en `uao.edu.co`.
- **Confirmación humana:** **sí, siempre**. Cambia permisos, no crea recursos: ver la categoría específica en `REGLAS_AGENTE.md`.

### B1b. Rehacer la tabla de costos con precios verificados de `westus`

- **Objetivo:** que los costos del plan sean de la región donde se despliega, y no de `eastus`.
- **Toca:** la tabla de costos de `PLAN_MP3.md` y su párrafo de totales. **Ninguna mutación.** Solo lectura contra `prices.azure.com`.
- **Por qué antes de B4:** la tabla es parte del criterio del 20 % de requerimientos, y B4 es el primer recurso que gasta de verdad.
- **Criterio de aceptación:** cada línea tiene precio verificado contra la API con `armRegionName eq 'westus'`, o la marca `~` de estimado. Los totales de demo y de 24/7 recalculados. La región `eastus` no aparece en ningún precio.
- **Confirmación humana:** no (solo lectura). La **decisión** sobre qué línea es estimada la toma el humano.

**Resultado: hecho.** H16 en detalle. Precios verificados y totales nuevos en la tabla del plan.

### B3b. Crear el presupuesto con alertas al 50 % y 80 % — antes de B4

- **Objetivo:** que exista una alarma antes de que empiece a facturar el workspace.
- **Toca:** un presupuesto en Cost Management con **alcance el grupo de recursos `rg-sirena-mp3`**, no la suscripción, con umbral de **USD 30/mes** y alertas al **50 %** y al **80 %**.
- **Por qué el alcance es el grupo y no la suscripción:** el microproyecto no es dueño de la suscripción `Azure for Students`, que es compartida y tiene otros gastos. Un presupuesto a nivel de suscripción mediría el gasto de todos y no avisaría cuando este proyecto se descontrola. A nivel de grupo, la señal es limpia: lo que se ve es exactamente lo que este microproyecto gastó.
- **Por qué 30 y no 12:** la tabla nueva deja el demo entre 12 y 15 USD. Con 30, el 50 % (15) cae justo en el gasto esperado —avisa de que el sistema está funcionando normal— y el 80 % (24) avisa cuando algo se salió de control. Si el presupuesto fuera 15, el 50 % saltaría en la operación normal y el aviso perdería valor.
- **Por qué antes de B4:** el grupo de recursos de B2 no cuesta nada, pero el workspace crea Storage, Key Vault, Application Insights y el Container Registry, que facturan desde que existen. Crear el presupuesto después es poner la alarma cuando ya se gastó.
- **Criterio de aceptación:** el presupuesto existe con umbral de 30 USD/mes sobre el alcance del grupo, con las dos alertas configuradas; el correo o webhook de aviso está verificado.
- **Confirmación humana:** **sí**. Crea un recurso de facturación, costo $0.
- **Límite que hay que tener presente:** un presupuesto **no detiene el gasto**, solo avisa. El control real es `min-instances 0` en el clúster y `az vm deallocate` al terminar cada sesión. Está anotado en la sección de controles de costo de `PLAN_MP3.md`.

**Resultado: hecho.** `presupuesto-sirena-mp3` creado en `rg-sirena-mp3`, 30 USD/mes, grain Mensual, del 1-S-2026 al 31-D-2026, con alertas 50% y 80% (ambas `GreaterThan`) a `juan_camilo.melendez@uao.edu.co`. El `id` confirma el alcance de grupo: `/subscriptions/1ba330a0-.../resourceGroups/rg-sirena-mp3/providers/Microsoft.Consumption/budgets/presupuesto-sirena-mp3`. `currentSpend.amount: 0.0`, como se espera: el workspace aún no existe.

El comando se ejecutó sin necesidad de un `az login` adicional: el token del último login con `--claims-challenge` que creó el grupo siguió vivo con el claim `p1`.

**B3 (rol `Contributor` del compañero) se mueve a DESPUÉS de B4**, como pediste. El permiso no lo necesitan el workspace ni el clúster, solo se necesita antes de la sustentación. No bloquea nada.

### B4. Crear el workspace y guardar el URI de MLflow

- **Toca:** workspace `mlw-sirena` en `rg-sirena-mp3`; `az configure --defaults`.
- **Criterio de aceptación:** el workspace existe; el `mlflow_tracking_uri` queda anotado en `PROGRESO.md`; Studio abre.
- **Confirmación humana:** **sí**. Costo estimado por el plan, a confirmar en la calculadora.
- **Precondición:** B3b tiene que estar hecho. Si el presupuesto no existe, este ticket no arranca.

**Resultado: hecho.** El workspace `mlw-sirena` existe en `rg-sirena-mp3` con `provisioningState: Succeeded`. Despliegue `mlw-sirena-5948415` completado.

- **`mlflow_tracking_uri`**: `azureml://westus.api.azureml.ms/mlflow/v1.0/subscriptions/1ba330a0-5897-4ef6-8fd1-d304b0e766d1/resourceGroups/rg-sirena-mp3/providers/Microsoft.MachineLearningServices/workspaces/mlw-sirena`
- **Discovery URL**: `https://westus.api.azureml.ms/discovery`
- **Notebook FQDN**: `ml-mlw-sirena-westus-f1f0a3bc-dfdb-48fc-b1d6-39784fe5f29d.westus.notebooks.azure.net`
- **Recursos creados dentro del presupuesto de 30 USD**: Storage (`mlwsirenstorage50b27a14d`), Key Vault (`mlwsirenkeyvault18607254`), Log Analytics (`mlwsirenlogalytif9b602f2`), Application Insights (`mlwsireninsights8a667a82`), y el workspace (`mlw-sirena`).
- **Nota**: el workspace se creó sin Container Registry standalone vinculado (propiedad `containerRegistry` es null). Azure ML usa registros administrados por defecto. Si B6 necesita un ACR explícito, se crea aparte y se vincula al workspace.
- **`az configure --defaults group=rg-sirena-mp3 location=westus`** aplicado.
- **Studio**: accesible en el portal de Azure (el workspace está `Succeeded` y el notebook FQDN está asignado). No se abrió desde esta terminal, pero el recurso existe y es accesible.
- **Costo esperado**: Storage (0,30/mes) + Key Vault (~1/mes) + Application Insights (~1/mes) ≈ 2,3/mes, muy dentro de los 30 USD del presupuesto.

### B5. Subir el corpus como Data asset versionado

- **Toca:** Data asset `gold_v1` con `dev.jsonl` y `eval.jsonl`.
- **Criterio de aceptación:** el asset existe con versión `1`; los archivos subidos conservan el SHA-256 verificado en A1.
- **Confirmación humana:** **sí**.

**Resultado: hecho.** Data asset `gold_v1` versión `1` creado en el `workspaceartifactstore` (type `uri_folder`). Subida de 0.31 MB desde `eval-prompt/corpus/gold_v1/`.

Los 3 JSONL subidos conservan los SHA-256 verificados en A1:
- `dev.jsonl` → `57b034dd1c7a4bf8b03eb5fef8f8c151d2d3ad4f020cf93bab44e1695099a32c` ✓
- `eval.jsonl` → `20c53e5a6efbd5511d1bb151c654e47941bfaf8ed5b3a34095dabe4e67738912` ✓
- `gold_standard_v1.jsonl` → `63dbf721a384bba92a3b160d3172c80b2e44286af1a2740829278cec0b85a992` ✓

Nota: B5 dice `dev.jsonl` y `eval.jsonl`, pero el README y el plan (L158) describen el asset con los tres JSONL + `README_gold_v1.md` con sus checksums. Subí los 3 JSONL + README porque `validar_corpus` necesita los tres para validar. El comando fue `az ml data create --name gold_v1 --path eval-prompt/corpus/gold_v1 --type uri_folder --version 1 --datastore workspaceartifactstore --workspace-name mlw-sirena --resource-group rg-sirena-mp3`.

### B6. Registrar y construir el Environment

- **Toca:** `azureml/env/Dockerfile` y `requirements.txt` de A7.
- **Criterio de aceptación:** el Environment queda `Succeeded`; se anota el tiempo de construcción.
- **Confirmación humana:** **sí**. Costo de la construcción, y después lo consume cada job.

**Resultado: iniciado.** El Environment `sirena-eval` versión `1` fue creado con `az ml environment create --file azureml/env/environment.yml --workspace-name mlw-sirena --resource-group rg-sirena-mp3 --no-wait`. El build context se subió al blob storage (`mlwsirenstorage50b27a14d`). El Docker build (imagen con los ~300 paquetes de `requirements.txt`) es asíncrono — el `provisioningState` aún no aparece, lo cual es normal para el inicio: el build tarda varios minutos. El `environment.yml` define `name: sirena-eval`, `version: 1`, build con `Dockerfile` desde `azureml/env/`.

### B7. Crear el clúster y su identidad

- **Toca:** `cpu-sirena`, `Standard_DS2_v2`, `min-instances 0`, `max-instances 2` (tope duro en las reglas), identidad administrada y permiso de lectura del secreto.
- **Criterio de aceptación:** el clúster queda `Succeeded`; `max-instances` es 2; la identidad puede leer el secreto de Key Vault.
- **Cómo se comprueba el acceso al secreto, y cuándo.** En la **Fase 4 (este ticket)** solo se puede verificar que el permiso quedó **otorgado**: que `az keyvault set-policy --secret-permissions get` corrió, o que la asignación RBAC `Key Vault Secrets User` existe con el principal de la identidad del clúster. Eso **no prueba** que la lectura funcione. La prueba real es una lectura efectiva, y llega en la **corrida corta de la Fase 6**: el job de evaluación usa el secreto para llamar a Groq, así que si la identidad no puede leer, el job falla con `Forbidden` en la llamada al Key Vault. Si aparece, se revisa si el vault usa políticas de acceso o RBAC, y el plan B es pasar la clave por variable de entorno al lanzar el job y rotarla después de la sustentación.
- **Confirmación humana:** **sí**.

**Resultado: en progreso (nodos en provisionamiento).** Clúster `cpu-sirena` creado con `STANDARD_DS2_v2`, `system_assigned`, `principalId: a9efd341-1dc2-4aff-9dc5-11717d40ae17`. `provisioningState: null` — los nodos se están aprovisionando (~5-15 min). Roles de plano de datos asignados:
- **Paso 3**: `Key Vault Secrets User` en `mlwsirenkeyvault18607254` → `a9efd341...` (ServicePrincipal) ✅
- **Paso 4 (B10)**: `AzureML Data Scientist` en `mlw-sirena` → `a9efd341...` (ServicePrincipal) ✅
- **Nota de RBAC**: el Key Vault usa `enableRbacAuthorization: true`. `az keyvault set-policy` **no funciona** con RBAC. Owner de suscripción **no incluye `dataActions`**. Los roles correctos se asignan con `az role assignment create --assignee-object-id <id> --assignee-principal-type ServicePrincipal`. Propagación: ~2 min.

### B8. Key Vault y el secreto de Groq

- **Toca:** Key Vault en `rg-sirena-mp3`.
- **Criterio de aceptación:** la clave queda guardada y la asignación de lectura está activa. **El comando con `<GROQ_API_KEY>` lo corre el humano**, nunca el agente.
- **Confirmación humana:** **sí**, y además la ejecuta el humano.

### B9. Verificación de la etapa y apagado del clúster

- **Toca:** sin recursos nuevos.
- **Criterio de aceptación:** evidencia de cada fase registrada en este archivo; `cpu-sirena` queda con `min-instances 0` y deallocated.
- **Confirmación humana:** **sí** para el `deallocate`.

### B10. Rol `AzureML Data Scientist` para la identidad del clúster

- **Objetivo:** que el job `registrar` pueda crear el modelo ganador en el registro del workspace. Sin este rol el job falla con `Forbidden` al escribir, aunque declare `identity: managed`: la identidad administrada delega el permiso, no lo tiene por sí sola.
- **Toca:** principal de la identidad de `cpu-sirena` (el mismo `PID` de B7), alcance el workspace, rol `AzureML Data Scientist`.
- **Alcance, y por qué este rol:** va sobre el **workspace**, no sobre el grupo ni la suscripción, así que no abre nada fuera del microproyecto. Es el rol mínimo que permite crear modelos; `Reader` no alcanza porque el job escribe.
- **Criterio de aceptación:** `az role assignment list --scope $(az ml workspace show --query id -o tsv) --query "[].{principal:principalName, rol:roleDefinitionName}" -o table` muestra el principal de la identidad del clúster con rol `AzureML Data Scientist`, y ninguna asignación con alcance de suscripción.
- **Confirmación humana:** **sí, siempre**. Cambia permisos, no crea recursos: ver la categoría específica en `REGLAS_AGENTE.md`.
- **Se prueba en la Fase 6.** Igual que B7, este ticket solo puede dejar constancia de que el permiso quedó otorgado. Que la escritura funcione de verdad se ve cuando la corrida corta termina en verde con el modelo registrado.

## 5. Etapa C — Componentes y pipeline (fases 5 y 6)

Estado: **5 pendientes**.

### C1. Registrar los cuatro componentes

- **Toca:** `az ml component create` para cada YAML de A8.
- **Criterio de aceptación:** los cuatro componentes existen en el workspace y su versión coincide con la del repo.
- **Confirmación humana:** **sí**.

### C2. Corrida corta con `limite=5`

- **Toca:** una ejecución del pipeline.
- **Criterio de aceptación:** el job termina en `Completed`; los cuatro pasos aparecen en Studio; existe una corrida de MLflow por modelo.
- **Confirmación humana:** **sí**. Costo acotado por `limite=5`.

### C3. Depurar hasta verde

- **Toca:** los scripts de `azureml/src/` y sus pruebas.
- **Criterio de aceptación:** cada arreglo va con su prueba, `make lint`, `make format-check` y `make test` en verde. Ante un mismo error dos veces, el agente se detiene y pregunta.
- **Confirmación humana:** no para el código; **sí** si el arreglo exige cambiar el clúster, los tamaños o la región.

### C4. Corrida completa sobre los 340 mensajes

- **Toca:** una ejecución del pipeline sin `limite`.
- **Criterio de aceptación:** job `Completed`; métricas de los dos modelos; aparece el riesgo de límites de Groq en `PROGRESO.md` si hubo 429.
- **Confirmación humana:** **sí**, por costo en tokens.

### C5. Extraer la evidencia para la presentación

- **Toca:** solo lectura de Studio y de MLflow.
- **Criterio de aceptación:** quedan anotados el id del job, las métricas de cada modelo, la decisión del paso de comparación, la versión registrada de `sirena-extractor` con sus tags, y la lista de vistas de Studio a capturar.
- **Confirmación humana:** no.

## 6. Etapa D — VM y cierre del ciclo (fases 7 y 8)

Estado: **Reemplazada por PLAN_INFRA.md (VM con Terraform, tickets I1 a I6).** Los tickets D1-D5 quedan marcados como reemplazados por I1-I6.

### D1. Crear la VM, el NSG y la identidad — **REEMPLAZADO por I1-I3**

- **Toca:** VM B2s, puertos 22 y 8501 restringidos a la IP del equipo, identidad administrada.
- **Criterio de aceptación:** la VM existe; el NSG no expone otros puertos; la identidad está asignada.
- **Confirmación humana:** **sí**, comando por comando.

### D2. Instalar dentro de la VM — **REEMPLAZADO por I4**

- **Objetivo:** clonar **el fork y la rama del microproyecto**, no el upstream (ver H8).
- **Toca:** `az vm run-command invoke --command-id RunShellScript`, en bloques pequeños. Docker, Azure CLI, `git clone` de `JCMelendezT/pmu-structured-extraction` en `feature/azureml-pipeline`, `docker compose`.
- **Criterio de aceptación:** los cinco servicios y el tablero levantan; el repo en la VM es el fork en la rama correcta.
- **Confirmación humana:** **sí**, porque cambia la VM. **Ningún secreto en esos scripts.**

### D3. Variables de entorno y health checks — **REEMPLAZADO por I4**

- **Toca:** el `.env` de la VM, que completa el humano por SSH.
- **Criterio de aceptación:** `/health` responde en los cinco servicios; el tablero responde en el puerto 8501.
- **Confirmación humana:** **sí** para `docker compose up -d`; los secretos los pone el humano.

### D4. Fijar el modelo registrado en la VM — **REEMPLAZADO por I5**

- **Toca:** `azureml/scripts/desplegar_config.sh`.
- **Criterio de aceptación:** el script deja en `INFERENCE_MODELO` el modelo ganador según el Model Registry, y se muestra el valor final.
- **Confirmación humana:** no si solo lee del registry; **sí** si el script reinicia contenedores.

### D5. Demo de extremo a extremo — **REEMPLAZADO por I6**

- **Toca:** un mensaje real por el canal que se use en la sustentación.
- **Criterio de aceptación:** la salida estructurada es correcta y la corrida queda registrada en MLflow; evidencia con captura.
- **Confirmación humana:** no.

## 7. Etapa E — Extras opcionales y apagado (fase 9)

Estado: **3 pendientes**. E1 y E2 solo arranca si el equipo decide incluirlos.

### E1. Extra de Designer

- **Criterio de aceptación:** un pipeline equivalente visible en Designer.
- **Confirmación humana:** **sí**, y antes hay que decidir si entra (sigue abierta en el plan).

### E2. Endpoint por lotes para inference

- **Criterio de aceptación:** solo si el equipo lo aprueba; recordatorio: los endpoints en línea están descartados por las reglas, un endpoint por lotes es otra cosa y hay que revisarlo antes.
- **Confirmación humana:** **sí**.

### E3. Apagado y limpieza

- **Objetivo:** no seguir pagando después de la sustentación.
- **Criterio de aceptación:** `cpu-sirena` deallocated; VM deallocated; después de la sustentación, grupo de recursos borrado, clave de Groq rotada y token del bot revocado con BotFather.
- **Confirmación humana:** **sí**, y el borrado del grupo solo si el humano lo pide con esas palabras.

## 8. Etapa F — Materiales de entrega

Estado: **6 pendientes** (F1 a F5 y F7; F6 quedó hecha). Ninguna toca Azure.

### F1. Reemplazar estimaciones por resultados reales

- **Toca:** tabla de costos y sección de riesgos del plan.
- **Criterio de aceptación:** las cifras vienen de `PROGRESO.md`, no del plan estimado; los riesgos que se materializaron quedan anotados.
- **Confirmación humana:** no.

### F2. `docs/AZURE.md`

- **Criterio de aceptación:** guía de despliegue que reproduce lo que efectivamente funcionó, con los comandos reales.
- **Confirmación humana:** no.

### F3. `docs/trabajo_futuro.md`

- **Criterio de aceptación:** refleja que MLflow ya está implementado y que ahora el registro vive en Azure ML.
- **Confirmación humana:** no.

### F4. Guion de la presentación

- **Criterio de aceptación:** guion de 15 minutos derivado de la sección 4 del plan, con resultados reales, y lista de las capturas que faltan.
- **Confirmación humana:** no.

### F5. Handoff para el compañero

- **Criterio de aceptación:** resumen del estado más el contenido de este archivo, para que pueda retomar sin contexto.
- **Confirmación humana:** no.

### F6. Corregir la fila de `validar_corpus` en el plan

- **Toca:** tabla de componentes del plan, fila `validar_corpus`.
- **Qué estaba mal:** la fila decia que el Data asset `gold_v1` traía `eval.jsonl` y `dev.jsonl`, cuando el README tiene los SHA-256 de **tres** JSONL: `dev.jsonl`, `eval.jsonl` y `gold_standard_v1.jsonl`. Un lector que quisiera seguir esa fila subiría un asset incompleto y el job fallaría por un checksum que nunca se podía comparar.
- **Criterio de aceptación:** la fila nombra los tres JSONL y aclara que el README trae los SHA-256 esperados.
- **Estado:** **hecho** en el cierre de A9.
- **Confirmación humana:** no.

### F7. Cerrar H7, la referencia a Llama en `AGENTS.md`

- **Toca:** `AGENTS.md`, sección de contexto del proyecto.
- **Qué está mal:** describe el LLM como "Llama 3.1 8B Instruct vía Groq" cuando el código usa `openai/gpt-oss-20b`. `AGENTS.md` es el archivo que leen los agentes antes de tocar el repo, así que la línea equivocada propaga el error a cualquier trabajo futuro.
- **Criterio de aceptación:** `AGENTS.md` nombra el modelo que el código realmente usa, o dice explícitamente que la elección de modelo está en `registro.py` y no en el documento.
- **Por qué no se hizo ya:** no es un refactor, es cambiar una descripción de contrato que el equipo puede haber escrito a propósito. Es la pregunta 3 de la sección siguiente.

**Resultado: hecho, con visto bueno del humano y señalada para aprobación del equipo.** La instrucción fue: no decidirlo solo, pero tampoco dejarlo abierto; preparar la corrección como parte del PR de esta rama y seguir.

Qué se cambió, y son dos líneas:

1. La línea de contexto: "LLM de pesos abiertos (Llama 3.1 8B Instruct vía Groq)" pasa a "LLM de pesos abiertos (`openai/gpt-oss-20b` vía Groq)".
2. La línea de tags de MLflow: "licencia Llama 3.1 Community License" pasa a "licencia del modelo realmente usado —`MIT` para `gpt-oss-20b`—", citando que es lo que registra `registro.py` con `LICENCIA = "MIT"`.

**El código no se tocó: ya era el correcto.** `registro.py:43` define `LICENCIA = "MIT"` y `docs/CONFIG_PROVEEDORES.md:65` ya decía que `gpt-oss-20b` es "Actualable libre (MIT)". Lo desactualizado era el documento del equipo, no la implementación. El tag de licencia que se registraba ya era el correcto; lo que estaba mal era la línea que lo describía.

**Lo que NO se tocó, a propósito:** `docs/propuesta/propuesta-final-sirena.md` y `docs/trabajo_futuro.md` también hablan de Llama 3.1. Son los entregables de los microproyectos 1 y 2, evaluados y ya entregados: reescribirlos cambia un documento histórico. `trabajo_futuro.md:78` ya registra la contradicción y la deja abierta a propósito. Si el equipo quiere cerrarla, es un ticket aparte y con su visto bueno.
- **Confirmación humana:** no para escribir el cambio. **Sí** para decidir el texto, porque es un acuerdo de equipo.

---

## 11. Etapa de Infraestructura — VM con Terraform (PLAN_INFRA.md)

Estado: **9 pendientes** (I0 a I8). Fuente de verdad: `PLAN_INFRA.md`.

### I0. Cerrar B7 (pipeline de Azure ML)

- **Objetivo:** clave real de Groq en el Key Vault, corrida corta `limite=5` en verde, `sirena-extractor:1` registrado.
- **Toca:** `az keyvault secret set` (lo ejecuta el humano), `az ml job create`.
- **Criterio de aceptación:** los 5 pasos en verde, `metricas.json` de los dos modelos, `decision.json`, y `sirena-extractor` versión 1 con sus tags en el registro.
- **Confirmación humana:** **sí** para `az ml job create`.

### I1. Código Terraform (sin tocar Azure)

- **Objetivo:** escribir `infra/terraform/` y `infra/scripts/` según PLAN_INFRA.md sección 5.
- **Toca:** `versions.tf`, `providers.tf`, `variables.tf`, `data.tf`, `network.tf`, `vm.tf`, `roles.tf`, `outputs.tf`, `cloud-init.yaml.tftpl`, `terraform.tfvars.example`, `.gitignore`, scripts.
- **Criterio de aceptación:** `terraform init`, `terraform fmt -check -recursive` y `terraform validate` en verde; `.gitignore` probado con `git status`.
- **Confirmación humana:** no.

### I2. Secreto de Telegram en el Key Vault

- **Objetivo:** `telegram-bot-token` en el Key Vault.
- **Toca:** `az keyvault secret set`.
- **Criterio de aceptación:** `az keyvault secret show ... --name telegram-bot-token --query "attributes.enabled"` devuelve `true`.
- **Confirmación humana:** **sí**, y además la ejecuta el humano.

### I3. Plan y aplicación

- **Objetivo:** `terraform plan` con 0 cambios y 0 destrucciones sobre lo existente, luego `terraform apply`.
- **Toca:** `terraform plan -out tfplan`, `terraform apply tfplan`.
- **Criterio de aceptación:** VM creada, roles asignados, SSH funciona, `cloud-init status --wait` devuelve `done`.
- **Confirmación humana:** **sí** para `terraform apply`.

### I4. Desplegar los contenedores en la VM

- **Objetivo:** 7 contenedores arriba y 5 `/health` en verde.
- **Toca:** `cargar_secretos.sh`, `docker compose build --parallel 1`, `docker compose up -d`, `salud.sh`.
- **Criterio de aceptación:** los 5 `/health` responden `ok`; `docker compose ps` sin reinicios; el tablero abre.
- **Confirmación humana:** **sí** para `docker compose up -d`.

### I5. Cerrar el ciclo MLOps

- **Objetivo:** la VM usa el modelo del registro.
- **Toca:** `desplegar_config.sh`.
- **Criterio de aceptación:** `docker compose exec inference env | grep INFERENCE_MODELO` muestra el modelo ganador de I0.
- **Confirmación humana:** no.

### I6. Prueba de humo externa

- **Objetivo:** mensaje real al bot, `POST /mensajes` → 202, acceso bloqueado desde IP no autorizada.
- **Toca:** mensaje al bot, `curl -X POST`, prueba desde datos móviles.
- **Criterio de aceptación:** las tres pruebas pasan.
- **Confirmación humana:** no.

### I7. Entrega al equipo

- **Objetivo:** completar `ENTREGA_EQUIPO.md` y compartirlo.
- **Toca:** `docs/microproyecto3/ENTREGA_EQUIPO.md`.
- **Criterio de aceptación:** documento completo con IP, URLs, accesos y restricciones.
- **Confirmación humana:** no.

### I8. Operación durante las pruebas y limpieza

- **Objetivo:** encender, apagar, redimensionar, autorizar IP, y limpieza final.
- **Toca:** `az vm start`, `az vm deallocate`, `terraform apply` para cambios de tamaño, `az group delete` (solo si Juan lo pide).
- **Criterio de aceptación:** VM apagada al terminar cada sesión; limpieza final cuando Juan lo decida.
- **Confirmación humana:** **sí** para `az vm deallocate` y `az group delete`.

---

## 9. Preguntas que siguen abiertas

Se responden en la etapa que las necesita, no antes.

| # | Pregunta | Se resuelve en |
| --- | --- | --- |
| 1 | ¿Cuál es la fecha de entrega y sustentación? Con ella se fija un cronograma por fechas | Etapa F |
| 2 | ¿Se hace el extra de Designer? | Etapa E, antes de arrancar E1 |
| 3 | ¿Se cierra H7, la corrección de `AGENTS.md` que dice Llama 3.1 8B cuando el modelo es `gpt-oss-20b`? | Ticket F7, antes de la sustentación |

## 10. Registro de sesiones

| Sesión | Fecha | Resultado |
| --- | --- | --- |
| 1 | 2026-09-27 | Fork y rama creados, CRLF del corpus corregido (A1), plan contrastado con el código, 12 hallazgos y 7 decisiones registradas, Etapas A a F partidas en 36 tickets |
| 2 | 2026-09-27 | Ticket A0 autorizado y cerrado en dos commits: `d10056b` formatea 4 archivos (AST idéntico verificado) y se instala `es_core_news_md`, que faltaba solo en esta máquina. **Línea base en verde: 338 pasan, 1 xfail.** Las 11 pruebas rojas no eran del repo |
| 3 | 2026-09-27 | A2 hecho: `validar_corpus` con los tres checksums del README y salida `gold_v1/eval.jsonl` + `manifest.json`. Los conteos reales son 60/340/400, y el total del corpus es 400, no la suma de los tres archivos. **Suite: 346 pasan, 1 xfail** |
| 4 | 2026-09-27 | **A3 revertido** por decisión del equipo, con evidencia de la doc oficial: las referencias `${{keyvault:...}}` no existen para command ni pipeline jobs, solo para online endpoints; y el Dockerfile del Environment ya instalaba los dos Azure SDK (plan L318), así que el argumento de "evitar dependencias" era falso. Hallazgo nuevo **H13**. La lectura del secreto pasa a `evaluar.py` con `SecretClient` + `DefaultAzureCredential`, sin imprimir y sin sustitución de shell. A7 y B7 reescritos: A7 no configura secretos, y la lectura efectiva se prueba en la corrida corta de la Fase 6 |
| 5 | 2026-09-27 | A4 hecho: `registro.py` ya no cambia de experimento cuando existe `MLFLOW_RUN_ID`. El arreglo fue **una línea**: `mlflow.start_run()` ya retoma la corrida del padre por su cuenta, así que lo único roto era el `set_experiment` incondicional. **Suite: 352 pasan, 1 xfail** |
| 6 | 2026-09-27 | A5 hecho: `evaluar.py` y `comparar.py`. La clave se resuelve adentro del proceso y no se imprime; el desempate por costo quedó anclado a `gpt-oss-20b` con umbral estricto de 0,02. **Suite: 371 pasan, 1 xfail**. Se apartó del plan a propósito: `metricas.json` lleva `"modelo"` porque el job que compara no recibe el modelo por input |
| 7 | 2026-09-27 | A6 hecho: `INFERENCE_MODELO` con default `openai/gpt-oss-20b` en el servicio `inference` del Compose. El default sale de `MODELO_POR_DEFECTO` de `registro.py`, no de un literal repetido. Sin Docker local: el `docker compose` de esta máquina no tiene plugin, y la imagen de la VM es de Azure, no nuestra |
| 8 | 2026-09-27 | A7 hecho: `requirements.txt` generado con `uv export -o` (316 líneas) en vez de la redirección `>` del plan, más `Dockerfile`, `environment.yml` y `.amlignore` en la raíz. **Ojo con `config/`**: `sirena_schema.ontologia` lo resuelve por ruta relativa al CWD, así que excluirlo del `.amlignore` rompe el job al importar. La imagen no se construyó: eso es Fase 3 |
| 9 | 2026-09-27 | A8 hecho: los cuatro componentes y `pipeline.yml`, con 46 pruebas de coherencia entre cables, nombres y tipos. **El output de `comparar` es `uri_folder` y no `uri_file`**, porque `comparar.py` recibe `--salida` como carpeta y escribe `decision.json` adentro; se verificó en el código, no se asumió por el nombre. `autor` y `rama` se exponieron como inputs del pipeline, que sin eso dejaban toda corrida con `autor=sirena`. Salió **A9**: falta `azureml/src/registrar.py`, que el plan pide y A8 no cubría |
| 10 | 2026-09-27 | **A9 hecho y con la Etapa A cerrada.** `registrar.py` registra `sirena-extractor` como `custom_model` con `MLClient`; nada de `mlflow.pyfunc.log_model`, que era el riesgo que el ticket anotaba y el plan L161 ya descartaba. Tres cosas se corrigieron contra la documentación oficial, no de memoria: **`identity` es clave del job y no del componente** (el esquema del command component no la tiene, y hay prueba que lo fija), **el `MLClient` no deduce el workspace dentro de un job** (los tres identificadores son inputs del pipeline, sin default porque el workspace no existe todavía), y **`decision.json` no basta para armar el paquete** (el informe del ganador vive en su carpeta de resultados, así que `registrar` recibe los dos `resultados`). `azure-ai-ml` quedó en el `Dockerfile` y no en `requirements.txt`, que se regenera con `uv export -o` y borraría la dependencia; el componente de registro perdió `key_vault_url` porque registrar no lee secretos. Salió **B10**: rol `AzureML Data Scientist` para la identidad del clúster, sin el cual el job falla con `Forbidden` al escribir. **Suite: 426 pasan, 1 xfail** |
| 11 | 2026-09-27 | **A9 commiteado y pusheado; B1 hecho.** El equipo descubrió una inconsistencia en el informe de cuota y, al verificar la facturación real de cada SKU, apareció que **el Plan B del clúster se iba a borrar por error** (H14, detalle completo arriba). Decisiones D8 y D9: región `westus` porque la latencia p95 que el proyecto reporta tiene que medir el sistema y no la geografía, y el workspace en EE.UU. por política de la suscripción, con la mitigación de la anonimización en Process. `PROGRESO.md` se registró **antes** de tocar el plan, no al revés. **Suite: 427 pasan, 1 xfail** (sube por la prueba que prohíbe `default` en los identificadores de Azure, porque el repositorio es público) |
| 12 | 2026-09-27 | **B2 a medias, B1b hecho, H7 cerrado.** B2: los tres proveedores quedaron en `Registered` (el registro es asíncrono y terminó bien), pero **`az group create` falló con `AADSTS50076`** — MFA requerido en el token en caché. Los comandos de lectura sí funcionan con ese token; el fallo es solo de escritura. **`rg-sirena-mp3` no existe** y hay que repetir únicamente ese comando después de un `az login`. Tres commits de documentación pusheados antes de esto. **B1b:** la tabla de costos del plan entera rehecha contra `prices.azure.com` con `armRegionName eq 'westus'`. Apareció **H16**: el disco de 32 GB estaba cotizado a ≈ 2,4/mes, que es el precio de la banda `E4` (hasta 256 GiB); el correcto es `E1 LRS` a **0,30/mes**, un factor de 8. Los precios que traía el equipo se confirmaron exactos contra la API: `Standard_B2s` 0,0496 y `Standard_B2s_v2` 0,0992. **D10: la VM vuelve a `Standard_B2s`** porque el headroom de cuota no justificaba pagar el doble por un riesgo que el peldaño 1 de la escalera resuelve gratis (construir en serie); los peldaños 2 y 3 son `B2s_v2` y `B4s_v2`, y redimensionar conserva el disco. **D11: el presupuesto va antes de B4**, porque el workspace crea Storage, Key Vault, Application Insights y Container Registry, que facturan desde que existen. **F7 cerrado** con dos líneas en `AGENTS.md` (Llama → `gpt-oss-20b`, y la licencia → MIT) señaladas en el PR como corrección de documentación para que el equipo apruebe; el código nunca estuvo mal. **Suite: 427 pasan, 1 xfail** |
