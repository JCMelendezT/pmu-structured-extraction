# Plan Microproyecto 3 — SIRENA en Azure Machine Learning

Sep 26, 2026 · @Juan M

SIRENA se monta en Azure con Azure Machine Learning como núcleo: un pipeline que evalúa y compara los modelos de extracción contra el gold standard, registra todo en MLflow y versiona la configuración ganadora; los microservicios corren en una VM con Docker Compose y consumen esa configuración.

## Resumen: qué pide el enunciado y cómo se cubre

El Microproyecto 3 pide resolver el problema de un cliente real o ficticio "usando las herramientas que provee Azure Machine Learning". El cliente es el Puesto de Mando Unificado (PMU) de Cali y el problema es el que ya resuelve SIRENA; lo nuevo es llevarlo a Azure con Azure ML como pieza central, no como adorno.

| Criterio | Peso | Lo que pide el enunciado | Entregable concreto en este plan |
| --- | --- | --- | --- |
| 1. Análisis de requerimientos | 20 % | Empresa y necesidades; requerimientos y restricciones; alternativas y selección; pipeline de Azure ML con componentes o algoritmos; costos con la calculadora de Azure | Secciones 1, Alternativas, Pipeline y Costos; export de la calculadora de precios (PDF o enlace) |
| 2. Propuesta de diseño | 25 % | Diagrama de componentes, relación y flujo entre ellos, descripción de cada uno | Diagrama de arquitectura + tabla de componentes + flujo numerado |
| 3. Demo | 30 % | Implementar un demo de la solución diseñada | Pipeline corriendo en Azure ML Studio, modelo registrado, app en VM procesando un mensaje real de Telegram |
| 4. Presentación | 25 % | 15 minutos: requerimientos, diseño y demo | Guion minuto a minuto + video de respaldo del demo |

El mayor peso está en el demo (30 %), así que el plan prioriza que el pipeline de Azure ML y la app funcionen de punta a punta antes de pulir documentos. Referencias que da el enunciado: [referencia de componentes de Azure ML](https://learn.microsoft.com/es-es/azure/machine-learning/component-reference/component-reference) y la [calculadora de precios](https://azure.microsoft.com/es-es/pricing/calculator/).

## Contexto heredado del curso

El plan reutiliza lo ya practicado: VM Ubuntu del módulo IaaS para los microservicios, APIs REST como forma de comunicación y la verificación de regiones antes de crear cualquier recurso.

| Fuente | Qué aporta | Cómo se usa aquí |
| --- | --- | --- |
| Práctica IaaS (Azure VM) | Ubuntu Server 22.04 LTS, tamaño sugerido Standard\_DS1\_v2, regiones alternativas si no hay capacidad | La VM que aloja los 5 microservicios, el frontend y el bot de Telegram. Se sube a B2s porque 3,5 GB de RAM no alcanzan para 7 contenedores |
| Práctica REST y REST + MySQL | API REST en Flask, pruebas con curl y Postman, pregunta de persistencia al apagar la máquina | SIRENA ya es REST (FastAPI). La pregunta de persistencia se responde con el volumen Docker de SQLite en el disco de la VM |
| Diapositivas API REST | Recursos, métodos HTTP, códigos de respuesta, JSON | Justifica el contrato `docs/CONTRATOS_SISTEMA.md` en la presentación |
| Guía de regiones | `az policy assignment show --name sys.regionrestriction` para ver regiones permitidas | Paso 0 del demo, antes de crear el grupo de recursos |
| Recomendaciones del profesor (23/09/2026) | Máximo 3 IP públicas por suscripción; escasez de recursos; se puede usar una sola suscripción del grupo; AWS EC2 como alternativa | El diseño usa 1 sola IP pública. Plan B de región y de suscripción en Riesgos |
| Gartner 2025 (clase 12) | Azure: fuerte en IA empresarial, pero con escasez de capacidad en varias regiones | Argumento de selección de proveedor y riesgo explícito de capacidad |
| Microproyecto 2 (AKS) | Clúster AKS, despliegue de un clasificador y monitoreo | Alternativa evaluada para los microservicios; se descarta para el demo por cuota de vCPU, pero se presenta como evolución a producción |

Restricciones prácticas que condicionan todo el diseño:

- Suscripción Azure for Students, con crédito limitado y cuota baja de vCPU por región. Hay que medirla antes de diseñar el cómputo.
- El trabajo es en parejas, pero la nota y la sustentación son individuales: cada integrante debe poder explicar y operar todo el demo.
- El equipo trabaja en Windows. Los comandos del plan están pensados para Azure Cloud Shell (bash) o WSL; no dependen de la terminal local.

## Estado actual de SIRENA y qué implica para la nube

El repositorio ya trae casi todo lo que Azure ML necesita: un harness de evaluación con CLI, registro en MLflow por variable de entorno, un gold standard congelado y Dockerfiles por servicio. Revisado sobre `main` (merge del PR #60).

| Pieza del repo | Estado | Implicación para el microproyecto |
| --- | --- | --- |
| 5 microservicios FastAPI (BFF :8000, CRUD :8001, Process :8002, Inference :8003, Geo :8004) + Frontend Streamlit :8501 | Con Dockerfile cada uno y `docker-compose.yml` | Se despliegan tal cual en la VM con `docker compose up -d` |
| Bot de Telegram (`telegram_source.py`) | Usa long polling (`GET /getUpdates`) | No necesita puerto de entrada ni IP adicional: solo salida a internet |
| Inference | LLM `openai/gpt-oss-20b` vía Groq, 2 etapas (compuerta + extracción), proveedor desacoplado con el protocolo `ProveedorLLM` | El modelo se elige con `INFERENCE_MODELO`. Agregar otro proveedor no toca el resto del código **del servicio Inference**; no aplica al harness de evaluación, que construye su propio `ServicioInferencia(ProveedorGroq())` en `azureml/src/evaluar.py` sin tocar `evaluacion.py` |
| Harness `inference.evaluacion` | CLI con `--corpus`, `--report`, `--limite`; calcula exactitud, F1 por campo, latencia media y p95, matrices de confusión | Es el código del componente de evaluación del pipeline, sin reescribirlo |
| `inference.registro` | Registra parámetros, métricas, artefactos y tags en MLflow si existe `MLFLOW_TRACKING_URI` | Azure ML es un servidor MLflow nativo: apuntar esa variable al workspace basta para que las corridas aparezcan en Studio |
| Gold standard v1 | 400 mensajes congelados con checksum SHA-256: 60 dev y 340 eval | Se sube como Data asset versionado; el checksum se valida en el pipeline |
| CRUD | SQLite en volumen Docker `sirena_db` | Suficiente para el demo; Azure SQL o PostgreSQL queda como evolución |
| Contenedor `mlflow` local en Compose | Existe | Se reemplaza por el tracking de Azure ML (se quita del Compose de la VM) |

Tres advertencias que conviene decir en la sustentación antes de que las pregunten:

- **El corpus es sintético.** Se generó por plantillas y la anotación de las 4 partidas fue simulada (`docs/trabajo_futuro.md`). Las métricas miden el pipeline, no el desempeño en mensajes reales.
- **No hay entrenamiento.** La constitución del proyecto prohíbe fine-tuning y GPU local (principio V). Azure ML se usa para evaluar, comparar, rastrear y versionar, que es MLOps legítimo para un modelo preentrenado.
- **`docs/trabajo_futuro.md` está desactualizado**: dice que MLflow no está implementado, pero `registro.py` y la dependencia `mlflow>=3.16.1` ya existen.

## 1. Análisis de requerimientos (20 %)

El cliente necesita convertir mensajes ciudadanos en texto libre en registros revisables en segundos, y poder demostrar con números qué tan bien lo hace el modelo antes de confiar en él.

### Empresa y necesidad

- **Cliente:** Puesto de Mando Unificado (PMU) de Santiago de Cali, que coordina la respuesta a emergencias según la Estrategia de Respuesta a Emergencias (ERE) del municipio.
- **Problema:** en una emergencia masiva (caso de referencia: la tragedia del 10 de agosto en Cali) los reportes llegan por mensajería, sin estructura y en volumen alto. El triaje manual es lento y propenso a errores.
- **Necesidad:** un copiloto que estructure cada mensaje (tipo de evento, servicio de respuesta, ubicación a barrio/comuna) para que un operador humano decida. Nunca prioriza ni despacha.
- **Necesidad nueva que resuelve Azure ML:** el PMU no puede adoptar un modelo de lenguaje sin evidencia. Necesita evaluaciones reproducibles, comparables y auditables cada vez que cambia el modelo, el prompt o la ontología.

### Requerimientos funcionales

| ID | Requerimiento | Componente que lo cumple |
| --- | --- | --- |
| RF-01 | Recibir mensajes ciudadanos desde Telegram | Bot `telegram-source` + BFF |
| RF-02 | Anonimizar datos personales antes de enviarlos al LLM o persistirlos | Process |
| RF-03 | Clasificar si un mensaje es accionable (compuerta) | Inference |
| RF-04 | Extraer tipo de evento, servicio de respuesta y ubicación literal | Inference |
| RF-05 | Resolver la ubicación a barrio/comuna de forma determinista | Geo |
| RF-06 | Persistir y consultar los reportes estructurados | CRUD |
| RF-07 | Mostrar al operador los reportes con su mensaje original | Frontend |
| RF-08 | Evaluar el modelo contra el gold standard con métricas por campo | Pipeline Azure ML: componente de evaluación |
| RF-09 | Comparar al menos 2 modelos candidatos con el mismo corpus y prompt | Pipeline Azure ML: evaluaciones en paralelo |
| RF-10 | Registrar cada evaluación (parámetros, métricas, artefactos) | MLflow en el workspace de Azure ML |
| RF-11 | Versionar la configuración ganadora (modelo, hash de prompts, ontología) | Registro de modelos de Azure ML |
| RF-12 | Desplegar en la app la configuración registrada | Script de despliegue en la VM |

### Requerimientos no funcionales

| ID | Requerimiento | Meta verificable |
| --- | --- | --- |
| RNF-01 | Latencia de procesamiento | p95 del pipeline de 2 etapas medido en la evaluación y reportado en Studio |
| RNF-02 | Reproducibilidad | Corpus con versión y checksum; entorno de ejecución versionado; semilla fija |
| RNF-03 | Trazabilidad | Cada registro muestra el mensaje original anonimizado; cada modelo registrado apunta al job que lo evaluó |
| RNF-04 | Seguridad de secretos | `GROQ_API_KEY` y token de Telegram fuera del código: Key Vault o `.env` con permisos 600 en la VM |
| RNF-05 | Exposición mínima | Solo el puerto 8501 (tablero) y 22 (SSH) abiertos, y solo desde la IP del equipo |
| RNF-06 | Costo | Cómputo de Azure ML que escala a 0; VM apagada fuera de pruebas; alerta de presupuesto |
| RNF-07 | Privacidad | Nombres y teléfonos nunca salen hacia Groq (ya garantizado por Process) |

### Restricciones

- Azure for Students: regiones limitadas por política, máximo 3 IP públicas, cuota baja de vCPU y posible escasez de capacidad.
- Sin GPU y sin entrenamiento (constitución del proyecto): un modelo de 20B parámetros no se puede servir en CPU dentro de Azure ML, así que la inferencia sigue vía API.
- Dependencia externa de Groq: cuota del plan gratuito y límites de peticiones por minuto.
- Datos sintéticos: no hay mensajes reales anotados.
- Tiempo: trabajo en pareja con sustentación individual.

## Alternativas de solución y selección

Se seleccionan tres cosas por separado: cómo se usa Azure ML, dónde corre el LLM y dónde corren los microservicios. La combinación elegida es A2 + L1 + H1, con A3 como extra si sobra tiempo.

### Decisión A: cómo se usa Azure Machine Learning

| Opción | Qué es | A favor | En contra | Decisión |
| --- | --- | --- | --- | --- |
| A1. Solo tracking | Apuntar `MLFLOW_TRACKING_URI` al workspace y correr la evaluación desde un PC | Cambio mínimo | Azure ML queda como base de datos de métricas; no hay pipeline ni componentes, y el enunciado los pide | Descartada como solución única (queda incluida en A2) |
| A2. Pipeline de evaluación y registro | Pipeline con componentes: validar corpus → evaluar 2 modelos en paralelo → comparar → registrar la configuración ganadora | Usa Data assets, Environments, Compute, Components, Pipelines, MLflow y Model Registry; reutiliza el harness existente; respeta "sin entrenamiento" | Depende de Groq dentro del job; hay que manejar el secreto | **Seleccionada** |
| A3. Línea base clásica en Designer | Pipeline en Designer con componentes clásicos: Preprocess Text → Extract N-Gram Features from Text → Split Data → Train Model (Multiclass Logistic Regression) → Score Model → Evaluate Model, para predecir `tipo_evento` | Usa directamente la referencia de componentes del enunciado; responde "¿hace falta un LLM?" | Con corpus por plantillas el clásico puede salir casi perfecto y engañar; solo cubre un campo; los componentes clásicos ya no reciben novedades | **Extra opcional**, presentado como comparación y no como producto |
| A4. Endpoint en línea gestionado para Inference | Servir el servicio Inference como Managed Online Endpoint | Muestra despliegue en Azure ML | El endpoint solo envolvería una llamada a Groq; consume cuota (mínimo 1 instancia + 20 % reservado) y cobra 24/7 | Descartada |
| A5. Endpoint por lotes | Batch endpoint que procesa un archivo de mensajes históricos | Escala a 0; caso real (reprocesar un día de mensajes) | Más configuración; no suma nota si A2 ya está completo | Extra si sobra tiempo |

### Decisión L: dónde corre el LLM

| Opción | A favor | En contra | Decisión |
| --- | --- | --- | --- |
| L1. Groq (actual) | Ya integrado y probado; `gpt-oss-20b` cuesta del orden de USD 0,10 por millón de tokens de entrada y 0,50 de salida | Dependencia externa; datos (ya anonimizados) salen de Azure | **Seleccionada. Confirmada por el profesor el 2026-09-26**: se acepta que el LLM se sirva desde Groq mientras la evaluación, la comparación, el registro y el despliegue viven en Azure ML |
| L2. Modelo en Azure AI Foundry (por ejemplo gpt-oss) | Todo dentro de Azure; misma familia de modelo | Las suscripciones de estudiante suelen no tener cuota para desplegar modelos; habría que escribir un `ProveedorAzure` | **Descartada.** No se planifica ni se implementa. Quedó sin uso al confirmarse L1 el 2026-09-26 |
| L3. Modelo pequeño servido en CPU en Azure ML | Sin dependencia externa | Contradice la constitución; un modelo que quepa en CPU no rinde en extracción estructurada; latencia alta | Descartada |

### Decisión H: dónde corren los microservicios

| Opción | A favor | En contra | Decisión |
| --- | --- | --- | --- |
| H1. 1 VM Ubuntu + Docker Compose | Es la práctica IaaS del curso; 1 IP pública; `docker-compose.yml` ya existe; se apaga cuando no se usa | Un solo punto de falla; escalado manual | **Seleccionada** |
| H2. AKS (Microproyecto 2) | Reutiliza lo aprendido; escalado y monitoreo | Nodos de sistema consumen vCPU que Azure ML también necesita; hay que escribir manifiestos para 7 servicios | Evolución a producción |
| H3. Azure Container Apps | Escala a 0, sin administrar VM | Servicio nuevo fuera del temario; 7 apps y red interna que configurar | Descartada por tiempo |

Criterios usados para seleccionar, en orden: cumple lo que pide el enunciado, cabe en la cuota y el crédito de estudiante, reutiliza código existente, se puede explicar individualmente en la sustentación.

## Pipeline de Azure Machine Learning propuesto

El pipeline tiene 4 componentes y corre en un clúster de cómputo que escala de 0 a 1 nodo; solo la configuración con mejor F1 llega al registro de modelos.

```text
Diagrama (texto): pipeline sirena-eval en cluster cpu-sirena (0-1 nodos)

Data asset gold_v1 --> validar_corpus (checksum SHA-256, entrega eval.jsonl)
                          |--> evaluar_modelo [gpt-oss-20b]  (F1 por campo, p95) --+
                          |--> evaluar_modelo [gpt-oss-120b] (F1 por campo, p95) --+--> comparar_modelos (regla: F1 macro, desempate: costo)
                                                                                         --> registrar_config (modelo + prompts + ontologia) --> Model registry: sirena-extractor
Ambas evaluaciones llaman a la API de Groq. Cada paso registra en MLflow del workspace.
Activos del workspace: Data asset gold_v1, Environment sirena-eval, Key Vault (GROQ_API_KEY), MLflow tracking, Model registry.
```

| Componente | Entrada | Salida | Código que ejecuta |
| --- | --- | --- | --- |
| `validar_corpus` | Data asset `gold_v1` (carpeta con `eval.jsonl`, `dev.jsonl`, `README_gold_v1.md`) | `eval.jsonl` validado + `manifest.json` con conteos | Script nuevo: recalcula SHA-256 y lo compara con el README; falla el job si no coincide |
| `evaluar_modelo` (×2, en paralelo) | `eval.jsonl`, parámetro `modelo`, parámetro `limite` | `evaluacion.md`, `metricas.json` | `python -m inference.evaluacion` del repo, con `INFERENCE_MODELO` fijado por parámetro; `registro.py` publica parámetros, métricas y artefactos en MLflow |
| `comparar_modelos` | Los dos `metricas.json` | `decision.json` (ganador y razón) | Script nuevo: gana el mayor F1 macro de `tipo_evento` y `es_reporte_accionable`; si la diferencia es menor a 2 puntos gana el más barato (20b) |
| `registrar_config` | `decision.json` + `config/ontologia.yaml` | Modelo `sirena-extractor:N` en el registro | Script nuevo: registra un modelo de tipo `custom_model` con la ontología y los prompts, y tags `modelo`, `f1_tipo_evento`, `latencia_p95_ms`, `prompt_hash`, `job_id` |

Por qué esto cuenta como pipeline de Azure ML aunque no haya entrenamiento: el modelo es preentrenado, así que el ciclo de MLOps es evaluar → comparar → versionar → desplegar. Cada ejecución es reproducible (misma versión del corpus, del entorno y del código) y queda auditada en Studio.

**Extra opcional (Designer, componentes clásicos de la referencia del enunciado):** Import Data (`gold_v1` como tabla) → Select Columns in Dataset (`texto`, `tipo_evento`) → Preprocess Text → Extract N-Gram Features from Text → Split Data (70/30) → Train Model con Multiclass Logistic Regression → Score Model → Evaluate Model. Se compara su exactitud en `tipo_evento` con la del LLM, advirtiendo que el corpus por plantillas favorece al modelo clásico. Antes hay que convertir el JSONL a CSV plano con solo los mensajes accionables.

## Cálculo aproximado de costos

El demo cuesta del orden de USD 12 en dos semanas si la VM se apaga fuera de las pruebas; operando 24/7 sería del orden de USD 45 al mes más el consumo de Groq. Precios de lista en `eastus`, Linux, pago por uso; el único verificado contra la API de precios de Azure es la B2s, el resto son aproximados y hay que confirmarlos en la calculadora.

| Recurso | Tamaño o SKU | Precio unitario (USD) | Demo: 2 semanas | Operación 24/7: mes |
| --- | --- | --- | --- | --- |
| VM de microservicios | Standard\_B2s (2 vCPU, 4 GB) | 0,0416 / hora ([precio de lista](https://prices.azure.com/api/retail/prices?$filter=armRegionName%20eq%20%27eastus%27%20and%20armSkuName%20eq%20%27Standard_B2s%27%20and%20priceType%20eq%20%27Consumption%27)) | 2,3 (56 h: 4 h/día) | 30,4 (730 h) |
| Disco del SO | Standard SSD 32 GB | ≈ 2,4 / mes (se cobra aunque la VM esté apagada) | 1,2 | 2,4 |
| IP pública | Standard, estática | ≈ 0,005 / hora | 1,8 | 3,7 |
| Workspace de Azure ML | — | Sin costo propio | 0 | 0 |
| Clúster de cómputo | Standard\_DS2\_v2, mín. 0 nodos | ≈ 0,15 / hora solo mientras corre | 0,9 (≈ 6 h de jobs) | 0,6 (1 evaluación semanal) |
| Container Registry | Basic (se crea al construir el primer Environment) | ≈ 0,17 / día | 2,3 | 5,0 |
| Storage + Key Vault + Application Insights | Creados con el workspace | Centavos por GB y por operación | < 1 | ≈ 1 |
| Groq, evaluaciones | gpt-oss-20b ≈ 0,10 entrada / 0,50 salida por millón de tokens | ≈ 0,25 por corrida de 340 mensajes con 20b; algo más con 120b | ≈ 3 (≈ 6 corridas) | ≈ 2 |
| **Total aproximado** |  |  | **≈ 12** | **≈ 45 + tráfico real en Groq** |

Supuestos del cálculo de Groq: unas 680 llamadas por corrida (2 etapas × 340 mensajes), del orden de 1,5 mil tokens de entrada por llamada porque el prompt incluye la ontología, y salida inflada por los tokens de razonamiento de gpt-oss. El plan gratuito de Groq puede cubrirlo, pero sus límites de peticiones por minuto alargan la corrida.

Para el entregable: armar el mismo escenario en la [calculadora de precios](https://azure.microsoft.com/es-es/pricing/calculator/) (Virtual Machines, Azure Machine Learning con el tamaño del clúster y horas, Container Registry, Storage, IP pública), exportarlo y adjuntarlo. Mostrar en la presentación las dos columnas: demo y operación.

Controles de costo: presupuesto con alerta al 50 % y 80 % del crédito, `min_instances: 0` y `idle_time_before_scale_down: 120` en el clúster, `az vm deallocate` al terminar cada sesión, y borrado del grupo de recursos después de la sustentación.

## 2. Propuesta de diseño (25 %)

Dos zonas en la misma región y el mismo grupo de recursos: una VM que opera SIRENA en tiempo real y un workspace de Azure ML que decide, con evidencia, qué modelo usa esa VM.

```text
Diagrama (texto): arquitectura

[Telegram] --long polling--> telegram-source --> BFF :8000 <-- Frontend :8501 <-- [Operador PMU, navegador, puerto 8501]
BFF --> Process :8002 ; BFF --> CRUD :8001 (proxy de lecturas)
Process --> Inference :8003 --HTTPS--> [API Groq, gpt-oss-20b / 120b]
Process --> Geo :8004 (barrio y comuna) ; Process --> CRUD :8001 (SQLite en volumen)
Todo lo anterior (menos Telegram, Groq y el operador) corre en: VM Ubuntu 22.04, B2s, Docker Compose. NSG: solo 22 y 8501 desde la IP del equipo.

Workspace de Azure ML: Data asset gold_v1, Model registry sirena-extractor, MLflow tracking, Pipeline job sirena-eval (llama a Groq).
Model registry --desplegar_config.sh fija INFERENCE_MODELO--> Inference (en la VM)
```

La línea resaltada es la que une las dos zonas: el script de despliegue lee la última versión de `sirena-extractor` en el registro y fija `INFERENCE_MODELO` en el `.env` de la VM antes de reiniciar el contenedor de Inference. Todo el tráfico entre microservicios es HTTP interno de la red de Docker; solo el tablero queda expuesto.

## Relación, flujo y descripción de los componentes

Hay dos flujos: el operativo, que procesa cada mensaje en segundos, y el de MLOps, que se corre cuando cambia el modelo, el prompt o la ontología.

### Flujo operativo (por mensaje)

1. Un ciudadano escribe al bot; `telegram-source` lo recoge por long polling y llama `POST /mensajes` en BFF.
2. BFF descarta reintentos exactos, responde `202` y dispara `POST /procesar` en Process sin esperar.
3. Process anonimiza el texto y llama `POST /compuerta` en Inference; si el mensaje no es accionable, termina ahí.
4. Si es accionable, Process llama `POST /extraccion` en Inference, que usa el modelo fijado por `INFERENCE_MODELO`.
5. Process llama a Geo para resolver barrio y comuna, marca posibles duplicados y persiste en CRUD.
6. El operador ve el registro en el tablero (Frontend → BFF → CRUD) junto al mensaje original anonimizado.

### Flujo de MLOps (por cambio)

1. Se sube una nueva versión del corpus como Data asset, o se cambia prompt u ontología en el repo.
2. Se lanza el pipeline `sirena-eval` (`az ml job create`), que valida el corpus y evalúa los modelos candidatos en paralelo.
3. Cada evaluación registra parámetros, métricas y artefactos en MLflow del workspace.
4. `comparar_modelos` elige el ganador y `registrar_config` crea la versión `sirena-extractor:N`.
5. En la VM, `desplegar_config.py` lee esa versión y reinicia solo el contenedor de Inference con el nuevo modelo.

### Descripción de los componentes

| Componente | Servicio de Azure | Función | Se relaciona con |
| --- | --- | --- | --- |
| Grupo de recursos `rg-sirena-mp3` | Resource Group | Agrupa todo para costos y borrado final | Todos |
| VM `vm-sirena` | Virtual Machines (IaaS) | Ejecuta los 7 contenedores con Docker Compose | IP pública, NSG, disco, Azure ML (lectura del registro) |
| NSG e IP pública | Virtual Network | Expone solo 8501 y 22 a la IP del equipo | VM |
| Identidad administrada de la VM | Microsoft Entra ID | Permite a la VM leer el registro de modelos sin guardar credenciales | Workspace (rol AzureML Data Scientist o Reader) |
| Workspace `mlw-sirena` | Azure Machine Learning | Contenedor de datos, entornos, cómputo, jobs, MLflow y modelos | Storage, Key Vault, App Insights, ACR |
| Data asset `gold_v1` | Azure ML Data (`uri_folder`) | Corpus versionado para evaluar | `validar_corpus` |
| Environment `sirena-eval` | Azure ML Environments (sobre ACR) | Imagen Docker con Python 3.12, uv y el paquete `inference` | Los 4 componentes |
| Compute cluster `cpu-sirena` | Azure ML Compute | Ejecuta los jobs; 0 nodos en reposo | Pipeline |
| Componentes y pipeline `sirena-eval` | Azure ML Components / Pipelines | Validar, evaluar, comparar y registrar | Data asset, MLflow, Model registry, Groq |
| MLflow tracking | Azure ML (MLflow nativo) | Guarda cada corrida y permite compararlas en Studio | Harness `inference.evaluacion` |
| Model registry `sirena-extractor` | Azure ML Models | Versiona la configuración ganadora con sus métricas | VM (despliegue) |
| Key Vault | Azure Key Vault (del workspace) | Guarda `GROQ_API_KEY` para los jobs | Clúster con identidad administrada |
| Storage Account | Azure Storage (del workspace) | Guarda datos, artefactos y logs de los jobs | Workspace |
| Application Insights | Azure Monitor (del workspace) | Telemetría del workspace | Workspace |
| Groq | Externo | Sirve gpt-oss-20b y gpt-oss-120b | Inference y `evaluar_modelo` |

## 3. Implementación del demo (30 %)

Diez fases en orden; cada una termina con una verificación concreta. Todos los comandos se corren en Azure Cloud Shell (bash). Los nombres (`rg-sirena-mp3`, `mlw-sirena`, `cpu-sirena`, `vm-sirena`) son sugeridos y se usan igual en todo el plan.

### Fase 0 — Preparar la suscripción

```bash
az extension add --name ml --upgrade
az account show --query name -o tsv
# Regiones permitidas por la politica (guia de regiones del curso)
SUB=$(az account show --query id -o tsv)
az policy assignment show --name sys.regionrestriction --scope /subscriptions/$SUB \
  --query "parameters.listOfAllowedLocations.value" -o tsv
# Cuota de vCPU por familia en la region elegida
az vm list-usage --location eastus -o table
# Proveedores que pueden no estar registrados en suscripciones de estudiante
for p in Microsoft.MachineLearningServices Microsoft.ContainerRegistry Microsoft.KeyVault Microsoft.Insights Microsoft.Storage; do az provider register --namespace $p; done
az group create --name rg-sirena-mp3 --location eastus
# Permisos del compañero, acotados al grupo de recursos (cambia permisos, no crea
# recursos: requiere confirmacion explicita). Solo dentro del directorio uao.edu.co.
az role assignment create --assignee <correo-uao-del-companero> --role Contributor --scope $(az group show --name rg-sirena-mp3 --query id -o tsv)
```

Verificación: el grupo responde `Succeeded` y hay al menos 4 vCPU libres entre las familias BS (VM) y DSv2 o DAv4 (clúster). Si no, cambiar de región permitida o de suscripción (ver Riesgos). Crear en el portal un presupuesto en Cost Management con alertas al 50 % y 80 %. La asignación de rol se verifica con `az role assignment list --scope $(az group show --name rg-sirena-mp3 --query id -o tsv) --query "[].{principal:principalName, rol:roleDefinitionName}" -o table`, donde debe aparecer el correo del compañero con rol `Contributor` y ningún otro alcance.

### Fase 1 — Workspace de Azure ML

```bash
az ml workspace create --name mlw-sirena --resource-group rg-sirena-mp3 --location eastus
az configure --defaults group=rg-sirena-mp3 workspace=mlw-sirena location=eastus
az ml workspace show --query mlflow_tracking_uri -o tsv   # guardar este URI
az ml compute list-usage -o table                         # cuota propia de Azure ML
```

Verificación: el workspace abre en [ml.azure.com](https://ml.azure.com) y el grupo contiene Storage, Key Vault y Application Insights creados automáticamente.

### Fase 2 — Data asset del corpus

`azureml/data/gold_v1.yml`:

```yaml
$schema: https://azuremlschemas.azureedge.net/latest/data.schema.json
name: gold_v1
version: 1
type: uri_folder
path: ../../eval-prompt/corpus/gold_v1
description: Gold standard v1 de SIRENA, 400 mensajes congelados el 2026-09-10 (60 dev, 340 eval)
tags: {sintetico: "si", checksum_eval: "20c53e5a6efb"}
```

```bash
az ml data create --file azureml/data/gold_v1.yml
```

Verificación: Studio → Data muestra `gold_v1` versión 1 con los tres archivos.

### Fase 3 — Environment de ejecución

Generar las dependencias exactas desde el lock del repo (en el PC o en Cloud Shell con uv instalado):

```bash
uv export --package inference --no-dev --no-hashes --no-emit-workspace > azureml/env/requirements.txt
```

`azureml/env/Dockerfile`:

```dockerfile
FROM python:3.12-slim
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt azureml-mlflow azure-identity azure-keyvault-secrets pyyaml
```

`azureml/env/environment.yml`:

```yaml
$schema: https://azuremlschemas.azureedge.net/latest/environment.schema.json
name: sirena-eval
version: 1
build:
  path: .
```

```bash
az ml environment create --file azureml/env/environment.yml
```

Verificación: Studio → Environments → `sirena-eval` termina el build en estado Succeeded (la primera vez crea el Container Registry). Riesgo conocido: `azureml-mlflow` puede no ser compatible con `mlflow>=3.16.1`; si el build o el tracking fallan, fijar en `requirements.txt` la versión de mlflow que indique `pip install azureml-mlflow` como compatible.

### Fase 4 — Cómputo y secreto

```bash
az ml compute create --name cpu-sirena --type AmlCompute --size Standard_DS2_v2 \
  --min-instances 0 --max-instances 2 --idle-time-before-scale-down 120 --identity-type SystemAssigned

KV=$(az ml workspace show --query key_vault -o tsv | awk -F/ '{print $NF}')
az keyvault secret set --vault-name $KV --name groq-api-key --value "<GROQ_API_KEY>"

# Permiso de lectura del secreto para la identidad del cluster
PID=$(az ml compute show --name cpu-sirena --query identity.principal_id -o tsv)
az keyvault set-policy --name $KV --object-id $PID --secret-permissions get
# Si el Key Vault usa RBAC: az role assignment create --assignee $PID --role "Key Vault Secrets User" --scope <id del Key Vault>
```

Con `--max-instances 2` las dos evaluaciones corren en paralelo; si la cuota no alcanza, dejar 1 y correrán una tras otra. Si `Standard_DS2_v2` no está disponible, probar `Standard_D2as_v4` o `Standard_DS1_v2`. Plan B del secreto si la identidad da problemas: pasar la clave como variable de entorno al lanzar el job y rotarla después de la sustentación (queda visible para quien lea el job).

### Fase 5 — Componentes y pipeline

Crear `azureml/components/` con los 4 YAML y `azureml/src/` con los scripts (detalle en la sección de cambios al repositorio). Ejemplo del componente de evaluación:

```yaml
$schema: https://azuremlschemas.azureedge.net/latest/commandComponent.schema.json
name: sirena_evaluar_modelo
display_name: Evaluar modelo SIRENA
version: 1
type: command
inputs:
  corpus: {type: uri_folder}
  modelo: {type: string, default: openai/gpt-oss-20b}
  limite: {type: integer, default: 340}
  key_vault_url: {type: string}
outputs:
  resultados: {type: uri_folder}
code: ../..
environment: azureml:sirena-eval@latest
environment_variables:
  KEY_VAULT_URL: ${{inputs.key_vault_url}}
  AZURE_TOKEN_CREDENTIALS: ManagedIdentityCredential
command: >-
  export PYTHONPATH=backend/inference:common/sirena-schema &&
  export INFERENCE_MODELO=${{inputs.modelo}} &&
  python azureml/src/evaluar.py --corpus ${{inputs.corpus}}/gold_v1/eval.jsonl
  --limite ${{inputs.limite}} --salida ${{outputs.resultados}}
```

La clave **no viaja por el comando**. `evaluar.py` la resuelve en el propio proceso: si `GROQ_API_KEY` ya está en el entorno (corrida local) la usa tal cual; si no, y hay `KEY_VAULT_URL`, lee el secreto `groq-api-key` del Key Vault con `SecretClient` + `DefaultAzureCredential` y lo escribe en `os.environ["GROQ_API_KEY"]` **sin imprimirlo**. Sin sustitución de shell, porque un `export GROQ_API_KEY=$(...)` deja la clave en el log del job, que se conserva y ve cualquiera con acceso al workspace.

`AZURE_TOKEN_CREDENTIALS=ManagedIdentityCredential` fija la credencial de forma explícita, como recomienda la documentación para producción, en vez de dejar que `DefaultAzureCredential` resuelva por su cuenta.

Las referencias `${{keyvault:...}}` **no** se usan: son solo para online endpoints y deployments, no para command ni pipeline jobs, y el Environment no admite variables de entorno con referencias a secretos.

`azureml/pipeline.yml`:

```yaml
$schema: https://azuremlschemas.azureedge.net/latest/pipelineJob.schema.json
type: pipeline
experiment_name: sirena-evaluacion
display_name: sirena-eval
settings:
  default_compute: azureml:cpu-sirena
inputs:
  gold: {type: uri_folder, path: azureml:gold_v1@latest}
  limite: 340
jobs:
  validar:
    component: ./components/validar_corpus.yml
    inputs: {gold: ${{parent.inputs.gold}}}
  evaluar_20b:
    component: ./components/evaluar_modelo.yml
    inputs:
      corpus: ${{parent.jobs.validar.outputs.corpus_validado}}
      modelo: openai/gpt-oss-20b
      limite: ${{parent.inputs.limite}}
  evaluar_120b:
    component: ./components/evaluar_modelo.yml
    inputs:
      corpus: ${{parent.jobs.validar.outputs.corpus_validado}}
      modelo: openai/gpt-oss-120b
      limite: ${{parent.inputs.limite}}
  comparar:
    component: ./components/comparar_modelos.yml
    inputs:
      resultados_a: ${{parent.jobs.evaluar_20b.outputs.resultados}}
      resultados_b: ${{parent.jobs.evaluar_120b.outputs.resultados}}
  registrar:
    component: ./components/registrar_config.yml
    inputs: {decision: ${{parent.jobs.comparar.outputs.decision}}}
```

Agregar `azureml/.amlignore` (o `.amlignore` en la raíz) para no subir `.git`, `frontend/`, `tests/`, `.venv/` ni `eval-prompt/annotation/` como código de los componentes.

### Fase 6 — Correr y depurar el pipeline

```bash
# Corrida corta para depurar: 5 mensajes por modelo
az ml job create --file azureml/pipeline.yml --set inputs.limite=5 --web
# Corrida completa cuando la corta termina en verde
az ml job create --file azureml/pipeline.yml --web
```

Verificación: el grafo muestra los 5 pasos en verde; Jobs → `sirena-evaluacion` tiene las corridas con métricas `f1_tipo_evento`, `exactitud_es_reporte_accionable`, `latencia_p95_ms`; se pueden seleccionar las dos evaluaciones y usar Compare; Models muestra `sirena-extractor` versión 1 con sus tags. Guardar capturas de cada vista para las diapositivas.

### Fase 7 — VM de microservicios

```bash
MI_IP=$(curl -s https://ifconfig.me)   # desde el PC del equipo, no desde Cloud Shell
az vm create --resource-group rg-sirena-mp3 --name vm-sirena --image Ubuntu2204 \
  --size Standard_B2s --admin-username azureuser --generate-ssh-keys \
  --public-ip-sku Standard --assign-identity
az network nsg rule update -g rg-sirena-mp3 --nsg-name vm-sirenaNSG -n default-allow-ssh \
  --source-address-prefixes $MI_IP/32
az network nsg rule create -g rg-sirena-mp3 --nsg-name vm-sirenaNSG -n allow-streamlit \
  --priority 1010 --protocol Tcp --destination-port-ranges 8501 --source-address-prefixes $MI_IP/32

# Permiso de la VM para leer el registro de modelos
VM_PID=$(az vm show -g rg-sirena-mp3 -n vm-sirena --query identity.principalId -o tsv)
az role assignment create --assignee $VM_PID --role "AzureML Data Scientist" \
  --scope $(az ml workspace show --query id -o tsv)
```

Dentro de la VM (`ssh azureuser@<IP>`):

```bash
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER && newgrp docker
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash && az extension add --name ml
git clone https://github.com/Juanxo17/pmu-structured-extraction.git && cd pmu-structured-extraction
cp .env.example .env && chmod 600 .env   # completar GROQ_API_KEY, TELEGRAM_BOT_TOKEN, INFERENCE_MODELO
docker compose up -d --build bff telegram-source crud process inference geo frontend
curl -s localhost:8000/health; curl -s localhost:8003/health
```

Verificación: el tablero abre en `http://<IP pública>:8501` desde el PC del equipo y no abre desde otra red (datos móviles). Si se generaron las llaves SSH en Cloud Shell, conectarse desde Cloud Shell; desde Windows usar `ssh-keygen` y pasar `--ssh-key-values` al crear la VM.

### Fase 8 — Cerrar el ciclo: la VM usa el modelo registrado

```bash
# En la VM: azureml/scripts/desplegar_config.sh
az login --identity
V=$(az ml model list -n sirena-extractor -g rg-sirena-mp3 -w mlw-sirena --query "max_by(@, &to_number(version)).version" -o tsv)
MODELO=$(az ml model show -n sirena-extractor --version $V -g rg-sirena-mp3 -w mlw-sirena --query tags.modelo -o tsv)
sed -i "s|^INFERENCE_MODELO=.*|INFERENCE_MODELO=$MODELO|" .env
docker compose up -d inference
echo "Inference usa $MODELO (sirena-extractor:$V)"
```

Verificación: `docker compose exec inference env | grep INFERENCE_MODELO` muestra el modelo ganador. Para que esto funcione, el servicio `inference` del Compose debe leer `INFERENCE_MODELO` (cambio al repositorio).

### Fase 9 — Extras opcionales y apagado

- **Designer (línea base clásica):** convertir los mensajes accionables a CSV (`texto`, `tipo_evento`), crearlo en Studio como Data asset tabular, armar en Designer el pipeline de la sección de Pipeline y correrlo en `cpu-sirena`. Capturar la salida de Evaluate Model.
- **Endpoint por lotes:** desplegar `sirena-extractor` en un batch endpoint que reciba un archivo de mensajes. Solo si todo lo anterior está listo.
- **Apagado diario:** `az vm deallocate -g rg-sirena-mp3 -n vm-sirena`. El clúster baja solo a 0 nodos.
- **Después de la sustentación:** `az group delete -n rg-sirena-mp3 --yes --no-wait`, rotar la clave de Groq y revocar el token del bot con BotFather.

## Cambios que hay que hacer en el repositorio

Los cambios son aditivos: una carpeta `azureml/` nueva, dos ajustes pequeños en archivos existentes y ninguno en la lógica de los microservicios. Según `AGENTS.md`, van en una rama `feature/azureml-pipeline` con PR, pruebas y docstrings estilo Google.

| Archivo | Tipo | Qué hace |
| --- | --- | --- |
| `azureml/data/gold_v1.yml` | Nuevo | Define el Data asset del corpus |
| `azureml/env/Dockerfile`, `environment.yml`, `requirements.txt` | Nuevo | Environment `sirena-eval` (requirements generado con `uv export`) |
| `azureml/components/validar_corpus.yml` + `azureml/src/validar_corpus.py` | Nuevo | Recalcula SHA-256 de `eval.jsonl` y `dev.jsonl`, los compara con `README_gold_v1.md` y copia `eval.jsonl` a la salida |
| `azureml/components/evaluar_modelo.yml` + `azureml/src/evaluar.py` | Nuevo | Envoltorio de `inference.evaluacion`: reutiliza `cargar_corpus`, `EvaluadorPrompts`, `metricas_por_campo`, `generar_informe` y `registrar_corrida`, y además escribe `metricas.json` (con `dataclasses.asdict`) en la salida, **más la clave `"modelo"`**: el job `comparar` solo recibe las dos carpetas de resultados, así que el desempate por costo no se puede aplicar si el artefacto no dice qué modelo midió. Antes de construir el proveedor resuelve la clave: usa `GROQ_API_KEY` del entorno si está, y si no lee `groq-api-key` del Key Vault con `SecretClient` + `DefaultAzureCredential` y la escribe en `os.environ` sin imprimirla |
| `azureml/components/comparar_modelos.yml` + `azureml/src/comparar.py` | Nuevo | Lee los dos `metricas.json`, aplica la regla de selección y escribe `decision.json` |
| `azureml/components/registrar_config.yml` + `azureml/src/registrar.py` | Nuevo | Registra `sirena-extractor` con `mlflow.pyfunc.log_model` (artefactos: ontología, `decision.json`, hashes de prompts) y le pone tags `modelo`, `f1_tipo_evento`, `latencia_p95_ms`, `prompt_hash` |
| `azureml/pipeline.yml`, `azureml/.amlignore` | Nuevo | Pipeline y exclusiones de subida |
| `azureml/scripts/desplegar_config.sh` | Nuevo | Fase 8: fija el modelo registrado en la VM |
| `.gitattributes` | Nuevo | Fuerza `eol=lf` en `eval-prompt/corpus/**/*.jsonl` para que el SHA-256 del corpus coincida con `README_gold_v1.md` en cualquier sistema operativo. Decisión del equipo ante el hallazgo H1 de `PROGRESO.md` |
| `docker-compose.yml` | Ajuste | En `inference`, agregar `INFERENCE_MODELO=${INFERENCE_MODELO:-openai/gpt-oss-20b}`; opcional: sacar `mlflow` a un perfil (`profiles: [local]`) para que no arranque en la VM |
| `backend/inference/inference/registro.py` | Ajuste | Hecho en A4: dentro del job sí se rechaza el experimento, así que no se llama `mlflow.set_experiment` cuando existe `MLFLOW_RUN_ID` (Azure ML ya fija el run y el experimento del job). El arreglo resultó ser de una línea porque `mlflow.start_run()` ya retoma la corrida existente por su cuenta |
| `tests/azureml/` | Nuevo | Pruebas de `comparar.py` (regla y desempate) y `validar_corpus.py` (checksum correcto e incorrecto), con patrón AAA |
| `docs/AZURE.md` y `docs/trabajo_futuro.md` | Docs | Guía de despliegue y actualización del estado de MLflow |

Regla de selección que implementa `comparar.py`, para escribirla igual en la presentación: gana el modelo con mayor promedio de `f1` de `tipo_evento` y `es_reporte_accionable`; si la diferencia es **menor a** 0,02 (estricto: a exactamente 0,02 ya gana el mayor), gana `gpt-oss-20b` por costo y latencia. El desempate está anclado a ese modelo por nombre y no a "el más barato de los dos", para que la regla no cambie de significado si cambian los candidatos; si hay empate y ninguno es `gpt-oss-20b`, el job falla en vez de elegir al azar. Ojo: las métricas están anidadas en `campos: list[MetricaCampo]`, no como claves planas `f1_tipo_evento`. La regla es una decisión del equipo: conviene acordarla antes de ver los resultados.

## 4. Presentación (25 %)

Quince minutos con el demo en el centro: 5 de contexto y diseño, 7 de demo en vivo y 3 de costos, cierre y preguntas. Como la sustentación es individual, cada integrante ensaya el guion completo, no solo su mitad.

| Minuto | Bloque | Qué se muestra | Criterio que cubre |
| --- | --- | --- | --- |
| 0:00–1:30 | Problema y cliente | El PMU, el caso del 10 de agosto, un mensaje real de ejemplo sin estructura | Requerimientos |
| 1:30–3:00 | Requerimientos y restricciones | Tabla corta de RF y RNF clave; límites de Azure for Students | Requerimientos |
| 3:00–4:00 | Alternativas y selección | Las 3 decisiones (Azure ML, LLM, hosting) con la opción elegida y por qué | Requerimientos |
| 4:00–5:30 | Diseño | Diagrama de arquitectura y diagrama del pipeline; los dos flujos | Diseño |
| 5:30–8:30 | Demo 1: Azure ML | Grafo del pipeline en verde, comparación de las dos evaluaciones, modelo `sirena-extractor` con tags | Demo |
| 8:30–11:00 | Demo 2: app en vivo | Mensaje enviado al bot desde el celular → aparece en el tablero con tipo de evento y comuna; `desplegar_config.sh` mostrando el modelo tomado del registro | Demo |
| 11:00–12:30 | Costos | Tabla demo vs. operación y captura de la calculadora | Requerimientos |
| 12:30–13:30 | Limitaciones y evolución | Corpus sintético, dependencia de Groq, evolución a AKS y a Azure SQL | Presentación |
| 13:30–15:00 | Preguntas | — | Presentación |

Preparación del demo para que no falle en vivo:

- Correr el pipeline completo el día anterior y dejar sus resultados abiertos en pestañas; en vivo solo lanzar una corrida con `limite=5` para mostrar que arranca.
- Encender la VM 20 minutos antes (`az vm start`) y verificar `/health` de los servicios.
- Tener 3 mensajes de prueba listos: uno accionable con barrio conocido, uno no accionable (pregunta o rumor) y uno con ubicación ambigua. Los tres muestran decisiones distintas del sistema.
- Si la IP del salón cambia, actualizar la regla del NSG con la nueva IP antes de empezar.
- Grabar un video de 3 minutos del demo completo como respaldo por si falla la red o Groq.

Preguntas probables y respuesta corta:

- **¿Dónde está el machine learning si no entrenan?** En la evaluación, comparación, trazabilidad y versionado del modelo: el ciclo de MLOps de un modelo preentrenado. El extra de Designer muestra además un modelo entrenado como línea base.
- **¿Por qué no un endpoint en línea de Azure ML?** Envolvería una llamada a Groq, cobraría 24/7 y consumiría cuota sin aportar funcionalidad.
- **¿Qué pasa con los datos al apagar la VM?** La base SQLite vive en un volumen Docker sobre el disco administrado, que persiste al desasignar la VM (misma pregunta de la práctica REST + MySQL).
- **¿Cómo protegen datos personales?** Process anonimiza antes de llamar a Groq y antes de persistir; las credenciales van en Key Vault o en `.env` con permisos 600.

## Lista de verificación de entrega

En orden de ejecución; lo marcado como extra no bloquea la entrega.

- [ ] Regiones permitidas, cuota de vCPU y proveedores verificados (Fase 0)
- [ ] Presupuesto con alertas creado
- [ ] Workspace `mlw-sirena` creado y URI de MLflow guardado
- [ ] Data asset `gold_v1` registrado
- [ ] Environment `sirena-eval` construido
- [ ] Clúster `cpu-sirena` con identidad y acceso al secreto de Groq
- [ ] Rama `feature/azureml-pipeline` con componentes, scripts y pruebas; PR con `pytest` y `ruff` en verde
- [ ] Pipeline con `limite=5` en verde
- [ ] Pipeline completo en verde, comparación en Studio y `sirena-extractor:1` registrado
- [ ] VM creada con NSG restringido a la IP del equipo
- [ ] Microservicios arriba en la VM y mensaje de Telegram visible en el tablero
- [ ] `desplegar_config.sh` toma el modelo del registro
- [ ] Capturas de cada vista y video de respaldo del demo
- [ ] Escenario armado y exportado en la calculadora de precios
- [ ] Documento: requerimientos, alternativas, pipeline, costos, diagramas y descripción de componentes
- [ ] Diapositivas y ensayo cronometrado de 15 minutos por cada integrante
- [ ] Extra: línea base en Designer
- [ ] Extra: endpoint por lotes
- [ ] Después de la sustentación: borrar el grupo de recursos, rotar la clave de Groq y revocar el token del bot

## Riesgos y plan B

El riesgo más probable es de capacidad o cuota en Azure, no de código; por eso la Fase 0 se hace primero y el plan B está definido antes de empezar.

| Riesgo | Señal | Plan B |
| --- | --- | --- |
| Sin capacidad o sin cuota para la VM o el clúster en la región | `SkuNotAvailable`, `OutOfQuota`, `QuotaExceeded` | Otra región permitida (por ejemplo `brazilsouth` o `westus`); otro tamaño (`Standard_D2as_v4`, `Standard_DS1_v2`); clúster con `max-instances 1`; usar la suscripción del otro integrante |
| Región bloqueada por política | `RequestDisallowedByPolicy` | Volver a la lista de regiones permitidas de la guía del curso |
| `azureml-mlflow` incompatible con mlflow 3.x | Error al construir el Environment o al registrar métricas | Fijar la versión de mlflow compatible solo en `azureml/env/requirements.txt`, sin tocar el lock del repo |
| MLflow rechaza `set_experiment` dentro del job | Error de experimento o de run activo en `evaluar_modelo` | `experiment_name: sirena-evaluacion` en el pipeline (ya incluido) y, si persiste, el ajuste en `registro.py` |
| La identidad del clúster no lee el Key Vault | `Forbidden` en la llamada de `evaluar.py` al `SecretClient` | Revisar si el Key Vault usa políticas de acceso o RBAC; en último caso, variable de entorno al lanzar el job y rotar la clave |
| Límites de Groq (429) o caída del servicio | Corridas lentas o fallidas | El proveedor ya reintenta con backoff; bajar `limite`; correr las dos evaluaciones en serie; tener resultados de la noche anterior |
| Sin acceso a gpt-oss-120b con la clave | `model_not_found` | Comparar contra `qwen/qwen3.8-27b` u otro modelo del catálogo de `docs/CONFIG_PROVEEDORES.md` |
| VM sin RAM al construir 7 imágenes | Build lento o contenedores reiniciando | Construir en serie (`docker compose build --parallel 1`) o subir temporalmente a `Standard_B2ms` |
| Red del salón cambia la IP pública del equipo | El tablero no abre en la sustentación | Actualizar la regla del NSG al llegar; video de respaldo |
| Todo Azure falla | Nada se puede crear | El profesor acepta AWS EC2 para la parte IaaS; la parte de Azure ML se muestra con el video y las capturas de corridas previas |
| Pregunta sobre validez de las métricas | — | Declarar desde el inicio que el corpus es sintético y que el aporte es el pipeline reproducible, no la cifra |

## Preguntas abiertas

- [ ] ¿Cuál es la fecha de entrega y sustentación? Con ella se fija un cronograma por fechas.
- [x] ¿En qué suscripción se monta todo? **Resuelta el 2026-09-27:** una sola suscripción "Azure for Students", la del propietario del proyecto. El compañero entra con rol `Contributor` acotado a `rg-sirena-mp3`, sin invitaciones porque ambos están en el dominio `uao.edu.co`. La atribución de autoría va en los tags `autor` y `rama` de MLflow. Las regiones y la cuota concretos se confirman en la Fase 0.
- [x] ¿El profesor acepta que el LLM se sirva desde Groq (fuera de Azure) si la evaluación, el registro y el despliegue viven en Azure? **Resuelta el 2026-09-26:** confirmado por el profesor. Se mantiene la decisión L1 y L2 queda descartada.
- [x] ¿Los cambios de `azureml/` van al repositorio de SIRENA por PR o a un fork? **Resuelta el 2026-09-27:** fork propio del equipo, `JCMelendezT/pmu-structured-extraction`, con `upstream` apuntando a `Juanxo17/pmu-structured-extraction`. Rama de trabajo `feature/azureml-pipeline` basada en `develop`.
- [ ] ¿Se hace el extra de Designer? Suma a la rúbrica de pipeline, pero cuesta tiempo convertir el corpus a tabla.

## Fuentes

- Enunciado "Microproyecto 3", Prof. Oscar Mondragón (archivo del curso).
- Práctica IaaS — Azure Virtual Machines; Práctica REST; Práctica REST + MySQL; diapositivas API REST; guía rápida de regiones de Azure; Gartner Magic Quadrant 2025 (material del curso).
- Recomendaciones para la práctica de Azure Virtual Machines, foro del curso, 23/09/2026.
- [Repositorio SIRENA (pmu-structured-extraction)](https://github.com/Juanxo17/pmu-structured-extraction): `Readme.md`, `AGENTS.md`, `.specify/memory/constitution.md`, `docker-compose.yml`, `docs/CONFIG_PROVEEDORES.md`, `docs/trabajo_futuro.md`, `docs/deuda_tecnica.md`, `backend/inference/inference/evaluacion.py` y `registro.py`.
- [Referencia de componentes de Azure ML](https://learn.microsoft.com/en-us/azure/machine-learning/component-reference/component-reference?view=azureml-api-2)
- [Configurar MLflow para Azure ML](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-configure-tracking?view=azureml-api-2)
- [SKUs de endpoints en línea gestionados](https://learn.microsoft.com/en-us/azure/machine-learning/reference-managed-online-endpoints-vm-sku-list?view=azureml-api-2)
- [Comandos az ml compute](https://learn.microsoft.com/en-us/cli/azure/ml/compute?view=azure-cli-latest)
- [API de precios de Azure, Standard\_B2s en eastus](https://prices.azure.com/api/retail/prices?$filter=armRegionName%20eq%20%27eastus%27%20and%20armSkuName%20eq%20%27Standard_B2s%27%20and%20priceType%20eq%20%27Consumption%27)
- [Precio de gpt-oss-20b en Groq (Requesty)](https://www.requesty.ai/models/groq/openai-gpt-oss-20b)
- [Calculadora de precios de Azure](https://azure.microsoft.com/es-es/pricing/calculator/)
