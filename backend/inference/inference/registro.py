"""Registro de corridas de evaluacion de prompts en MLflow.

Cada corrida del harness se guarda como una evaluacion (no un
entrenamiento): parametros del modelo y del corpus, metricas por campo,
latencia y errores, artefactos del informe y las matrices de confusion, y
tags del contexto de la corrida.

    El registro se habilita al definir la variable MLFLOW_TRACKING_URI; si no
    esta definida, la corrida se ejecuta igual pero sin registrarse.

    Dentro de un job de Azure ML la corrida ya la abrio el pipeline padre y
    MLFLOW_RUN_ID la apunta. En ese caso no se cambia el experimento, porque
    MLflow ya tiene la corrida activa y cambiarla a mitad de camino falla.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import mlflow

from inference.prompts import sistema_compuerta, sistema_extraccion

os.environ.setdefault("MLFLOW_SUPPRESS_PRINTING_URL_TO_STDOUT", "true")

if TYPE_CHECKING:
    from inference.evaluacion import EvaluacionEjemplo, EjemploGold, Metricas

_LOGGER = logging.getLogger(__name__)

EXPERIMENTO = "sirena-evaluacion"
MODELO_POR_DEFECTO = "openai/gpt-oss-20b"
PROVEEDOR = "groq"
UMBRAL_COMPUERTA = "no_aplica"
EQUIPO = "SIRENA"
AMBIENTE = "dev"
LICENCIA = "MIT"


def registrar_corrida(
    *,
    metricas: Metricas,
    ejemplos: Sequence[EjemploGold],
    resultados: Sequence[EvaluacionEjemplo],
    ruta_informe: Path,
    corpus: Path,
    matrices_confusion: dict[str, dict[str, dict[str, int]]] | None = None,
    tracking_uri: str | None = None,
    autor: str | None = None,
    rama: str | None = None,
    pr: str | None = None,
) -> str | None:
    """Registra una corrida del harness en MLflow y devuelve su id.

    Sin MLFLOW_TRACKING_URI (o sin tracking_uri), la corrida no se registra
    y se devuelve None, permitiendo que la evaluacion siga sin red.

    Args:
        metricas: Resumen numerico de la corrida a registrar.
        ejemplos: Ejemplos gold evaluados, en orden de entrada.
        resultados: Resultados del servicio, en el mismo orden.
        ruta_informe: Ruta del informe Markdown generado por el harness.
        corpus: Ruta del corpus JSONL utilizado en la corrida.
        matrices_confusion: Matrices por campo con la coincidencia entre lo
            predicho y el gold, si se calcularon.
        tracking_uri: URI del servidor MLflow. Por defecto, la variable de
            entorno MLFLOW_TRACKING_URI.
        autor: Nombre del autor que corre la evaluacion. Por defecto, el
            nombre de usuario de Git.
        rama: Rama de Git donde corre la evaluacion. Por defecto, la rama
            actual de Git.
        pr: Numero del pull request asociado a la corrida, si existe.

    Returns:
        Id del run creado, o None si no hay URI de seguimiento configurada.

    """
    uri = tracking_uri if tracking_uri is not None else os.environ.get("MLFLOW_TRACKING_URI")
    if not uri:
        _LOGGER.warning("MLFLOW_TRACKING_URI sin definir; la corrida no se registra en MLflow")
        return None
    mlflow.set_tracking_uri(uri)
    if not os.environ.get("MLFLOW_RUN_ID"):
        mlflow.set_experiment(EXPERIMENTO)
    with mlflow.start_run() as run:
        _registrar_parametros(corpus)
        _registrar_metricas(metricas)
        _registrar_tags(autor=autor, rama=rama, pr=pr)
        mlflow.log_artifact(str(ruta_informe))
        mlflow.log_dict(_ejemplos_prediccion(resultados), "ejemplos_prediccion.json")
        if matrices_confusion:
            mlflow.log_dict(matrices_confusion, "matrices_confusion.json")
    _LOGGER.info("Corrida registrada en MLflow con el run %s", run.info.run_id)
    return run.info.run_id


def _registrar_parametros(corpus: Path) -> None:
    """Registra los parametros de la corrida como params de MLflow.

    Args:
        corpus: Ruta del corpus JSONL utilizado en la corrida.

    """
    mlflow.log_params(
        {
            "modelo": _variable_entorno("INFERENCE_MODELO", MODELO_POR_DEFECTO),
            "proveedor": PROVEEDOR,
            "temperatura": _variable_flotante("INFERENCE_TEMPERATURA", 0.0),
            "intentos": _variable_entera("INFERENCE_INTENTOS_LLM", 3),
            "corpus": str(corpus),
            "version_corpus": _version_corpus(corpus),
            "umbral_compuerta": UMBRAL_COMPUERTA,
            "prompt_compuerta_hash": _hash_prompt(sistema_compuerta()),
            "prompt_extraccion_hash": _hash_prompt(sistema_extraccion()),
        }
    )


def _registrar_metricas(metricas: Metricas) -> None:
    """Registra las metricas de la corrida como metrics de MLflow.

    Incluye exactitud y F1 por campo del esquema, junto con la latencia
    media y percentil 95, los errores y el total de ejemplos.

    Args:
        metricas: Resumen numerico de la corrida registrada.

    """
    por_campo: dict[str, float] = {}
    for campo in metricas.campos:
        por_campo[f"exactitud_{campo.campo}"] = campo.exactitud
        por_campo[f"f1_{campo.campo}"] = campo.f1
    mlflow.log_metrics(
        {
            **por_campo,
            "latencia_media_ms": metricas.latencia_media_ms,
            "latencia_p95_ms": metricas.latencia_p95_ms,
            "errores_validacion": metricas.errores_validacion,
            "total_ejemplos": metricas.total_ejemplos,
        }
    )


def _registrar_tags(*, autor: str | None, rama: str | None, pr: str | None) -> None:
    """Registra los tags de contexto de la corrida en MLflow.

    Args:
        autor: Nombre del autor, o None para derivarlo de Git.
        rama: Rama de Git, o None para derivarla de Git.
        pr: Numero del pull request asociado, si existe.

    """
    mlflow.set_tags(
        {
            "licencia": LICENCIA,
            "equipo": EQUIPO,
            "autor": autor or _comando_git("config", "user.name"),
            "ambiente": AMBIENTE,
            "rama": rama or _comando_git("rev-parse", "--abbrev-ref", "HEAD"),
        }
    )
    if pr:
        mlflow.set_tag("pr", pr)


def _ejemplos_prediccion(resultados: Sequence[EvaluacionEjemplo]) -> list[dict]:
    """Convierte los resultados en el artefacto de predicciones.

    Args:
        resultados: Resultados del servicio por ejemplo evaluado.

    Returns:
        Lista con el texto, el error, las salidas serializadas y la latencia.

    """
    ejemplos: list[dict] = []
    for resultado in resultados:
        ejemplos.append(
            {
                "texto": resultado.texto,
                "error": resultado.error,
                "compuerta": _serializar(resultado.compuerta),
                "naturaleza": _serializar(resultado.naturaleza),
                "ubicacion": _serializar(resultado.ubicacion),
                "latencia_ms": resultado.latencia_ms,
            }
        )
    return ejemplos


def _serializar(valor: object) -> dict | None:
    """Serializa un modelo del esquema o devuelve None.

    Args:
        valor: Modelo del esquema a serializar, o None.

    Returns:
        Diccionario JSON del modelo, o None si el valor es None.

    """
    if valor is None:
        return None
    return json.loads(valor.model_dump_json())


def _version_corpus(corpus: Path) -> str:
    """Deriva la version del corpus a partir de su directorio contenedor.

    Args:
        corpus: Ruta del corpus JSONL utilizado en la corrida.

    Returns:
        Nombre del directorio padre (por ejemplo, gold_v1) o el nombre del
        archivo si el corpus no vive dentro de un directorio versionado.

    """
    if corpus.parent.name and corpus.parent.name != ".":
        return corpus.parent.name
    return corpus.name


def _hash_prompt(sistema: str) -> str:
    """Resume la configuracion de un prompt con un hash corto.

    Args:
        sistema: Instrucciones de sistema del prompt a resumir.

    Returns:
        Primeros 12 caracteres del hash SHA-256 del texto del prompt.

    """
    return hashlib.sha256(sistema.encode("utf-8")).hexdigest()[:12]


def _comando_git(*argumentos: str) -> str:
    """Ejecuta un comando de Git y devuelve su salida limpia.

    Args:
        argumentos: Argumentos del comando de Git a ejecutar.

    Returns:
        Salida del comando sin espacios laterales, o "desconocido" si el
        comando falla o Git no esta disponible.

    """
    try:
        salida = subprocess.check_output(
            ["git", *argumentos],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return "desconocido"
    return salida.strip()


def _variable_entorno(nombre: str, por_defecto: str) -> str:
    """Devuelve una variable de entorno o el valor por defecto.

    Args:
        nombre: Nombre de la variable de entorno.
        por_defecto: Valor a usar si la variable no esta definida.

    Returns:
        Valor de la variable o el valor por defecto.

    """
    return os.environ.get(nombre, por_defecto)


def _variable_flotante(nombre: str, por_defecto: float) -> float:
    """Devuelve una variable de entorno numerica o el valor por defecto.

    Args:
        nombre: Nombre de la variable de entorno.
        por_defecto: Valor a usar si la variable no esta definida.

    Returns:
        Valor numerico de la variable o el valor por defecto.

    Raises:
        ValueError: Si la variable no es un numero valido.

    """
    valor = os.environ.get(nombre)
    return float(valor) if valor is not None else por_defecto


def _variable_entera(nombre: str, por_defecto: int) -> int:
    """Devuelve una variable de entorno entera o el valor por defecto.

    Args:
        nombre: Nombre de la variable de entorno.
        por_defecto: Valor a usar si la variable no esta definida.

    Returns:
        Valor entero de la variable o el valor por defecto.

    Raises:
        ValueError: Si la variable no es un entero valido.

    """
    valor = os.environ.get(nombre)
    return int(valor) if valor is not None else por_defecto
