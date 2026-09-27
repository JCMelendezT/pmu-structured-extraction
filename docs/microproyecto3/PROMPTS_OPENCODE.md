# Prompts para opencode — Microproyecto 3

Seis sesiones, una por etapa. Cada una empieza desde cero y lee los archivos del plan, así que no depende de la memoria de la sesión anterior. Copiar cada prompt tal cual; cambiar solo lo que está entre `< >`.

## Preparación (una sola vez, a mano)

1. Clonar el repo (o el fork del equipo) y crear la rama:

   ```bash
   git clone https://github.com/Juanxo17/pmu-structured-extraction.git
   cd pmu-structured-extraction
   git checkout develop
   git checkout -b feature/azureml-pipeline
   ```

2. Copiar los tres archivos en `docs/microproyecto3/`: `PLAN_MP3.md`, `REGLAS_AGENTE.md` y este `PROMPTS_OPENCODE.md`.

3. Crear `opencode.json` en la raíz del repo para que las reglas se carguen en todas las sesiones:

   ```json
   {
     "$schema": "https://opencode.ai/config.json",
     "instructions": ["docs/microproyecto3/REGLAS_AGENTE.md"]
   }
   ```

   opencode ya lee el `AGENTS.md` de la raíz, así que las convenciones de SIRENA (uv, ruff, pytest, Gitflow) entran solas.

4. Hacer un commit con estos archivos antes de la primera sesión, para que todo lo que haga el agente quede como diff contra ese punto.

---

## Sesión 1 — Leer, cuestionar y partir en tickets (sin código)

```text
Vamos a desarrollar el Microproyecto 3 del curso Computación en la Nube siguiendo docs/microproyecto3/PLAN_MP3.md.
Lee completos, en este orden: docs/microproyecto3/REGLAS_AGENTE.md, AGENTS.md, docs/microproyecto3/PLAN_MP3.md, docker-compose.yml, backend/inference/inference/evaluacion.py y backend/inference/inference/registro.py.

En esta sesión NO escribas código ni ejecutes comandos que creen o cambien recursos de Azure.

1. Usa la skill grill-with-docs sobre el plan: contrástalo con el código real del repo y hazme las preguntas que haya que resolver antes de implementar (inconsistencias entre el plan y el código, supuestos no verificados, las "Preguntas abiertas" del plan). Una pregunta a la vez.
2. Con mis respuestas, usa la skill to-tickets para partir el plan en tickets pequeños, en este orden de etapas:
   A. Cambios al repo sin Azure (archivos de azureml/, scripts, pruebas, ajuste de docker-compose.yml).
   B. Azure fases 0 a 4 (suscripción, workspace, Data asset, Environment, clúster y secreto).
   C. Azure fases 5 y 6 (registrar componentes, correr y depurar el pipeline).
   D. Fases 7 y 8 (VM, microservicios, desplegar_config.sh).
   E. Fase 9 opcional (Designer, endpoint por lotes) y apagado.
   F. Materiales de entrega (documento, capturas, calculadora, diapositivas).
   Cada ticket: objetivo, archivos o recursos que toca, criterio de aceptación verificable y si necesita confirmación humana según REGLAS_AGENTE.md.
3. Escribe los tickets en docs/microproyecto3/PROGRESO.md, todos en estado pendiente, y haz commit.
```

## Sesión 2 — Etapa A: código y pruebas (sin Azure)

```text
Lee docs/microproyecto3/REGLAS_AGENTE.md, docs/microproyecto3/PLAN_MP3.md y docs/microproyecto3/PROGRESO.md.
Trabaja solo los tickets de la etapa A, uno a la vez, en la rama feature/azureml-pipeline. No ejecutes nada contra Azure.

Para cada ticket:
- Usa la skill tdd: primero las pruebas en tests/azureml/ (AAA, clases TestX), luego el código mínimo para pasarlas.
- Reutiliza las funciones existentes de inference.evaluacion e inference.registro; no copies su lógica.
- azureml/env/requirements.txt se genera con: uv export --package inference --no-dev --no-hashes --no-emit-workspace
- Valida los YAML de componentes y pipeline contra el esquema del plan (nombres de inputs y outputs coherentes entre componentes y pipeline.yml).
- Corre make lint, make format-check y make test. Si pasan, commit y marca el ticket como hecho en PROGRESO.md con la evidencia.

Cuando termine la etapa A, usa la skill code-review sobre el diff completo de la rama y muéstrame los hallazgos antes de seguir.
```

## Sesión 3 — Etapa B: Azure fases 0 a 4

```text
Lee docs/microproyecto3/REGLAS_AGENTE.md, docs/microproyecto3/PLAN_MP3.md (fases 0 a 4) y docs/microproyecto3/PROGRESO.md.
Trabaja los tickets de la etapa B. Uso la Azure CLI en <Git Bash | WSL | PowerShell>.

1. Primero solo lectura: con az o con el MCP de Azure, dame las regiones permitidas por la política, la cuota de vCPU por familia en esas regiones y el estado de los proveedores del plan. Con eso recomiéndame una región y los tamaños de VM y clúster, siguiendo la tabla de Riesgos del plan. Espera mi decisión.
2. Luego, por cada comando que crea o cambia algo: muéstrame el comando exacto, qué recurso toca y el costo aproximado, y espera mi "ok" antes de ejecutarlo.
3. El secreto de Groq lo escribo yo: dame el comando con <GROQ_API_KEY> y yo lo corro.
4. Después de cada fase, ejecuta la verificación que indica el plan y registra la evidencia en PROGRESO.md.
```

## Sesión 4 — Etapa C: pipeline en Azure ML

```text
Lee docs/microproyecto3/REGLAS_AGENTE.md, docs/microproyecto3/PLAN_MP3.md (fases 5 y 6, y la tabla de Riesgos) y docs/microproyecto3/PROGRESO.md.
Trabaja los tickets de la etapa C.

1. Pídeme confirmación y lanza la corrida corta: az ml job create --file azureml/pipeline.yml --set inputs.limite=5
2. Sigue el estado del job con az ml job show / az ml job stream. Si falla un paso, descarga sus logs, diagnostica con la skill diagnosing-bugs y propone el arreglo mínimo (revisa primero los riesgos conocidos: azureml-mlflow con mlflow 3.x, set_experiment dentro del job, permisos de Key Vault).
3. Arreglos de código: con prueba, lint y commit como en la etapa A. Si el mismo error aparece dos veces, detente y pregúntame.
4. Con la corrida corta en verde, pídeme confirmación para la corrida completa.
5. Al final, dame: id del pipeline job, métricas principales de cada modelo, decisión del paso comparar, versión registrada de sirena-extractor con sus tags, y la lista de vistas de Studio que debo capturar para la presentación.
```

## Sesión 5 — Etapa D: VM y cierre del ciclo

```text
Lee docs/microproyecto3/REGLAS_AGENTE.md, docs/microproyecto3/PLAN_MP3.md (fases 7 y 8) y docs/microproyecto3/PROGRESO.md.
Trabaja los tickets de la etapa D. Mi IP pública es <MI_IP>.

1. Creación de la VM, reglas del NSG e identidad administrada: comando por comando, con mi confirmación.
2. La instalación dentro de la VM (Docker, Azure CLI, clonado del repo, docker compose) hazla con az vm run-command invoke --command-id RunShellScript, en bloques pequeños y con mi confirmación. No pongas secretos en esos scripts: el .env de la VM lo completo yo por SSH.
3. Verifica /health de cada servicio y que el tablero responda en http://<IP de la VM>:8501.
4. Corre azureml/scripts/desplegar_config.sh en la VM y muéstrame qué modelo quedó en INFERENCE_MODELO.
5. Registra la evidencia en PROGRESO.md. Recuérdame apagar la VM (az vm deallocate) al terminar.
```

## Sesión 6 — Etapa F: materiales de entrega

```text
Lee docs/microproyecto3/PLAN_MP3.md y docs/microproyecto3/PROGRESO.md.
Con los resultados reales registrados en PROGRESO.md (no con los números estimados del plan):

1. Actualiza en el plan la tabla de costos y la sección de riesgos con lo que realmente pasó.
2. Redacta docs/AZURE.md con la guía de despliegue tal como quedó funcionando.
3. Actualiza docs/trabajo_futuro.md: MLflow ya está implementado y ahora se registra en Azure ML.
4. Arma el guion de la presentación de 15 minutos a partir de la sección "4. Presentación" del plan, con los resultados reales, y la lista de capturas que faltan.
5. Usa la skill handoff para dejar un resumen del estado para mi compañero de pareja.
```

---

## Consejos

- Una sesión por etapa. Si una sesión se alarga mucho, pídele a opencode la skill `handoff` y abre una nueva que lea ese resumen junto con `PROGRESO.md`.
- La etapa A se puede hacer completa sin gastar crédito. Conviene cerrarla y revisarla antes de tocar Azure.
- Si el agente pide saltarse una confirmación "para ir más rápido", la respuesta es no: la cuota y el crédito de estudiante no se recuperan.
- Revisar cada PR a mano antes de fusionar, aunque las pruebas estén en verde.
