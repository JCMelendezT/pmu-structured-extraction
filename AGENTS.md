# AGENTS.md

Lineamientos para cualquier persona o agente de código (Claude Code, OpenCode, etc.) que trabaje en este repositorio. Léelo antes de modificar cualquier archivo.

## Contexto del proyecto

**SIRENA** — extracción estructurada de reportes ciudadanos de emergencia (Santiago de Cali) mediante un LLM de pesos abiertos (`openai/gpt-oss-20b` vía Groq), con validación de esquema y normalización geográfica determinista. Ver la propuesta completa en [`docs/propuesta/propuesta-final-sirena.md`](docs/propuesta/propuesta-final-sirena.md).

Los principios de producto y las exclusiones de alcance (qué no calcula ni decide el sistema, límites éticos, restricciones de despliegue) están en [`.specify/memory/constitution.md`](.specify/memory/constitution.md) — ese archivo es el que valida `/speckit-plan` y `/speckit-analyze`; este `AGENTS.md` cubre solo convenciones operativas del día a día.

## Arquitectura: 5 servicios independientes (en paralelo)

Cada uno un proceso FastAPI propio, comunicándose por HTTP — ver `docs/CONTRATOS_SISTEMA.md` para el contrato completo (endpoints, request/response, esquema compartido). Viven bajo `backend/<nombre>/`, cada uno con su propio `pyproject.toml` y `Dockerfile` (workspace de `uv`, un solo `uv.lock` en la raíz).

- **BFF** (:8000) — **Cesar** — gateway único hacia lo externo (Telegram, Frontend); proxy puro hacia CRUD, dispara `/procesar` en Process
- **CRUD** (:8001) — **Julian** — persistencia SQLite/SQLAlchemy; único componente que toca la base de datos
- **Process** (:8002) — **Cesar** — preprocesamiento (anonimización, duplicados) + orquestador de dos etapas; llama a Inference, Geo y CRUD
- **Inference** (:8003) — **Juan** — cliente de inferencia (Groq), prompts, validador/reparación
- **Geo** (:8004) — **Julian** — gazetteer, normalización geográfica determinista, nunca invoca al LLM

**Frontend** (Streamlit) — **Sebas** — cliente puro de BFF; consume `GET/PATCH /reportes` y `GET /reportes/resumen`, no es uno de los 5 servicios ni implementa lógica propia de negocio.

El esquema Pydantic de extracción (`ReporteEstructurado`, en `docs/CONTRATOS_SISTEMA.md`) es el contrato central: nadie implementa contra un campo hasta que quede congelado y acordado por el equipo. Cambios a cualquier endpoint o campo van en el mismo PR que actualiza ese documento.

Código compartido por los 5 servicios (esquema, ontología) vive en `common/sirena-schema` (paquete `sirena_schema`) — nunca se duplica en un servicio. El vocabulario de `tipo_evento`/`servicio_de_respuesta` se edita en `config/ontologia.yaml`, no en código.

## Gestor de paquetes: uv, exclusivamente (workspace)

Prohibido `pip install` directo. Es un workspace de `uv`: un `uv.lock` en la raíz, cada servicio (`backend/*`, `common/*`, `frontend`) con su propio `pyproject.toml`.

```bash
uv sync --all-packages          # instalar todo el workspace (entorno de desarrollo local)
uv sync --package <nombre>      # instalar solo un servicio (lo que usa cada Dockerfile)
uv run --package <nombre> ...   # correr un comando dentro del entorno de ese servicio
uv add --package <nombre> <paquete>       # dependencia de producción de ese servicio
uv add --package <nombre> --dev <paquete> # dependencia de desarrollo de ese servicio
```

Los comandos de día a día están en el `Makefile`: `make install`, `make lint`, `make format`, `make test`, `make test-cov`, `make run-<servicio>` (ej. `make run-bff`), `make docker-up`.

## Estilo de código

- PEP 8, verificado con `ruff`.
- Docstrings obligatorios en todo módulo, clase, función y método público (Google style: `Args:`, `Returns:`, `Raises:`).
- Cero warnings: se corrige la causa, nunca se silencia con `warnings.filterwarnings`.
- Sin abstracciones ni manejo de errores para casos que no pueden ocurrir. No hacer refactors fuera del alcance de lo que se está trabajando.
- Alta cohesión, bajo acoplamiento — mismo criterio que en `uao-neumonia`: si un método hace algo claramente distinto al resto de la clase, se extrae a su propia clase con nombre específico, nunca a un `utils.py`/`Manager.py`.
- No referenciar IDs de tarea (`T-XX`) en código, docstrings ni comentarios — el código no necesita saber qué ticket lo originó; esa trazabilidad va en el commit/PR.

## Pruebas

- Mínimo 120 pruebas unitarias con `pytest` en `tests/`.
- Toda función nueva o modificada necesita su prueba correspondiente.
- Patrón AAA (Arrange / Act / Assert), agrupadas en clases `TestNombreDeLoQueSePrueba`.
- La suite debe pasar en verde antes de abrir un Pull Request.

## MLflow

Como el modelo es preentrenado (no hay fine-tuning), cada corrida de MLflow registra una **evaluación o sesión de inferencia**, no un entrenamiento:

- **Parámetros**: repositorio + revisión del modelo en Groq/HF Hub, versión del corpus, umbral de la compuerta (etapa 1), configuración de prompts.
- **Métricas**: precisión exacta y F1 por campo del esquema, latencia media/p95.
- **Artefactos**: informe de evaluación, ejemplos de predicción.
- **Tags**: licencia del modelo realmente usado —`MIT` para `gpt-oss-20b`, que es lo que registra `registro.py` con `LICENCIA = "MIT"`—, equipo/autor, ambiente (dev/prod), PR asociado.

`mlflow server` + variable `MLFLOW_TRACKING_URI` compartida por el equipo (mismo flujo del laboratorio de Clase 7).

## Flujo de Git

- Gitflow: `main` (producción) ← `develop` (integración) ← `feature/<servicio>-<algo>` (ej. `feature/inference-prompts-v1`).
- Todo cambio se integra mediante Pull Request con la plantilla oficial (`.github/pull_request_template.md`) — nunca push directo a `main` ni a `develop`.
- Un PR no se mergea si `pytest` o `ruff` fallan.

## Contratos entre módulos

Las firmas y esquemas documentados en `docs/CONTRATOS_SISTEMA.md` son la interfaz que el resto del equipo asume para integrar su propio módulo. Si necesitas cambiar el esquema de un campo ya contratado:

1. Actualiza `docs/CONTRATOS_SISTEMA.md` en el mismo PR.
2. Avisa al equipo — quien depende de ese campo puede estar trabajando con un mock basado en la versión anterior.
