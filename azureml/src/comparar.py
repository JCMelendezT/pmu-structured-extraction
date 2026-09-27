"""Elige el modelo ganador entre dos corridas de evaluacion.

La regla es una decision del equipo, escrita en el plan antes de ver los
resultados: gana el mayor promedio de f1 de tipo_evento y
es_reporte_accionable, y si la diferencia es menor a 0,02 gana el modelo
barato, que cuesta menos y responde mas rapido.

El desempate esta anclado a gpt-oss-20b a proposito. No es "el mas barato de
los dos": es el modelo que la comparacion de costos del plan puso como
barato, y escribirlo fijo evita que la regla cambie de significado cuando
cambien los candidatos del pipeline.
"""

import argparse
import json
from pathlib import Path
from typing import Sequence

CAMPOS_DECISIVOS = ("tipo_evento", "es_reporte_accionable")
MODELO_BARATO = "openai/gpt-oss-20b"
UMBRAL = 0.02
ARCHIVO_METRICAS = "metricas.json"
ARCHIVO_DECISION = "decision.json"


def _f1(metricas: dict, campo: str) -> float:
    """Devuelve el F1 de un campo dentro de unas metricas.

    Args:
        metricas: Contenido de un metricas.json.
        campo: Nombre del campo del esquema.

    Returns:
        Valor del F1 del campo.

    Raises:
        ValueError: Si las metricas no tienen ese campo.

    """
    for entrada in metricas["campos"]:
        if entrada["campo"] == campo:
            return float(entrada["f1"])
    raise ValueError(f"Las metricas no tienen el campo {campo}: no se puede aplicar la regla.")


def _puntaje(metricas: dict) -> float:
    """Promedia el F1 de los campos que deciden la competencia.

    Args:
        metricas: Contenido de un metricas.json.

    Returns:
        Promedio de los F1 de tipo_evento y es_reporte_accionable.

    """
    return sum(_f1(metricas, campo) for campo in CAMPOS_DECISIVOS) / len(CAMPOS_DECISIVOS)


def elegir(metricas_a: dict, metricas_b: dict) -> dict:
    """Aplica la regla de seleccion y devuelve la decision.

    Args:
        metricas_a: Metricas del primer candidato.
        metricas_b: Metricas del segundo candidato.

    Returns:
        Decision con el modelo ganador, la razon y las metricas que el
        registro de la configuracion necesita para los tags.

    Raises:
        ValueError: Si a un candidato le falta un campo decisivo, o si hay
            empate y ninguno de los dos es el modelo barato.

    """
    puntaje_a = _puntaje(metricas_a)
    puntaje_b = _puntaje(metricas_b)
    diferencia = abs(puntaje_a - puntaje_b)
    ganador, perdedor = (
        (metricas_a, metricas_b)
        if puntaje_a >= puntaje_b
        else (
            metricas_b,
            metricas_a,
        )
    )
    if diferencia >= UMBRAL:
        razon = (
            f"El F1 promedio de {ganador['modelo']} es mayor por {diferencia:.4f}, "
            f"por encima del margen de {UMBRAL}."
        )
    else:
        ganador = _barato(ganador, perdedor)
        razon = (
            f"La diferencia de F1 promedio es de {diferencia:.4f}, menor a {UMBRAL}. "
            f"Gana {MODELO_BARATO} por costo y latencia."
        )
    return {
        "ganador": ganador["modelo"],
        "razon": razon,
        "f1_tipo_evento": _f1(ganador, "tipo_evento"),
        "latencia_p95_ms": float(ganador["latencia_p95_ms"]),
    }


def _barato(ganador: dict, perdedor: dict) -> dict:
    """Devuelve el candidato barato, para aplicar el desempate.

    Args:
        ganador: Candidato con mayor puntaje.
        perdedor: Candidato con menor puntaje.

    Returns:
        El de los dos cuyo modelo es el barato.

    Raises:
        ValueError: Si ninguno de los dos es el modelo barato.

    """
    for candidato in (ganador, perdedor):
        if candidato["modelo"] == MODELO_BARATO:
            return candidato
    raise ValueError(
        f"Hay empate pero ninguno de los candidatos es {MODELO_BARATO}, "
        "y el desempate esta definido solo para ese modelo."
    )


def _leer_metricas(resultados: Path) -> dict:
    """Lee el metricas.json de la salida de un job evaluado.

    Args:
        resultados: Carpeta con el metricas.json del job.

    Returns:
        Contenido del metricas.json.

    Raises:
        FileNotFoundError: Si la carpeta no tiene metricas.json.

    """
    return json.loads((resultados / ARCHIVO_METRICAS).read_text(encoding="utf-8"))


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Define y resuelve los argumentos de la linea de comandos.

    Args:
        argv: Argumentos de la linea de comandos, o None para usar sys.argv.

    Returns:
        Espacio de nombres con los argumentos resueltos.

    """
    parser = argparse.ArgumentParser(description="Elige el modelo ganador entre dos evaluaciones")
    parser.add_argument("--resultados-a", type=Path, required=True, help="Carpeta del job A")
    parser.add_argument("--resultados-b", type=Path, required=True, help="Carpeta del job B")
    parser.add_argument("--salida", type=Path, required=True, help="Carpeta donde va decision.json")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de la linea de comandos.

    Args:
        argv: Argumentos de la linea de comandos, o None para usar sys.argv.

    Returns:
        Codigo de salida, 0 si se eligio ganador y 1 si no se pudo decidir.

    """
    args = _parse_args(argv)
    try:
        decision = elegir(_leer_metricas(args.resultados_a), _leer_metricas(args.resultados_b))
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(f"No se pudo decidir el ganador: {error}")
        return 1
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / ARCHIVO_DECISION).write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Ganador: {decision['ganador']}")
    print(f"Razon: {decision['razon']}")
    return 0
