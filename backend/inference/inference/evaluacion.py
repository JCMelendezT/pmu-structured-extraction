"""Evaluacion de los prompts del servicio de inferencia contra ejemplos gold.

Ejecuta la compuerta y la extraccion sobre cada ejemplo de un corpus anotado
y calcula exactitud y F1 por campo del esquema, junto con la latencia media
y el percentil 95. Genera un informe Markdown con el resumen, las matrices
de confusion por campo en forma de tablas legibles y las matrices con mayor
cantidad de errores.

Uso desde la raiz del repo:

    uv run --package inference python -m inference.evaluacion \
        --corpus eval-prompt/corpus/generado/corpus.jsonl \
        --report eval-prompt/report/evaluacion.md [--limite N]
"""

import argparse
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Sequence

from inference.proveedor import ProveedorGroq
from inference.servicio import ServicioInferencia
from inference.validador import RechazoSalida
from sirena_schema.schema import Compuerta, Naturaleza, Ubicacion, UbicacionExtraida

CAMPOS_COMPUERTA = ("es_reporte_accionable", "temporalidad", "intencion")
CAMPOS_NATURALEZA = ("tipo_evento", "servicio_de_respuesta")
CAMPOS_UBICACION = ("ubicacion_texto_literal", "punto_referencia")
CAMPOS_EVALUADOS = CAMPOS_COMPUERTA + CAMPOS_NATURALEZA + CAMPOS_UBICACION
MAX_VALORES_MATRIZ = 16
MAX_MATRICES_ERROR = 3
MAX_CONFUSIONES_POR_CAMPO = 3


@dataclass(frozen=True)
class EjemploGold:
    """Ejemplo del corpus con la salida esperada por el esquema.

    Attributes:
        texto: Mensaje ciudadano original que recibe el servicio.
        compuerta: Valores gold de la etapa de compuerta.
        naturaleza: Naturaleza gold, si el mensaje es accionable.
        ubicacion: Ubicacion gold, si el mensaje es accionable.

    """

    texto: str
    compuerta: Compuerta
    naturaleza: Naturaleza | None = None
    ubicacion: Ubicacion | None = None

    @classmethod
    def desde_dict(cls, datos: dict) -> "EjemploGold":
        """Construye un ejemplo a partir de un objeto JSON del corpus.

        Args:
            datos: Campos del ejemplo gold (texto, compuerta, naturaleza,
                ubicacion).

        Returns:
            Ejemplo gold con los objetos del esquema ya validados.

        """
        compuerta = Compuerta.model_validate(datos["compuerta"])
        naturaleza = (
            Naturaleza.model_validate(datos["naturaleza"])
            if datos.get("naturaleza") is not None
            else None
        )
        ubicacion = (
            Ubicacion.model_validate(datos["ubicacion"])
            if datos.get("ubicacion") is not None
            else None
        )
        return cls(
            texto=datos["texto"],
            compuerta=compuerta,
            naturaleza=naturaleza,
            ubicacion=ubicacion,
        )


@dataclass
class EvaluacionEjemplo:
    """Salida del servicio para un ejemplo y su latencia.

    Attributes:
        texto: Mensaje ciudadano evaluado.
        compuerta: Compuerta predicha, si no hubo error.
        naturaleza: Naturaleza predicha, si el mensaje es accionable.
        ubicacion: Ubicacion textual predicha, si el mensaje es accionable.
        error: Detalle del rechazo de validacion, si ocurrio.
        latencia_ms: Tiempo total de la evaluacion en milisegundos.

    """

    texto: str
    compuerta: Compuerta | None = None
    naturaleza: Naturaleza | None = None
    ubicacion: UbicacionExtraida | None = None
    error: str | None = None
    latencia_ms: float = 0.0


@dataclass(frozen=True)
class MetricaCampo:
    """Exactitud y F1 de un campo sobre los ejemplos donde tiene gold.

    Attributes:
        campo: Nombre del campo del esquema.
        evaluados: Cantidad de ejemplos con valor gold para el campo.
        exactitud: Proporcion de valores predichos identicos al gold.
        f1: F1 medio por ejemplo entre el valor predicho y el gold.

    """

    campo: str
    evaluados: int
    exactitud: float
    f1: float


@dataclass(frozen=True)
class Metricas:
    """Resumen numerico de una corrida de evaluacion.

    Attributes:
        campos: Metricas por campo del esquema.
        latencia_media_ms: Latencia promedio por ejemplo.
        latencia_p95_ms: Percentil 95 de la latencia por ejemplo.
        errores_validacion: Ejemplos rechazados por la validacion.
        total_ejemplos: Cantidad de ejemplos evaluados.

    """

    campos: list[MetricaCampo]
    latencia_media_ms: float
    latencia_p95_ms: float
    errores_validacion: int
    total_ejemplos: int


def cargar_corpus(ruta: Path) -> list[EjemploGold]:
    """Lee un corpus JSONL con la salida gold esperada por el esquema.

    Cada linea es un objeto JSON con los campos texto y compuerta, y
    opcionalmente naturaleza y ubicacion.

    Args:
        ruta: Ruta al archivo JSONL del corpus.

    Returns:
        Lista de ejemplos gold cargados.

    Raises:
        FileNotFoundError: Si la ruta del corpus no existe.

    """
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el corpus: {ruta}")
    ejemplos: list[EjemploGold] = []
    with ruta.open("r", encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue
            ejemplos.append(EjemploGold.desde_dict(json.loads(linea)))
    return ejemplos


class EvaluadorPrompts:
    """Corre el servicio de inferencia sobre los ejemplos del corpus.

    Attributes:
        servicio: Servicio de inferencia que se desea evaluar.

    """

    def __init__(self, servicio: ServicioInferencia) -> None:
        """Guarda el servicio de inferencia a evaluar.

        Args:
            servicio: Servicio con la etapa de compuerta y extraccion.

        """
        self._servicio = servicio

    def evaluar(self, ejemplos: Sequence[EjemploGold]) -> list[EvaluacionEjemplo]:
        """Evalua cada ejemplo y registra el resultado y la latencia.

        Args:
            ejemplos: Ejemplos gold del corpus a evaluar.

        Returns:
            Resultado de cada ejemplo en el mismo orden de entrada.

        """
        return [self._evaluar_ejemplo(ejemplo) for ejemplo in ejemplos]

    def _evaluar_ejemplo(self, ejemplo: EjemploGold) -> EvaluacionEjemplo:
        """Corre el servicio completo sobre un ejemplo.

        Args:
            ejemplo: Ejemplo gold a evaluar.

        Returns:
            Salida del servicio o el rechazo de validacion correspondiente.

        """
        inicio = time.perf_counter()
        try:
            compuerta = self._servicio.clasificar(ejemplo.texto)
            naturaleza: Naturaleza | None = None
            ubicacion: UbicacionExtraida | None = None
            if compuerta.es_reporte_accionable:
                naturaleza, ubicacion = self._servicio.extraer(ejemplo.texto)
        except RechazoSalida as error:
            return EvaluacionEjemplo(
                texto=ejemplo.texto,
                error=str(error),
                latencia_ms=_latencia_ms(inicio),
            )
        return EvaluacionEjemplo(
            texto=ejemplo.texto,
            compuerta=compuerta,
            naturaleza=naturaleza,
            ubicacion=ubicacion,
            latencia_ms=_latencia_ms(inicio),
        )


def metricas_por_campo(
    ejemplos: Sequence[EjemploGold],
    resultados: Sequence[EvaluacionEjemplo],
) -> Metricas:
    """Calcula exactitud, F1, latencias y errores de una corrida.

    Un campo se evalua solo cuando el ejemplo gold tiene valor para el;
    los campos opcionales sin gold no penalizan la prediccion.

    Args:
        ejemplos: Ejemplos gold evaluados en orden de entrada.
        resultados: Resultados del servicio en el mismo orden.

    Returns:
        Metricas por campo y resumen de latencia y errores.

    """
    aciertos = {campo: 0 for campo in CAMPOS_EVALUADOS}
    evaluados = {campo: 0 for campo in CAMPOS_EVALUADOS}
    f1_total = {campo: 0.0 for campo in CAMPOS_EVALUADOS}
    latencias: list[float] = []
    errores_validacion = 0
    for ejemplo, resultado in zip(ejemplos, resultados, strict=True):
        if resultado.error is not None:
            errores_validacion += 1
        if resultado.latencia_ms:
            latencias.append(resultado.latencia_ms)
        for campo in CAMPOS_EVALUADOS:
            gold = _valor_gold(ejemplo, campo)
            if gold is None:
                continue
            exacto, f1 = _comparar_conjunto(_valor_predicho(resultado, campo), gold)
            aciertos[campo] += 1 if exacto else 0
            evaluados[campo] += 1
            f1_total[campo] += f1
    return Metricas(
        campos=[
            MetricaCampo(
                campo=campo,
                evaluados=evaluados[campo],
                exactitud=_proporcion(aciertos[campo], evaluados[campo]),
                f1=_proporcion(f1_total[campo], evaluados[campo]),
            )
            for campo in CAMPOS_EVALUADOS
        ],
        latencia_media_ms=fmean(latencias) if latencias else 0.0,
        latencia_p95_ms=_p95(latencias) if latencias else 0.0,
        errores_validacion=errores_validacion,
        total_ejemplos=len(ejemplos),
    )


def matriz_confusion(
    ejemplos: Sequence[EjemploGold],
    resultados: Sequence[EvaluacionEjemplo],
    campo: str,
) -> dict[str, dict[str, int]]:
    """Cuenta las coincidencias por valor entre lo predicho y el gold.

    Desnormaliza los campos multivaluados expandiendo cada valor de la
    lista como una entrada independiente en la matriz.

    Args:
        ejemplos: Ejemplos gold evaluados en orden de entrada.
        resultados: Resultados del servicio en el mismo orden.
        campo: Nombre del campo del esquema.

    Returns:
        Diccionario anidado valor_gold -> valor_predicho -> cantidad.

    """
    cuentas: dict[str, dict[str, int]] = {}
    for ejemplo, resultado in zip(ejemplos, resultados, strict=True):
        gold = _valor_gold(ejemplo, campo)
        if gold is None:
            continue
        predicho = _valor_predicho(resultado, campo)
        for valor_gold in _a_conjunto(gold):
            fila = cuentas.setdefault(valor_gold, {})
            for valor_predicho in _a_conjunto(predicho):
                fila[valor_predicho] = fila.get(valor_predicho, 0) + 1
    return cuentas


def generar_informe(
    metricas: Metricas,
    resultados: Sequence[EvaluacionEjemplo],
    ruta: Path,
    matrices_confusion: dict[str, dict[str, dict[str, int]]] | None = None,
) -> None:
    """Escribe el informe de evaluacion en formato Markdown.

    Incluye, cuando se calculan, las matrices de confusion por campo en
    forma de tablas legibles y una seccion que destaca las matrices con
    mayor cantidad de errores y explica sus confusiones dominantes.

    Args:
        metricas: Resumen numerico de la corrida.
        resultados: Resultados por ejemplo para listar los errores.
        ruta: Ruta donde se escribira el informe.
        matrices_confusion: Matrices por campo calculadas por
            matriz_confusion, si se desea incluir su vista legible.

    """
    lineas = [
        "# Informe de evaluacion de prompts",
        "",
        f"- Generado: {datetime.now().isoformat(timespec='seconds')}",
        f"- Ejemplos: {metricas.total_ejemplos}",
        f"- Errores de validacion: {metricas.errores_validacion}",
        "",
        "## Metricas por campo",
        "",
        "| Campo | Evaluados | Exactitud | F1 |",
        "|---|---:|---:|---:|",
    ]
    for metrica in metricas.campos:
        lineas.append(
            f"| {metrica.campo} | {metrica.evaluados} | "
            f"{metrica.exactitud:.3f} | {metrica.f1:.3f} |"
        )
    lineas.extend(
        [
            "",
            "## Latencia",
            "",
            f"- Media: {metricas.latencia_media_ms:.1f} ms",
            f"- P95: {metricas.latencia_p95_ms:.1f} ms",
        ]
    )
    if matrices_confusion is not None:
        lineas.extend(_seccion_matrices(matrices_confusion))
        lineas.extend(_seccion_matrices_error(metricas, matrices_confusion))
    con_error = [resultado for resultado in resultados if resultado.error is not None]
    if con_error:
        lineas.extend(["", "## Ejemplos con error", ""])
        for resultado in con_error:
            lineas.append(f"- {resultado.texto!r}: {resultado.error}")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def _seccion_matrices(
    matrices_confusion: dict[str, dict[str, dict[str, int]]],
) -> list[str]:
    """Genera las tablas legibles de las matrices de confusion por campo.

    Args:
        matrices_confusion: Matrices por campo de matriz_confusion.

    Returns:
        Lineas de Markdown con una tabla por campo evaluado.

    """
    lineas = ["", "## Matrices de confusion", ""]
    for campo in CAMPOS_EVALUADOS:
        lineas.extend(_render_matriz_confusion(campo, matrices_confusion.get(campo, {})))
    return lineas


def _seccion_matrices_error(
    metricas: Metricas,
    matrices_confusion: dict[str, dict[str, dict[str, int]]],
) -> list[str]:
    """Genera la seccion que destaca las matrices con mayor error.

    Args:
        metricas: Resumen numerico de la corrida.
        matrices_confusion: Matrices por campo de matriz_confusion.

    Returns:
        Lineas de Markdown con las matrices mas confusas y su explicacion.

    """
    lineas: list[str] = ["", "## Matrices con mayor error", ""]
    destacadas = _matrices_con_mas_error(matrices_confusion)
    if not destacadas:
        lineas.append("_Esta corrida no tuvo errores de clasificacion._")
        return lineas
    lineas.append(f"Las {len(destacadas)} matrices con mas errores de esta corrida:")
    for campo, errores, evaluados, confusiones in destacadas:
        lineas.extend([f"### {campo} — {errores} errores de {evaluados} evaluados", ""])
        for oro, predicho, cantidad in confusiones:
            lineas.append(f"- {_explicar_confusion(campo, oro, predicho, cantidad)}")
        lineas.append("")
    return lineas


def _matrices_con_mas_error(
    matrices_confusion: dict[str, dict[str, dict[str, int]]],
) -> list[tuple[str, int, int, list[tuple[str, str, int]]]]:
    """Rankea las matrices por cantidad de errores fuera de la diagonal.

    Args:
        matrices_confusion: Matrices por campo de matriz_confusion.

    Returns:
        Tuplas (campo, errores, evaluados, confusiones) con las
        MAX_MATRICES_ERROR matrices de mayor error, ordenadas de mayor
        a menor cantidad de errores.

    """
    errores_por_campo: list[tuple[str, int, int, list[tuple[str, str, int]]]] = []
    for campo in CAMPOS_EVALUADOS:
        matriz = matrices_confusion.get(campo, {})
        evaluados = sum(cantidad for fila in matriz.values() for cantidad in fila.values())
        errores = sum(
            cantidad
            for oro, fila in matriz.items()
            for predicho, cantidad in fila.items()
            if oro != predicho
        )
        if errores:
            errores_por_campo.append((campo, errores, evaluados, _confusiones_top(matriz)))
    errores_por_campo.sort(key=lambda entrada: entrada[1], reverse=True)
    return errores_por_campo[:MAX_MATRICES_ERROR]


def _confusiones_top(
    matriz: dict[str, dict[str, int]],
) -> list[tuple[str, str, int]]:
    """Devuelve los pares oro->predicho mas confundidos del campo.

    Args:
        matriz: Mapeo valor_gold -> valor_predicho -> cantidad.

    Returns:
        Pares (gold, predicho, cantidad) distintos de la diagonal,
        ordenados de mayor a menor cantidad.

    """
    pares = [
        (oro, predicho, cantidad)
        for oro, fila in matriz.items()
        for predicho, cantidad in fila.items()
        if oro != predicho
    ]
    pares.sort(key=lambda par: par[2], reverse=True)
    return pares[:MAX_CONFUSIONES_POR_CAMPO]


def _explicar_confusion(campo: str, oro: str, predicho: str, cantidad: int) -> str:
    """Describe en espanol una confusion dominante de un campo.

    Args:
        campo: Campo del esquema al que pertenece la matriz.
        oro: Valor gold confundido.
        predicho: Valor predicho incorrecto.
        cantidad: Ejemplos con esa confusion.

    Returns:
        Frase de una linea que describe el patron de error.

    """
    if campo == "es_reporte_accionable":
        if oro == "true":
            return f"{cantidad} ejemplos: reporte accionable clasificado como no accionable"
        return f"{cantidad} ejemplos: no accionable clasificado como accionable"
    if campo in CAMPOS_UBICACION:
        return f"{cantidad} ejemplos: recupera {predicho!r} en lugar de {oro!r}"
    return f"{cantidad} ejemplos: asigna {predicho!r} en lugar de {oro!r}"


def _render_matriz_confusion(
    campo: str,
    matriz: dict[str, dict[str, int]],
) -> list[str]:
    """Genera la tabla Markdown legible de la matriz de confusion de un campo.

    Para campos de alta cardinalidad (por ejemplo, textos libres) solo se
    muestran los MAX_VALORES_MATRIZ valores mas frecuentes y el resto se
    agrupa bajo "otros", manteniendo la tabla acotada. La diagonal correcta
    se resalta en negrita y se agregan totales de filas y columnas.

    Args:
        campo: Nombre del campo evaluado.
        matriz: Mapeo valor_gold -> valor_predicho -> cantidad.

    Returns:
        Lineas de Markdown con la tabla del campo evaluado.

    """
    if not matriz:
        return [f"### {campo}", "", "_Sin ejemplos con oro para este campo._", ""]
    total_oro: dict[str, int] = {}
    total_predicho: dict[str, int] = {}
    for oro, fila in matriz.items():
        total_oro[oro] = sum(fila.values())
        for predicho, cantidad in fila.items():
            total_predicho[predicho] = total_predicho.get(predicho, 0) + cantidad
    visibles = sorted(
        set(total_oro) | set(total_predicho),
        key=lambda valor: (valor not in total_oro, -total_oro.get(valor, 0), valor),
    )
    visibles = visibles[:MAX_VALORES_MATRIZ]
    reducida = _agregar_otros(matriz, visibles)
    filas = [oro for oro in visibles if oro in reducida]
    if "otros" in reducida:
        filas.append("otros")
    columnas = [valor for valor in visibles if any(valor in fila for fila in reducida.values())]
    hay_otros = any("otros" in fila for fila in reducida.values())
    if hay_otros:
        columnas.append("otros")

    cabecera = (
        "| Oro \\ Predicho | "
        + " | ".join(_etiqueta_matriz(valor) for valor in columnas)
        + " | Total |"
    )
    celdas_separador = [":---"] + ["---:"] * (len(columnas) + 1)
    separador = "|" + "|".join(celdas_separador) + "|"
    lineas = [f"### {campo}", "", cabecera, separador]
    totales_columna = [0] * len(columnas)
    for oro in filas:
        fila = reducida[oro]
        celdas = [f"**{_etiqueta_matriz(oro)}**"]
        for indice, predicho in enumerate(columnas):
            cantidad = fila.get(predicho, 0)
            totales_columna[indice] += cantidad
            celdas.append(f"**{cantidad}**" if oro == predicho else str(cantidad))
        celdas.append(str(sum(fila.values())))
        lineas.append("| " + " | ".join(celdas) + " |")
    celdas_total = ["**Total**"] + [str(t) for t in totales_columna]
    lineas.append("| " + " | ".join(celdas_total) + " |")
    return lineas


def _agregar_otros(
    matriz: dict[str, dict[str, int]],
    visibles: set[str] | list[str],
) -> dict[str, dict[str, int]]:
    """Agrupa bajo "otros" los valores no visibles de una matriz.

    Args:
        matriz: Mapeo valor_gold -> valor_predicho -> cantidad.
        visibles: Conjunto de valores que si se muestran en la tabla.

    Returns:
        Matriz reducida donde los valores ocultos se consolidan en "otros".

    """
    visibles_set = set(visibles)
    reducida: dict[str, dict[str, int]] = {}
    for oro, fila in matriz.items():
        oro_visto = oro if oro in visibles_set else "otros"
        for predicho, cantidad in fila.items():
            predicho_visto = predicho if predicho in visibles_set else "otros"
            reducida.setdefault(oro_visto, {})
            reducida[oro_visto][predicho_visto] = (
                reducida[oro_visto].get(predicho_visto, 0) + cantidad
            )
    return reducida


def _etiqueta_matriz(valor: str) -> str:
    """Devuelve la etiqueta Markdown de un valor de la matriz.

    Args:
        valor: Valor del esquema (puede ser la cadena vacia).

    Returns:
        El valor tal cual, o "_vacio_" cuando es la cadena vacia.

    """
    return valor if valor else "_vacio_"


def _latencia_ms(inicio: float) -> float:
    """Devuelve los milisegundos transcurridos desde un instante.

    Args:
        inicio: Resultado previo de time.perf_counter().

    Returns:
        Milisegundos transcurridos desde el instante de inicio.

    """
    return (time.perf_counter() - inicio) * 1000


def _valor_gold(ejemplo: EjemploGold, campo: str) -> object:
    """Devuelve el valor gold de un campo del ejemplo.

    Args:
        ejemplo: Ejemplo gold del que se toma el valor.
        campo: Nombre del campo del esquema.

    Returns:
        Valor gold del campo, o None si no aplica al ejemplo.

    """
    if campo in CAMPOS_COMPUERTA:
        return getattr(ejemplo.compuerta, campo)
    if campo in CAMPOS_NATURALEZA:
        return getattr(ejemplo.naturaleza, campo) if ejemplo.naturaleza else None
    return getattr(ejemplo.ubicacion, campo) if ejemplo.ubicacion else None


def _valor_predicho(resultado: EvaluacionEjemplo, campo: str) -> object:
    """Devuelve el valor predicho de un campo del resultado.

    Args:
        resultado: Resultado del servicio del que se toma el valor.
        campo: Nombre del campo del esquema.

    Returns:
        Valor predicho del campo, o None si no fue producido.

    """
    if campo in CAMPOS_COMPUERTA:
        return getattr(resultado.compuerta, campo) if resultado.compuerta else None
    if campo in CAMPOS_NATURALEZA:
        return getattr(resultado.naturaleza, campo) if resultado.naturaleza else None
    return getattr(resultado.ubicacion, campo) if resultado.ubicacion else None


def _comparar_conjunto(predicho: object, gold: object) -> tuple[bool, float]:
    """Compara un valor predicho contra el gold en exactitud y F1.

    Compara como conjuntos para que los campos multivaluados, por ejemplo
    los servicios de respuesta, midan el solapamiento parcial.

    Args:
        predicho: Valor producido por el servicio.
        gold: Valor esperado en el corpus.

    Returns:
        Tupla con la coincidencia exacta y el F1 (1.0 si ambos vacios).

    """
    predicto = _a_conjunto(predicho)
    golds = _a_conjunto(gold)
    interseccion = len(predicto & golds)
    exacto = predicto == golds
    if not predicto and not golds:
        return exacto, 1.0
    if interseccion == 0:
        return exacto, 0.0
    precision = interseccion / len(predicto)
    recall = interseccion / len(golds)
    return exacto, 2 * precision * recall / (precision + recall)


def _a_conjunto(valor: object) -> set[str]:
    """Convierte un valor del esquema en un conjunto normalizado.

    Args:
        valor: Valor escalar o lista del esquema.

    Returns:
        Conjunto de cadenas normalizadas; un None se vuelve el valor nulo.

    """
    if isinstance(valor, (list, tuple)):
        return {_normalizar(item) for item in valor}
    return {_normalizar(valor)}


def _normalizar(valor: object) -> str:
    """Normaliza un valor para compararlo de forma estable.

    Args:
        valor: Valor del esquema a normalizar.

    Returns:
        Cadena sin espacios laterales y en minusculas.

    """
    return str(valor).strip().casefold() if isinstance(valor, str) else str(valor)


def _proporcion(aciertos: float, total: int) -> float:
    """Calcula una proporcion evitando la division por cero.

    Args:
        aciertos: Cantidad de casos acertados.
        total: Cantidad de casos evaluados.

    Returns:
        Proporcion entre 0 y 1, o 0 si no hay casos evaluados.

    """
    return aciertos / total if total else 0.0


def _p95(valores: Sequence[float]) -> float:
    """Calcula el percentil 95 de una secuencia.

    Args:
        valores: Secuencia de latencias en milisegundos.

    Returns:
        Percentil 95 de la secuencia ordenada.

    """
    ordenados = sorted(valores)
    indice = max(0, math.ceil(0.95 * len(ordenados)) - 1)
    return ordenados[indice]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Define y resuelve los argumentos de la linea de comandos.

    Args:
        argv: Argumentos de la linea de comandos, o None para usar sys.argv.

    Returns:
        Espacio de nombres con los argumentos resueltos.

    """
    parser = argparse.ArgumentParser(
        description="Evalua los prompts del servicio de inferencia contra un corpus"
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="Archivo JSONL del corpus con salida gold",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Ruta del informe Markdown (por defecto, con marca de tiempo)",
    )
    parser.add_argument(
        "--limite",
        type=int,
        default=None,
        help="Evalua solo los primeros N ejemplos del corpus",
    )
    return parser.parse_args(argv)


def _ruta_informe_por_defecto() -> Path:
    """Devuelve la ruta por defecto del informe con marca de tiempo.

    Returns:
        Ruta en eval-prompt/report con la fecha y hora de la corrida.

    """
    nombre = datetime.now().strftime("evaluacion_%Y%m%d_%H%M%S.md")
    return Path("eval-prompt/report") / nombre


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de la linea de comandos.

    Args:
        argv: Argumentos de la linea de comandos, o None para usar sys.argv.

    Returns:
        Codigo de salida, 0 si la corrida finalizo correctamente.

    """
    args = _parse_args(argv)
    ejemplos = cargar_corpus(args.corpus)
    if args.limite is not None:
        ejemplos = ejemplos[: args.limite]
    servicio = ServicioInferencia(ProveedorGroq())
    evaluador = EvaluadorPrompts(servicio)
    resultados = evaluador.evaluar(ejemplos)
    metricas = metricas_por_campo(ejemplos, resultados)
    matrices = {campo: matriz_confusion(ejemplos, resultados, campo) for campo in CAMPOS_EVALUADOS}
    ruta = args.report if args.report is not None else _ruta_informe_por_defecto()
    generar_informe(metricas, resultados, ruta, matrices_confusion=matrices)
    from inference.registro import registrar_corrida

    run_id = registrar_corrida(
        metricas=metricas,
        ejemplos=ejemplos,
        resultados=resultados,
        ruta_informe=ruta,
        corpus=args.corpus,
        matrices_confusion=matrices,
    )
    print(f"Informe generado en {ruta}")
    if run_id:
        print(f"Corrida registrada en MLflow: {run_id}")
    print(
        "Ejemplos: "
        f"{metricas.total_ejemplos} | Errores de validacion: "
        f"{metricas.errores_validacion} | Latencia media: "
        f"{metricas.latencia_media_ms:.1f} ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
