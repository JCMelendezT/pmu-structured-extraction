"""Obtiene la clave de Groq para el job sin exponerla en ningun log.

La clave llega por variable de entorno: el Environment de Azure ML la inyecta
desde el Key Vault del workspace usando la identidad administrada del job. Por
eso este modulo no abre ningun cliente de Azure ni imprime el valor. Si la
variable no llega, el error dice como cablearla en vez de suprimirlo.
"""

from __future__ import annotations

import os


class SecretoNoEncontrado(RuntimeError):
    """La variable de entorno con el secreto no llego al job."""


def leer_secreto(nombre: str) -> str:
    """Devuelve el valor del secreto, o falla indicando como cablearlo.

    Args:
        nombre: Nombre de la variable de entorno, por ejemplo `GROQ_API_KEY`.

    Returns:
        El valor del secreto.

    Raises:
        SecretoNoEncontrado: Si la variable no existe o llega vacia. El mensaje
            nombra la variable y la referencia de Key Vault que debe llevarla al
            job, pero nunca incluye ningun valor.

    """
    valor = os.environ.get(nombre, "")
    if not valor:
        raise SecretoNoEncontrado(
            f"Falta la variable {nombre}. El job debe recibirla desde el Key Vault "
            f"del workspace (referencia de Key Vault en el Environment "
            f"sirena-eval) o exportarla en environment_variables del pipeline."
        )
    return valor
