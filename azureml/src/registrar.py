"""Registra la configuracion ganadora de la evaluacion como modelo de Azure ML.

Lo que se registra no es un modelo de MLflow: es la configuracion que gano la
comparacion. El paquete es una carpeta con la ontologia que fija el
vocabulario, la decision que explica por que gano ese modelo, los hashes de
los prompts usados y el informe de evaluacion del ganador. Por eso se
registra con MLClient y AssetTypes.CUSTOM_MODEL, y no con
mlflow.pyfunc.log_model: no hay funcion de inferencia que cargar, hay una
configuracion que documentar y que alguien mas va a reproducir.

El SDK de Azure se importa adentro de las funciones que lo usan y no al tope
del modulo, para que las pruebas corran sin azure-ai-ml instalado: la imagen
del Environment lo trae, el entorno de desarrollo no lo necesita.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Sequence

from inference.prompts import VERSION_PROMPTS, sistema_compuerta, sistema_extraccion

NOMBRE_MODELO = "sirena-extractor"
ARCHIVO_DECISION = "decision.json"
ARCHIVO_METRICAS = "metricas.json"
ARCHIVO_INFORME = "informe.md"
ARCHIVO_PROMPTS = "prompts.json"
CARPETA_CONFIG = "config"
ARCHIVO_ONTOLOGIA = "ontologia.yaml"
LONGITUD_HASH = 12
# El identificador de la corrida lo aporta el pipeline padre: MLFLOW_RUN_ID ya
# apunta a la corrida abierta para este job. Fuera de Azure no hay corrida, y
# el tag dice local para no inventar un id.
JOB_ID_LOCAL = "local"


class SinInformeGanador(RuntimeError):
    """Ninguno de los resultados corresponde al modelo que decidio ganar."""


def hashes_prompts() -> dict[str, str]:
    """Resume los prompts del servicio de inferencia con un hash corto.

    Usa el mismo formato que inference.registro guarda como parametros de
    MLflow, para que el tag del modelo y la corrida sean comparables.

    Returns:
        Version de los prompts y los hashes de compuerta y extraccion.

    """
    return {
        "version_prompts": VERSION_PROMPTS,
        "compuerta": _hash_prompt(sistema_compuerta()),
        "extraccion": _hash_prompt(sistema_extraccion()),
    }


def ensamblar_paquete(
    *,
    decision: Path,
    resultados_a: Path,
    resultados_b: Path,
    salida: Path,
    ontologia: Path,
) -> Path:
    """Arma la carpeta que se registra como modelo.

    Args:
        decision: Ruta del decision.json que produjo comparar.
        resultados_a: Carpeta de resultados de la primera evaluacion.
        resultados_b: Carpeta de resultados de la segunda evaluacion.
        salida: Carpeta destino del paquete.
        ontologia: Ruta del config/ontologia.yaml que define el vocabulario.

    Returns:
        Ruta de la carpeta con el paquete armado.

    Raises:
        SinInformeGanador: Si ningun resultado corresponde al modelo ganador.
        FileNotFoundError: Si falta la decision o la ontologia.

    """
    ganador = json.loads(decision.read_text(encoding="utf-8"))["ganador"]
    informe = _informe_del_ganador(ganador, resultados_a, resultados_b)

    (salida / CARPETA_CONFIG).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ontologia, salida / CARPETA_CONFIG / ARCHIVO_ONTOLOGIA)
    shutil.copyfile(decision, salida / ARCHIVO_DECISION)
    shutil.copyfile(informe, salida / ARCHIVO_INFORME)
    (salida / ARCHIVO_PROMPTS).write_text(
        json.dumps(hashes_prompts(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return salida


def descripcion(*, ruta: Path, decision: dict[str, Any], job_id: str) -> dict[str, Any]:
    """Describe el modelo a registrar con los tags que exige el plan.

    Args:
        ruta: Carpeta con el paquete armado.
        decision: Contenido de decision.json ya leido.
        job_id: Identificador de la corrida, para rastrearla desde el modelo.

    Returns:
        Descripcion del modelo con nombre, ruta, tipo, texto y tags.

    """
    hashes = hashes_prompts()
    return {
        "name": NOMBRE_MODELO,
        "path": str(ruta),
        "type": "custom_model",
        "description": (
            f"Configuracion ganadora de la evaluacion de prompts: {decision['ganador']}. "
            "Incluye la ontologia, la decision, los hashes de los prompts y el informe."
        ),
        "tags": {
            "modelo": decision["ganador"],
            "f1_tipo_evento": str(decision["f1_tipo_evento"]),
            "latencia_p95_ms": str(decision["latencia_p95_ms"]),
            "prompt_hash": f"compuerta={hashes['compuerta']},extraccion={hashes['extraccion']}",
            "job_id": job_id,
        },
    }


def construir_modelo(descripcion: dict[str, Any]) -> Any:
    """Construye la entidad Model de Azure ML a partir de la descripcion.

    Args:
        descripcion: Descripcion calculada por la funcion descripcion.

    Returns:
        Entidad Model lista para crear o actualizar en el workspace.

    Raises:
        ValueError: Si el tipo de la descripcion no es un tipo de asset valido.

    """
    from azure.ai.ml.constants import AssetTypes
    from azure.ai.ml.entities import Model

    return Model(
        path=descripcion["path"],
        type=AssetTypes(descripcion["type"]),
        name=descripcion["name"],
        description=descripcion["description"],
        tags=descripcion["tags"],
    )


def registrar(cliente: Any, descripcion: dict[str, Any]) -> Any:
    """Crea o actualiza el modelo en el registro del workspace.

    Args:
        cliente: MLClient apuntando al workspace destino.
        descripcion: Descripcion calculada por la funcion descripcion.

    Returns:
        Entidad Model ya registrada, con su version asignada.

    """
    modelo = construir_modelo(descripcion)
    cliente.models.create_or_update(modelo)
    return modelo


def main(argv: Sequence[str] | None = None) -> int:
    """Arma el paquete ganador y lo registra en el workspace.

    Args:
        argv: Argumentos de linea de comandos, o None para usar sys.argv.

    Returns:
        Codigo de salida, 0 si el modelo quedo registrado y 1 si no.

    """
    args = _parse_args(argv)
    try:
        paquete = ensamblar_paquete(
            decision=args.decision,
            resultados_a=args.resultados_a,
            resultados_b=args.resultados_b,
            salida=args.salida,
            ontologia=args.ontologia,
        )
    except (FileNotFoundError, KeyError, SinInformeGanador) as error:
        print(f"No se pudo armar el paquete del modelo: {error}")
        return 1

    descripcion_modelo = descripcion(
        ruta=paquete,
        decision=json.loads(args.decision.read_text(encoding="utf-8")),
        job_id=args.job_id,
    )
    try:
        modelo = registrar(
            _cliente(args.subscription_id, args.resource_group, args.workspace),
            descripcion_modelo,
        )
    except Exception as error:  # noqa: BLE001 - el SDK puede fallar por cualquier razon
        print(f"No se pudo registrar el modelo: {error}")
        return 1
    print(f"Modelo {modelo.name} version {modelo.version} registrado desde {paquete}")
    return 0


def _informe_del_ganador(ganador: str, resultados_a: Path, resultados_b: Path) -> Path:
    """Localiza el informe de evaluacion del modelo que gano.

    Cada evaluacion escribe metricas.json con el nombre del modelo que midio
    y su informe.md al lado, asi que el ganador se reconoce leyendo los
    metricas.json y no suponiendo que el ganador es el primer resultado.

    Args:
        ganador: Nombre del modelo que decidio la comparacion.
        resultados_a: Carpeta de resultados de la primera evaluacion.
        resultados_b: Carpeta de resultados de la segunda evaluacion.

    Returns:
        Ruta del informe.md del modelo ganador.

    Raises:
        SinInformeGanador: Si ninguna carpeta corresponde al ganador o al
            ganador le falta el informe.

    """
    for resultados in (resultados_a, resultados_b):
        metricas = resultados / ARCHIVO_METRICAS
        if not metricas.exists():
            continue
        if json.loads(metricas.read_text(encoding="utf-8")).get("modelo") != ganador:
            continue
        informe = resultados / ARCHIVO_INFORME
        if not informe.exists():
            break
        return informe
    raise SinInformeGanador(f"ningun resultado trae el informe de {ganador}")


def _hash_prompt(sistema: str) -> str:
    """Resume un prompt con un hash corto.

    Args:
        sistema: Instrucciones de sistema del prompt a resumir.

    Returns:
        Primeros 12 caracteres del hash SHA-256 del texto del prompt.

    """
    return hashlib.sha256(sistema.encode("utf-8")).hexdigest()[:LONGITUD_HASH]


def _cliente(subscription_id: str, resource_group: str, workspace: str) -> Any:
    """Abre un MLClient contra el workspace con la identidad administrada.

    Los tres identificadores van explicitos porque el MLClient no los deduce
    dentro de un job: los defaults del CLI viven en la maquina que submits,
    no en el contenedor.

    Args:
        subscription_id: Id de la suscripcion de Azure.
        resource_group: Grupo de recursos del workspace.
        workspace: Nombre del workspace de Azure ML.

    Returns:
        MLClient listo para registrar el modelo.

    """
    from azure.ai.ml import MLClient
    from azure.identity import DefaultAzureCredential

    return MLClient(
        credential=DefaultAzureCredential(),
        subscription_id=subscription_id,
        resource_group_name=resource_group,
        workspace_name=workspace,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Interpreta los argumentos de linea de comandos.

    Args:
        argv: Argumentos a interpretar, o None para usar sys.argv.

    Returns:
        Namespace con los argumentos ya tipados por argparse.

    """
    parser = argparse.ArgumentParser(
        description="Registra la configuracion ganadora como modelo del workspace"
    )
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--resultados-a", type=Path, required=True)
    parser.add_argument("--resultados-b", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument(
        "--ontologia",
        type=Path,
        default=Path(os.environ.get("ONTOLOGIA_PATH", "config/ontologia.yaml")),
    )
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument(
        "--job-id",
        default=os.environ.get("MLFLOW_RUN_ID") or JOB_ID_LOCAL,
    )
    return parser.parse_args(argv)
