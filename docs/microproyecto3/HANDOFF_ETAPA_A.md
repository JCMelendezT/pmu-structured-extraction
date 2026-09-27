# Handoff — Etapa A cerrada, arranque de la Etapa B

**Fecha:** 2026-09-27
**Rama:** `feature/azureml-pipeline` (16 commits sobre `origin/develop`, ya pusheada a `origin`)
**Último commit:** `3802289 feat(mp3): registrar la configuracion ganadora como custom_model`
**Suite:** 427 pasan, 1 xfail. Lint y formato limpios. Sube de 426 por la prueba que prohíbe `default` en `subscription_id`, `resource_group` y `workspace`, agregada porque el repositorio es público.
**Estado:** Etapa A completa. Todo lo hecho es código y pruebas; **cero recursos de Azure creados**.

> Este documento no reemplaza a `PROGRESO.md`, que es el estado real y detallado del proyecto
> (36 tickets, hallazgos, decisiones, registro de sesiones). Acá va solo lo que no está allá y
> lo que hace falta para arrancar una sesión nueva sin leer 400 líneas primero.

---

## 1. Qué quedó hecho

Los nueve tickets de la Etapa A están cerrados y commiteados uno por uno.

| Ticket | Commit | Qué dejó |
| --- | --- | --- |
| A0, A1 | `eff2d66`, `27f3f4d`, `b6bfc5b`, `d10056b` | Línea base en verde, `.gitattributes` para que los checksums del corpus no dependan del SO |
| A2 | `216e83b` | `validar_corpus.py`: valida los **tres** SHA-256 del README y deja `gold_v1/eval.jsonl` + `manifest.json` |
| A3 | `c546741` | **Revertido** por decisión del equipo. La lectura del secreto va dentro de `evaluar.py` |
| A4 | `f6eef40` | `registro.py` no cambia de experimento si ya hay corrida abierta |
| A5 | `011f001` | `evaluar.py` y `comparar.py`, con la regla de selección y el desempate por costo |
| A6 | `1b75608` | `INFERENCE_MODELO` con default `openai/gpt-oss-20b` en el Compose |
| A7 | `31c9b60` | `requirements.txt` generado, `Dockerfile`, `environment.yml`, `.amlignore` |
| A8 | `e4eb5e1` | Los cuatro componentes y `pipeline.yml` |
| A9 | `3802289` | `registrar.py`: registra `sirena-extractor` como `custom_model` |

Detalle, criterios de aceptación y evidencia de cada uno: **sección 3 de `PROGRESO.md`**.

## 2. Decisiones que ya están tomadas

No reabrir salvo que aparezca evidencia nueva. Están en `PROGRESO.md` §2 (D1 a D7); las que
más peso tienen para la Etapa B:

- **Una sola suscripción**, la del propietario del proyecto. El compañero entra con `Contributor`
  acotado a `rg-sirena-mp3`. Ambos en el mismo dominio, sin invitaciones.
- **Groq es el único proveedor.** No hay Azure AI Foundry en ninguna parte.
- **Selección del modelo:** promedio del F1 de `tipo_evento` y `es_reporte_accionable`. Si la
  diferencia es `>= 0.02` gana el mayor; si es `< 0.02` gana `openai/gpt-oss-20b` por costo.
- **La identidad administrada no tiene permiso por sí misma.** Delegar no es tener. De ahí B10.
- **`${{keyvault:...}}` no existe para command ni pipeline jobs**, solo para online endpoints. El
  secreto se lee con `SecretClient` adentro del proceso, nunca por sustitución de shell.

## 3. Los tres desvíos de A9

Son lo más importante que se lleva la sesión nueva, porque los tres se verificaron contra la
documentación oficial y no contra la suposición. **Están documentados en el cuerpo del commit
`3802289` y en la sección A9 de `PROGRESO.md`; acá va el resumen.**

**a) `identity` es clave del job, no del componente.**
El esquema `commandComponent.schema.json` no lista `identity` entre sus claves válidas; el
`pipelineJob.schema.json` sí, con `ManagedIdentityConfiguration` y valores `managed` /
`managed_identity`. Ponerla en el YAML del componente pasa la revisión del autor y falla en
`az ml job create`. Vive en `azureml/pipeline.yml` sobre `jobs.registrar`.
**Hay una prueba que verifica que el componente NO declare `identity`.** No la borres: es lo que
impide que alguien devuelva la clave al lugar donde no valida.

**b) `azure-ai-ml` está en el `Dockerfile`, no en `azureml/env/requirements.txt`.**
Ese archivo se regenera con `uv export -o`. Cualquier dependencia agregada a mano desaparece en
la siguiente regeneración, sin aviso ni error. Si alguien insiste en tenerla en
`requirements.txt`, hay que cambiar **cómo se genera** ese archivo, no editarlo.

**c) `subscription_id`, `resource_group` y `workspace` son inputs del pipeline, sin default.**
El `MLClient` no los deduce dentro de un job: los defaults del `az configure` viven en la
máquina que submits, no en el contenedor. Circulan variables tipo `AZUREML_ARM_SUBSCRIPTION`,
pero no hay documentación oficial que las respalde como contrato, y el último paso del
pipeline no va a depender de algo no documentado.

> **Restricción permanente:** el repositorio es público. `subscription_id`, `resource_group` y
> `workspace` **no pueden** aparecer como `default` en `pipeline.yml` en ningún momento. Se
> pasan siempre al crear el job. Si alguna vez hay que fijarlos, que sea en un `.env` local
> ignorado, nunca en un archivo versionado.

## 4. Reglas del repo que hay que conocer antes de tocar nada

Detalle completo en `docs/microproyecto3/REGLAS_AGENTE.md`. Lo que más cuesta si no se sabe:

- **Encoding:** editar con las herramientas de edición, nunca con `Set-Content`, `Out-File`, `>`
  ni `>>`. En PowerShell 5.1 esos comandos escriben los `.md` con acentos corruptos.
- **Gates:** `make lint`, `make format-check` y `make test` en verde antes de cerrar cada ticket.
- **Correr los tests con `uv run pytest`.** `python -m pytest` con el Python del sistema (3.14 en
  esta máquina) no encuentra los módulos de `azureml/src` y falla en la recolección.
- **TDD:** pruebas en `tests/azureml/`, patrón AAA, docstrings Google.
- **Confirmación humana** para toda mutación de Azure y toda asignación de rol. Mostrar comando
  exacto, recurso tocado y costo estimado antes de ejecutar.
- **Sin push** salvo que lo pida explícitamente.

## 5. Trampas que ya se pisaron

Cosas que no se ven leyendo el código y que cuestan una hora si se redescubren:

- **`config/` no puede estar en `.amlignore`.** `sirena_schema.ontologia` resuelve
  `config/ontologia.yaml` con una ruta relativa al directorio de trabajo del proceso. Si se
  excluye, el job muere al importar, antes de evaluar nada.
- **El output `decision` de `comparar` es `uri_folder`, no `uri_file`,** aunque se llame
  `decision`: `comparar.py` recibe `--salida` como carpeta y escribe `decision.json` adentro.
- **`decision.json` no alcanza para armar el paquete del modelo.** Dice quién ganó, pero el
  `informe.md` vive en la carpeta de resultados de ese modelo y `comparar.py` no copia informes.
  Por eso `registrar` recibe `resultados_a` y `resultados_b`.
- **La imagen del Environment no se construyó todavía.** Eso es Fase 3 (B6). En esta máquina
  tampoco hay Docker, así que el `docker compose` es la VM de Azure, no el equipo local.
- **Queda una línea sin prueba unitaria:** la que llama `create_or_update` con el SDK real. El
  SDK de Azure quedó fuera del entorno de desarrollo a propósito, así que eso se ejercita en la
  primera corrida real. Es el primer punto donde puede fallar el pipeline.
- **VirtualBox sirve.** Docker no se necesita hasta la Fase 8, que es la VM de microservicios.

## 6. Qué sigue: la Etapa B

Las diez tareas de la Etapa B están en `PROGRESO.md` §4. El orden y lo que bloquea qué:

1. **B1 — regiones, cuota y proveedores.** Solo lectura, no pide confirmación. **Es lo siguiente.**
2. **B2 — grupo de recursos y los cinco proveedores.** Pide confirmación.
3. **B4 — workspace `mlw-sirena`.** Pide confirmación. Anotar el `mlflow_tracking_uri` en `PROGRESO.md`.
4. **B7 + B10 — clúster `cpu-sirena` y su rol.** **B10 es el que desbloquea el job `registrar`**:
   sin `AzureML Data Scientist` sobre el workspace, falla con `Forbidden` al escribir aunque
   declare `identity: managed`.
5. **B8 — Key Vault.** El comando con `<GROQ_API_KEY>` lo corre el humano, nunca el agente.
6. **Fase 6 — corrida corta con `limite=5`.** Primer contacto real con Azure. Acá se descubre si
   la línea sin prueba unitaria funciona. Al crear el job hay que pasar explícitamente
   `subscription_id`, `resource_group` y `workspace`.

Coste: la corrida corta son centavos. El clúster queda en `min-instances 0` y se apaga al
terminar. Borrar el grupo de recursos y rotar la clave de Groq, después de la sustentación.

## 7. Suggested skills para la sesión siguiente

- **`sdd-explore`** o el agente `explore`: para leer `PROGRESO.md` y `PLAN_MP3.md` sin gastar
  contexto de a uno.
- **`systemic-issue-triage`**: si aparece un hallazgo durante B1, el formato de `PROGRESO.md`
  §1 (H1 a H13) ya separa el síntoma de la causa raíz, así que conviene seguirlo.
- **`webapp-testing`** / las herramientas `azure-mcp_*`: para las consultas de Azure de B1 y para
  inspeccionar el job cuando la corrida corta falle.
- Ignorar cualquier skill que sugiera refactors: el alcance de la Etapa B es escribir los
  tickets, no mejorar el código de la Etapa A.

## 8. Nada sensible en este documento

No hay claves, tokens ni identificadores de suscripción. El nombre del tipo de suscripción
("Azure for Students") está en `PROGRESO.md` desde antes y es una decisión del equipo, no un
secreto. El `GROQ_API_KEY` vive solo en el Key Vault y lo carga el humano.
