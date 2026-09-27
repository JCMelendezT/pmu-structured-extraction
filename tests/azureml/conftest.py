"""Hace importables los scripts de azureml/src en las pruebas.

azureml/src no es un paquete del workspace de uv, porque estos scripts se
ejecutan como programa dentro del contenedor de Azure ML, no se importan.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SRC = RAIZ / "azureml" / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
