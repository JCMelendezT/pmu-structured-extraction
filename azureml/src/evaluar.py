"""Envoltorio del harness de evaluacion para correrlo dentro de un job.

No reimplementa nada: arma su propio servicio de inferencia, le pasa el
corpus validado y devuelve lo que el harness ya sabe calcular, mas un
metricas.json con el nombre del modelo para que el job de comparacion no
tenga que adivinar de donde salieron las metricas.

La clave de Groq se resuelve aqui adentro y nunca viaja por el comando del
job. Un ``export GROQ_API_KEY=$(...)`` en el comando deja la clave escrita en
el log del job, que se conserva y lee cualquiera con acceso al workspace.
"""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from inference.evaluacion import (
    CAMPOS_EVALUADOS,
    EvaluadorPrompts,
    cargar_corpus,
    generar_informe,
    matriz_confusion,
    metricas_por_campo,
)
from inference.proveedor import ProveedorGroq
from inference.registro import MODELO_POR_DEFECTO, registrar_corrida
from inference.servicio import ServicioInferencia

NOMBRE_SECRETO = "groq-api-key"
ARCHIVO_METRICAS = "metricas.json"
ARCHIVO_INFORME = "informe.md"


def _leer_secreto(vault_url: str) -> str:
    """Lee la clave de Groq del Key Vault con la identidad del job.

    Los clientes de Azure se importan adentro porque solo existen en la
    imagen del Environment, no en el entorno de desarrollo del repositorio.

    Args:
        vault_url: URL del Key Vault donde vive el secreto.

    Returns:
        Valor del secreto, que el llamador no debe imprimir.

    """
    from azure.identity import ManagedIdentityCredential
    from azure.keyvault.secrets import SecretClient

    cliente = SecretClient(vault_url=vault_url, credential=ManagedIdentityCredential())
    return cliente.get_secret(NOMBRE_SECRETO).value


def _resolver_clave() -> None:
    """Deja GROQ_API_KEY en el entorno sin imprimirla.

    Primero usa la que ya venga en el entorno, que es el caso de una corrida
    local. Solo si no hay, y hay Key Vault, lee el secreto con la identidad
    administrada del compute.

    Raises:
        RuntimeError: Si no hay ninguna fuente de donde sacar la clave.

    """
    if os.environ.get("GROQ_API_KEY"):
        return
    vault_url = os.environ.get("KEY_VAULT_URL")
    if not vault_url:
        raise RuntimeError(
            "No hay clave de Groq: define GROQ_API_KEY en el entorno o KEY_VAULT_URL "
            "para leerla del Key Vault."
        )
    os.environ["GROQ_API_KEY"] = _leer_secreto(vault_url)


def _escribir_metricas(salida: Path, metricas, modelo: str) -> None:
    """Vierte las metricas de la corrida para el job de comparacion.

    El nombre del modelo va dentro del archivo a proposito: es el dato que
    decide el desempate por costo, y el job que compara no recibe el modelo
    por input. Un metricas.json que no dice que midio es una trampa.

    Args:
        salida: Carpeta de salida del job.
        metricas: Metricas calculadas por el harness.
        modelo: Identificador del modelo evaluado.

    """
    contenido = asdict(metricas)
    contenido["modelo"] = modelo
    (salida / ARCHIVO_METRICAS).write_text(
        json.dumps(contenido, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Define y resuelve los argumentos de la linea de comandos.

    Args:
        argv: Argumentos de la linea de comandos, o None para usar sys.argv.

    Returns:
        Espacio de nombres con los argumentos resueltos.

    """
    parser = argparse.ArgumentParser(description="Evalua un modelo contra el corpus gold v1")
    parser.add_argument("--corpus", type=Path, required=True, help="JSONL del corpus gold")
    parser.add_argument("--salida", type=Path, required=True, help="Carpeta de salida del job")
    parser.add_argument(
        "--limite", type=int, default=None, help="Evalua solo los primeros N ejemplos"
    )
    parser.add_argument("--autor", default="sirena", help="Integrante que corre la evaluacion")
    parser.add_argument("--rama", default="", help="Rama de codigo que se esta evaluando")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de la linea de comandos.

    Args:
        argv: Argumentos de la linea de comandos, o None para usar sys.argv.

    Returns:
        Codigo de salida, 0 si la corrida termino y 1 si no se pudo hacer.

    """
    args = _parse_args(argv)
    try:
        _resolver_clave()
    except RuntimeError as error:
        print(str(error))
        return 1

    ejemplos = cargar_corpus(args.corpus)
    if args.limite is not None:
        ejemplos = ejemplos[: args.limite]
    servicio = ServicioInferencia(ProveedorGroq())
    resultados = EvaluadorPrompts(servicio).evaluar(ejemplos)
    metricas = metricas_por_campo(ejemplos, resultados)
    matrices = {campo: matriz_confusion(ejemplos, resultados, campo) for campo in CAMPOS_EVALUADOS}

    args.salida.mkdir(parents=True, exist_ok=True)
    ruta_informe = args.salida / ARCHIVO_INFORME
    generar_informe(metricas, resultados, ruta_informe, matrices_confusion=matrices)
    modelo = os.environ.get("INFERENCE_MODELO", MODELO_POR_DEFECTO)
    _escribir_metricas(args.salida, metricas, modelo)

    run_id = registrar_corrida(
        metricas=metricas,
        ejemplos=ejemplos,
        resultados=resultados,
        ruta_informe=ruta_informe,
        corpus=args.corpus,
        matrices_confusion=matrices,
        autor=args.autor,
        rama=args.rama,
    )
    print(f"Informe generado en {ruta_informe}")
    if run_id:
        print(f"Corrida registrada en MLflow: {run_id}")
    print(
        f"Ejemplos: {metricas.total_ejemplos} | Errores de validacion: "
        f"{metricas.errores_validacion} | Latencia media: {metricas.latencia_media_ms:.1f} ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
