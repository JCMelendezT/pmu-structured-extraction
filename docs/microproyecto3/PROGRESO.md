# Progreso — Microproyecto 3 (SIRENA en Azure ML)

Bitácora de la implementación. La fuente de verdad del *qué* es `PLAN_MP3.md`; este archivo registra el *cómo*: hallazgos, decisiones del equipo y estado de cada ticket.

**Rama de trabajo:** `feature/azureml-pipeline` (base `develop` en `28e96af`)
**Fork:** `JCMelendezT/pmu-structured-extraction` · **Upstream:** `Juanxo17/pmu-structured-extraction`
**Reglas:** `docs/microproyecto3/REGLAS_AGENTE.md`

Estado de este documento: **Sesión 1 cerrada, Etapa A iniciada.** Línea base en verde desde `d10056b`. Tickets A0 y A1 hechos; A2 a A8 pendientes.

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
| H7 | `AGENTS.md` describe el LLM como "Llama 3.1 8B Instruct", pero el código y `.env.example` usan `openai/gpt-oss-20b` | `AGENTS.md` vs `backend/inference/inference/proveedor.py:83` | **Abierto.** No se corrigió en silencio. Propuesta: una línea de corrección. Requiere visto bueno del equipo |
| H8 | La Fase 7 del plan clona el upstream, lo que descartaría los componentes de `azureml/` que viven en el fork | Fase 7 del plan, paso de clonado | **Pendiente.** El ticket D2 clona el fork y la rama `feature/azureml-pipeline` |
| H9 | El profesor aceptó que el LLM se sirva desde Groq mientras la evaluación, la comparación, el registro y el despliegue vivan en Azure ML | Respuesta del profesor, 2026-09-26 | **Resuelto.** D5. La pregunta abierta quedó marcada en el plan |
| H10 | No estaba definido sobre qué suscripción se monta todo, lo que bloqueaba los permisos del compañero y el alcance de los comandos | Decisión del equipo | **Resuelto.** D6: una sola suscripción, con rol acotado para el compañero |
| H11 | La rama base `develop` no pasaba `make format-check`: `ruff format` marcaría 4 archivos, dos de ellos justo los que este microproyecto va a tocar (`backend/inference/inference/evaluacion.py` y `backend/inference/inference/registro.py`), más `tests/inference/test_evaluacion.py` y `tests/inference/test_registro.py`. **El mismo problema está en `main` del repositorio original**: no es una regresión del fork | `make format-check` sobre `develop` | **Resuelto.** Commit `d10056b`, verificado que el AST de los 4 archivos es idéntico antes y después |
| H12 | Las 11 pruebas que fallaban eran **del entorno local, no del repo**: las 11 son `spacy.load("es_core_news_md")` y el modelo en español faltaba en esta máquina. `Makefile:8` ya lo descarga en `make install`, o sea que en el equipo que hizo el repo sí estaba. Con el modelo instalado, las 11 pasan | `backend/process/process/anonimizacion.py:70`, 7 pruebas en `test_anonimizacion.py` y 4 en `test_orquestador.py` | **Resuelto.** `uv run --package process python -m spacy download es_core_news_md`. Sin cambios en el repo |

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

## 3. Etapa A — Cambios al repositorio, sin Azure

Estado: **2 hechos, 7 pendientes**. No toca Azure, no gasta crédito.

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

### A3. `leer_secreto` para la clave de Groq

- **Objetivo:** obtener `GROQ_API_KEY` dentro del job, desde Key Vault con la identidad administrada, o desde el entorno si la variable ya está.
- **Toca:** `azureml/src/leer_secreto.py`, `tests/azureml/test_leer_secreto.py`.
- **Criterio de aceptación:** devuelve la clave sin imprimirla; los asserts verifican que la clave nunca aparezca en los logs ni en la salida de los tests; falla con error explícito si no encuentra la variable ni el secreto.
- **Confirmación humana:** no.

### A4. Proteger `registro.py` cuando la corrida ya existe

- **Objetivo:** que `registrar_corrida` funcione dentro de un job de Azure ML sin romper la corrida abierta por MLflow.
- **Toca:** `backend/inference/inference/registro.py` (excepción acotada, ver `REGLAS_AGENTE.md`), `tests/azureml/test_registro_run_id.py`.
- **Criterio de aceptación:** con `MLFLOW_RUN_ID` presente, no se llama `set_experiment`; sin la variable, el comportamiento actual se mantiene; la suite en verde.
- **Confirmación humana:** no.

### A5. `evaluar.py` y `comparar.py`

- **Objetivo:** el componente de evaluación y el de comparación, sin reescribir el harness.
- **Toca:** `azureml/src/evaluar.py`, `azureml/src/comparar.py`, `tests/azureml/test_evaluar.py`, `tests/azureml/test_comparar.py`.
- **Criterio de aceptación:** `evaluar.py` construye su propio `ServicioInferencia(ProveedorGroq())` y reutiliza `cargar_corpus`, `EvaluadorPrompts`, `metricas_por_campo`, `generar_informe` y `registrar_corrida`; `evaluacion.py` no se modifica; escribe `metricas.json` serializado con `dataclasses.asdict`; acepta `autor` y `rama` como inputs y los pasa a `registrar_corrida`; `comparar.py` elige la versión ganadora con el criterio del plan.
- **Confirmación humana:** no.

### A6. `INFERENCE_MODELO` en el servicio de inferencia

- **Objetivo:** que la VM pueda fijar el modelo ganador por variable de entorno.
- **Toca:** `docker-compose.yml`.
- **Criterio de aceptación:** el servicio `inference` recibe `INFERENCE_MODELO` con default `openai/gpt-oss-20b`; el resto de los servicios no cambia.
- **Confirmación humana:** no.

### A7. Environment de Azure ML y `.amlignore`

- **Objetivo:** una imagen de Python 3.12 con las dependencias del servicio de inferencia y un contexto de subida que no arrastre el repo entero.
- **Toca:** `azureml/env/Dockerfile`, `azureml/env/requirements.txt`, `.amlignore` **en la raíz del repo** (ver H6).
- **Criterio de aceptación:** `requirements.txt` se genera con `uv export --package inference --no-dev --no-hashes --no-emit-workspace`; la imagen instala sin errores; el `.amlignore` excluye `.git`, `data/`, `frontend/`, `*.db` y los `.env`.
- **Confirmación humana:** no.

### A8. YAML de componentes y del pipeline

- **Objetivo:** los cuatro componentes y el pipeline, con nombres de inputs y outputs coherentes.
- **Toca:** `azureml/components/sirena_validar_corpus.yml`, `sirena_evaluar_modelo.yml`, `sirena_comparar_modelos.yml`, `sirena_registrar_configuracion.yml`, `azureml/pipeline.yml`.
- **Criterio de aceptación:** cada input y output del `pipeline.yml` existe con el mismo nombre y tipo en el componente que lo consume; los YAML validan contra el esquema de Azure ML; los defaults coinciden con los del plan.
- **Confirmación humana:** no.

## 4. Etapa B — Azure, fases 0 a 4

Estado: **9 pendientes**. Todos los comandos de creación pasan por la puerta de confirmación.

### B1. Lectura de regiones, cuota y proveedores

- **Objetivo:** decidir región y tamaños con datos, no con suposiciones.
- **Toca:** ninguna mutación. `az policy assignment show`, `az vm list-usage`, `az provider show`.
- **Criterio de aceptación:** informe con las regiones permitidas por la política, la cuota de vCPU por familia en cada una, y el estado de registro de los cinco proveedores; recomendación de región y de tamaños siguiendo la tabla de Riesgos del plan.
- **Confirmación humana:** no (solo lectura). La **decisión** de región sí la toma el humano.

### B2. Registrar proveedores y crear el grupo de recursos

- **Toca:** `Microsoft.MachineLearningServices`, `Microsoft.ContainerRegistry`, `Microsoft.KeyVault`, `Microsoft.Insights`, `Microsoft.Storage`; `az group create --name rg-sirena-mp3`.
- **Criterio de aceptación:** el grupo responde `Succeeded`; los cinco proveedores quedan en `Registered`.
- **Confirmación humana:** **sí**. Mostrar comando exacto, recurso tocado y costo (cero, pero crea recursos).

### B3. Rol `Contributor` del compañero, acotado al grupo

- **Objetivo:** que el compañero pueda lanzar el pipeline, ver Studio y encender o apagar la VM, sin acceso a nada fuera del microproyecto.
- **Toca:** identidad del compañero en el dominio `uao.edu.co`, alcance `rg-sirena-mp3`.
- **Criterio de aceptación:** `az role assignment list --scope <id de rg-sirena-mp3>` muestra al compañero con rol `Contributor`; el alcance no es la suscripción ni un nivel superior; no hay invitaciones pendientes porque ambos están en `uao.edu.co`.
- **Confirmación humana:** **sí, siempre**. Cambia permisos, no crea recursos: ver la categoría específica en `REGLAS_AGENTE.md`.

### B4. Crear el workspace y guardar el URI de MLflow

- **Toca:** workspace `mlw-sirena` en `rg-sirena-mp3`; `az configure --defaults`.
- **Criterio de aceptación:** el workspace existe; el `mlflow_tracking_uri` queda anotado en `PROGRESO.md`; Studio abre.
- **Confirmación humana:** **sí**. Costo estimado por el plan, a confirmar en la calculadora.

### B5. Subir el corpus como Data asset versionado

- **Toca:** Data asset `gold_v1` con `dev.jsonl` y `eval.jsonl`.
- **Criterio de aceptación:** el asset existe con versión `1`; los archivos subidos conservan el SHA-256 verificado en A1.
- **Confirmación humana:** **sí**.

### B6. Registrar y construir el Environment

- **Toca:** `azureml/env/Dockerfile` y `requirements.txt` de A7.
- **Criterio de aceptación:** el Environment queda `Succeeded`; se anota el tiempo de construcción.
- **Confirmación humana:** **sí**. Costo de la construcción, y después lo consume cada job.

### B7. Crear el clúster y su identidad

- **Toca:** `cpu-sirena`, `Standard_DS2_v2`, `min-instances 0`, `max-instances 2` (tope duro en las reglas), identidad administrada y permiso de lectura del secreto.
- **Criterio de aceptación:** el clúster queda `Succeeded`; `max-instances` es 2; la identidad puede leer el secreto de Key Vault.
- **Confirmación humana:** **sí**.

### B8. Key Vault y el secreto de Groq

- **Toca:** Key Vault en `rg-sirena-mp3`.
- **Criterio de aceptación:** la clave queda guardada y la asignación de lectura está activa. **El comando con `<GROQ_API_KEY>` lo corre el humano**, nunca el agente.
- **Confirmación humana:** **sí**, y además la ejecuta el humano.

### B9. Verificación de la etapa y apagado del clúster

- **Toca:** sin recursos nuevos.
- **Criterio de aceptación:** evidencia de cada fase registrada en este archivo; `cpu-sirena` queda con `min-instances 0` y deallocated.
- **Confirmación humana:** **sí** para el `deallocate`.

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

Estado: **5 pendientes**.

### D1. Crear la VM, el NSG y la identidad

- **Toca:** VM B2s, puertos 22 y 8501 restringidos a la IP del equipo, identidad administrada.
- **Criterio de aceptación:** la VM existe; el NSG no expone otros puertos; la identidad está asignada.
- **Confirmación humana:** **sí**, comando por comando.

### D2. Instalar dentro de la VM

- **Objetivo:** clonar **el fork y la rama del microproyecto**, no el upstream (ver H8).
- **Toca:** `az vm run-command invoke --command-id RunShellScript`, en bloques pequeños. Docker, Azure CLI, `git clone` de `JCMelendezT/pmu-structured-extraction` en `feature/azureml-pipeline`, `docker compose`.
- **Criterio de aceptación:** los cinco servicios y el tablero levantan; el repo en la VM es el fork en la rama correcta.
- **Confirmación humana:** **sí**, porque cambia la VM. **Ningún secreto en esos scripts.**

### D3. Variables de entorno y health checks

- **Toca:** el `.env` de la VM, que completa el humano por SSH.
- **Criterio de aceptación:** `/health` responde en los cinco servicios; el tablero responde en el puerto 8501.
- **Confirmación humana:** **sí** para `docker compose up -d`; los secretos los pone el humano.

### D4. Fijar el modelo registrado en la VM

- **Toca:** `azureml/scripts/desplegar_config.sh`.
- **Criterio de aceptación:** el script deja en `INFERENCE_MODELO` el modelo ganador según el Model Registry, y se muestra el valor final.
- **Confirmación humana:** no si solo lee del registry; **sí** si el script reinicia contenedores.

### D5. Demo de extremo a extremo

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

Estado: **5 pendientes**. Ninguna toca Azure.

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

---

## 9. Preguntas que siguen abiertas

Se responden en la etapa que las necesita, no antes.

| # | Pregunta | Se resuelve en |
| --- | --- | --- |
| 1 | ¿Cuál es la fecha de entrega y sustentación? Con ella se fija un cronograma por fechas | Etapa F |
| 2 | ¿Se hace el extra de Designer? | Etapa E, antes de arrancar E1 |
| 3 | ¿Se cierra H7, la corrección de `AGENTS.md` que dice Llama 3.1 8B cuando el modelo es `gpt-oss-20b`? | Antes de cerrar la Etapa A |

## 10. Registro de sesiones

| Sesión | Fecha | Resultado |
| --- | --- | --- |
| 1 | 2026-09-27 | Fork y rama creados, CRLF del corpus corregido (A1), plan contrastado con el código, 12 hallazgos y 7 decisiones registradas, Etapas A a F partidas en 36 tickets |
| 2 | 2026-09-27 | Ticket A0 autorizado y cerrado en dos commits: `d10056b` formatea 4 archivos (AST idéntico verificado) y se instala `es_core_news_md`, que faltaba solo en esta máquina. **Línea base en verde: 338 pasan, 1 xfail.** Las 11 pruebas rojas no eran del repo |
