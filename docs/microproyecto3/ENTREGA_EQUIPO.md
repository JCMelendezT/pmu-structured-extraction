# Entrega de la infraestructura — SIRENA en Azure

> **Responsable de la infraestructura:** Juan Meléndez · **Fecha de entrega:** 2026-09-28 · **Versión desplegada:** `feature/azureml-pipeline` @ `a4753ed`

## Dónde está

| Qué | Dirección |
| --- | --- |
| Tablero del operador (Streamlit) | `http://57.156.64.147:8501` |
| API del BFF | `http://57.156.64.147:8000` |
| Documentación interactiva del BFF (Swagger) | `http://57.156.64.147:8000/docs` |
| Salud del BFF | `http://57.156.64.147:8000/health` |

Solo esos dos puertos están abiertos, y **solo para las IP autorizadas**. CRUD, Process, Inference y Geo (8001–8004) son internos y no se pueden probar desde fuera.

## Cómo pedir acceso

1. Busca tu IP pública en https://ifconfig.me desde la red donde vas a correr las pruebas.
2. Mándasela a Juan. Él la agrega en Terraform y te confirma (tarda unos minutos).
3. Si cambias de red (casa, universidad, datos móviles), tu IP cambia y hay que pedirla de nuevo.

IP autorizadas hoy: Juan (admin), Julián, Sebastián, Juan Plata, Cesar

## Acceso SSH

El equipo puede conectarse por SSH para ver logs y contenedores:

```bash
ssh julian@57.156.64.147    # Julián
ssh sebas@57.156.64.147     # Sebastián
ssh juanp@57.156.64.147     # Juan Plata
ssh cesar@57.156.64.147     # Cesar
```

Cada usuario tiene su llave SSH y está en el grupo `docker`, así que pueden ejecutar `docker compose ps`, `docker compose logs`, etc. sin sudo.

## Cuándo está encendida

- **El apagado es manual:** `az vm deallocate -g rg-sirena-mp3 -n vm-sirena`. Si nadie la apaga, la VM se queda prendida consumiendo crédito.
- Para usarla, avísale a Juan con anticipación: él la enciende y confirma que los servicios están sanos.
- Para pruebas de carga sostenidas, pídele una **ventana de carga**: sube la VM a `Standard_D2as_v4` (2 vCPU sin ráfaga) durante la prueba y la regresa a `Standard_B2s_v2` al terminar. Con la `B2s_v2` la CPU baja cuando se agotan los créditos de ráfaga y los resultados salen distorsionados.

## Especificaciones

| Qué | Valor |
| --- | --- |
| Región | `chilecentral` (Chile; la suscripción permite Latinoamérica) |
| VM normal | `Standard_B2s_v2`: 2 vCPU de ráfaga, 4 GB RAM |
| VM en ventana de carga | `Standard_D2as_v4`: 2 vCPU dedicadas, 8 GB RAM |
| Sistema | Ubuntu 22.04, Docker Compose, 7 contenedores en una sola VM |
| Base de datos | SQLite dentro del contenedor de CRUD (un solo escritor) |
| Modelo de lenguaje | `openai/gpt-oss-20b` vía API de Groq (provisional — registrado con `limite=5`, se reemplaza con la corrida completa) |

## Endpoints para las pruebas

Contrato completo en `docs/CONTRATOS_SISTEMA.md`. Resumen:

| Método y ruta | Qué hace | Llama al LLM |
| --- | --- | --- |
| `GET /health` | Salud del BFF | No |
| `GET /reportes` | Lista de reportes, con filtros y paginación por query string | No |
| `GET /reportes/resumen` | Conteos para el tablero | No |
| `GET /reportes/{id_reporte}` | Un reporte | No |
| `PATCH /reportes/{id_reporte}` | Corrección del operador | No |
| `POST /mensajes` | Recibe un mensaje y dispara el pipeline | **Sí, hasta 2 llamadas por mensaje** |

Cuerpo de `POST /mensajes`:

```json
{
  "fuente": "telegram",
  "id_externo": "carga-000001",
  "texto": "inundacion en el barrio Vista Hermosa, el agua ya entro a las casas",
  "marca_temporal_origen": "2026-09-28T15:00:00Z",
  "autor_id_telegram": "prueba-carga"
}
```

## Lo que hay que saber antes de medir

1. **`id_externo` tiene que ser único en cada petición.** Si se repite, el BFF responde `409` y la prueba mide rechazos, no el sistema.
2. **`POST /mensajes` responde `202` antes de procesar.** Su latencia es la de recibir el mensaje, no la del pipeline. Para medir el pipeline completo hay que consultar después `GET /reportes` y comparar tiempos.
3. **El límite de `POST /mensajes` es Groq, no Azure.** Groq limita peticiones por minuto (responde `429`) y cobra por token en el plan de pago. Una prueba masiva sobre `POST /mensajes` mide a Groq y gasta la cuota del equipo. Recomendación: medir la infraestructura con los `GET`, y la escritura con volumen bajo y acordado con Juan.
4. **CRUD usa SQLite con un solo escritor.** Con muchas escrituras concurrentes va a ser el primer cuello de botella. Es un hallazgo esperable para el análisis.
5. **No hay autenticación** en el BFF. No compartan la IP fuera del equipo.
6. **No prueben el bot de Telegram con carga:** un solo proceso hace long polling y Telegram también limita.
7. **Al apagar la VM, los contenedores no arrancan automáticamente.** Después de `az vm start` hay que ejecutar `docker compose up -d`.

## Métricas disponibles

- **Portal de Azure → `vm-sirena` → Métricas:** CPU, red de entrada y salida, disco. Sin costo. Juan puede compartir capturas o darles acceso de lectura.
- **`docker stats` en la VM:** CPU y memoria por contenedor, lo corre Juan durante la prueba si lo piden.

## Contacto y cambios

- Juan despliega cualquier versión nueva del código (`git pull` + reconstrucción) y avisa por el grupo.
- Si algo no responde: revisar primero que su IP siga autorizada y que la VM esté encendida; después escribirle a Juan con la hora, la ruta y el código de respuesta.
