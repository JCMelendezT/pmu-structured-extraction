"""Valida el corpus gold_v1 antes de evaluar y prepara la salida del pipeline.

Recalcula el SHA-256 de los tres `.jsonl` congelados y lo compara con lo que
declara `README_gold_v1.md`. Si algo no coincide, falla el job: es preferible
que la evaluacion no corra antes que medir contra un corpus que cambio.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

ARCHIVOS_CON_CHECKSUM = ("dev.jsonl", "eval.jsonl", "gold_standard_v1.jsonl")
NOMBRE_README = "README_gold_v1.md"
NOMBRE_MANIFESTO = "manifest.json"
CARPETA_EVAL = "gold_v1"

_FILA_CHECKSUM = re.compile(
    r"^\|\s*`(?P<nombre>[^`]+)`\s*\|\s*`(?P<sha256>[0-9a-f]{64})`\s*\|",
    re.MULTILINE,
)


class ChecksumNoCoincide(RuntimeError):
    """El corpus no coincide con los checksums congelados en el README."""


def _sha256(ruta: Path) -> str:
    """Devuelve el SHA-256 de un archivo, leido en binario."""
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _contar_ejemplos(ruta: Path) -> int:
    """Cuenta las lineas con contenido de un JSONL."""
    with ruta.open(encoding="utf-8") as archivo:
        return sum(1 for linea in archivo if linea.strip())


def leer_checksums(readme: Path) -> dict[str, str]:
    """Extrae la tabla de checksums del README.

    Args:
        readme: Ruta a `README_gold_v1.md`.

    Returns:
        Diccionario de nombre de archivo a SHA-256, con lo que el README declara.

    """
    texto = readme.read_text(encoding="utf-8")
    return {m["nombre"]: m["sha256"] for m in _FILA_CHECKSUM.finditer(texto)}


def _verificar(raiz: Path, declarados: dict[str, str]) -> None:
    """Comprueba que los tres JSONL exista y coincida su SHA-256 con el README.

    Args:
        raiz: Carpeta que contiene el corpus y su README.
        declarados: Checksums extraidos del README.

    Raises:
        ChecksumNoCoincide: Si el README no declara un archivo obligatorio, si
            el archivo falta, o si el SHA-256 calculado no coincide.

    """
    for nombre in ARCHIVOS_CON_CHECKSUM:
        if nombre not in declarados:
            raise ChecksumNoCoincide(f"{NOMBRE_README} no declara el checksum de {nombre}")
        ruta = raiz / nombre
        if not ruta.is_file():
            raise ChecksumNoCoincide(f"Falta el archivo {nombre} en el corpus")
        calculado = _sha256(ruta)
        if calculado != declarados[nombre]:
            raise ChecksumNoCoincide(
                f"{nombre} no coincide con el checksum congelado: "
                f"esperado {declarados[nombre]}, calculado {calculado}"
            )


def validar(raiz: Path, salida: Path) -> dict[str, Any]:
    """Valida el corpus y escribe `gold_v1/eval.jsonl` mas el manifiesto.

    Todos los checksums se verifican antes de escribir nada, para que un fallo
    no deje una salida a medias que otro paso podria tomar como valida.

    Args:
        raiz: Carpeta que contiene el corpus y su `README_gold_v1.md`.
        salida: Carpeta de salida del componente.

    Returns:
        El manifiesto escrito, tal como queda en disco.

    Raises:
        ChecksumNoCoincide: Si el README falta o el corpus no coincide con el.

    """
    readme = raiz / NOMBRE_README
    if not readme.is_file():
        raise ChecksumNoCoincide(f"No se encontro {NOMBRE_README} en el corpus")

    _verificar(raiz, leer_checksums(readme))

    archivos = []
    for ruta in sorted(raiz.iterdir()):
        if not ruta.is_file():
            continue
        es_jsonl = ruta.suffix == ".jsonl"
        archivos.append(
            {
                "nombre": ruta.name,
                "sha256": _sha256(ruta) if ruta.name in ARCHIVOS_CON_CHECKSUM else None,
                "conteo": _contar_ejemplos(ruta) if es_jsonl else None,
            }
        )
    manifiesto = {"raiz": raiz.name, "archivos": archivos}

    destino = salida / CARPETA_EVAL / "eval.jsonl"
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(raiz / "eval.jsonl", destino)
    (salida / NOMBRE_MANIFESTO).write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifiesto


def main(argv: list[str] | None = None) -> int:
    """Ejecuta la validacion desde la linea de comandos.

    Args:
        argv: Argumentos de la linea de comandos; si es `None`, usa `sys.argv`.

    Returns:
        0 si el corpus es valido.

    """
    parser = argparse.ArgumentParser(description="Valida el corpus gold_v1.")
    parser.add_argument("--entrada", type=Path, required=True, help="Carpeta del corpus")
    parser.add_argument("--salida", type=Path, required=True, help="Carpeta de salida")
    argumentos = parser.parse_args(argv)

    manifiesto = validar(argumentos.entrada, argumentos.salida)
    conteos = ", ".join(
        f"{archivo['nombre']}={archivo['conteo']}"
        for archivo in manifiesto["archivos"]
        if archivo["conteo"] is not None
    )
    print(f"Corpus valido: {conteos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
