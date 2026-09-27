"""Pruebas del evaluador de prompts con un proveedor sin red."""

import json

import pytest

from inference.evaluacion import (
    EvaluacionEjemplo,
    EvaluadorPrompts,
    EjemploGold,
    cargar_corpus,
    generar_informe,
    metricas_por_campo,
    matriz_confusion,
)
from inference.servicio import ServicioInferencia
from sirena_schema.schema import Compuerta, Naturaleza, Ubicacion


class ProveedorProgramado:
    """Proveedor sin red con respuestas JSON segun la etapa del prompt.

    Detecta la etapa por el texto de sistema ("extractor" identifica la
    extraccion) y agota primero las respuestas de la cola de cada etapa.

    Attributes:
        compuertas: Respuestas de la etapa de compuerta.
        extracciones: Respuestas de la etapa de extraccion.

    """

    def __init__(self, compuertas: list[str], extracciones: list[str] | None = None) -> None:
        """Guarda las respuestas preprogramadas de cada etapa.

        Args:
            compuertas: Respuestas crudas de la compuerta, en orden.
            extracciones: Respuestas crudas de la extraccion, en orden.

        """
        self.compuertas = compuertas
        self.extracciones = list(extracciones or [])

    def completar(self, sistema: str, usuario: str) -> str:
        """Devuelve la siguiente respuesta de la etapa correspondiente.

        Args:
            sistema: Instrucciones de sistema de la etapa.
            usuario: Mensaje de usuario (se ignora en la prueba).

        Returns:
            Ultima respuesta programada de la etapa o la siguiente de la cola.

        """
        cola = self.extracciones if "extractor" in sistema else self.compuertas
        if len(cola) > 1:
            return cola.pop(0)
        return cola[0]


COMPUERTA_ACCIONABLE = (
    '{"es_reporte_accionable": true, "temporalidad": "ocurriendo_ahora", '
    '"intencion": "solicita_ayuda"}'
)
COMPUERTA_NO_ACCIONABLE = (
    '{"es_reporte_accionable": false, '
    '"temporalidad": "referencia_noticia", '
    '"intencion": "solicita_informacion"}'
)
EXTRACCION_SISMO = (
    '{"naturaleza": {"tipo_evento": "sismo", "servicio_de_respuesta": ["A"]}, '
    '"ubicacion": {"ubicacion_texto_literal": "Calle 5", '
    '"punto_referencia": null}}'
)
EXTRACCION_INCENDIO = (
    '{"naturaleza": {"tipo_evento": "incendio_estructural", '
    '"servicio_de_respuesta": ["B", "G"]}, "ubicacion": '
    '{"ubicacion_texto_literal": "Calle 1", "punto_referencia": "Parque"}}'
)


def _ejemplo_sismo() -> EjemploGold:
    """Construye un ejemplo gold accionable de tipo sismo.

    Returns:
        Ejemplo gold con naturaleza y ubicacion completas.

    """
    return EjemploGold(
        texto="temblor en el centro, me estoy quedando sin oxigeno",
        compuerta=Compuerta.model_validate(
            {
                "es_reporte_accionable": True,
                "temporalidad": "ocurriendo_ahora",
                "intencion": "solicita_ayuda",
            }
        ),
        naturaleza=Naturaleza.model_validate(
            {
                "tipo_evento": "sismo",
                "servicio_de_respuesta": ["A"],
            }
        ),
        ubicacion=Ubicacion.model_validate(
            {
                "ubicacion_texto_literal": "Calle 5",
                "barrio": "Centro",
                "comuna": "3",
                "punto_referencia": "Plaza de Caycedo",
                "nivel_granularidad": "exacta",
                "lat": None,
                "lon": None,
            }
        ),
    )


def _ejemplo_incendio() -> EjemploGold:
    """Construye un ejemplo gold accionable de incendio.

    Returns:
        Ejemplo gold con naturaleza y ubicacion completas.

    """
    return EjemploGold(
        texto="se quema una casa en el penon",
        compuerta=Compuerta.model_validate(
            {
                "es_reporte_accionable": False,
                "temporalidad": "ya_ocurrio",
                "intencion": "reporta_terceros",
            }
        ),
        naturaleza=Naturaleza.model_validate(
            {
                "tipo_evento": "incendio_estructural",
                "servicio_de_respuesta": ["B", "G"],
            }
        ),
        ubicacion=Ubicacion.model_validate(
            {
                "ubicacion_texto_literal": "Calle 1",
                "barrio": "El Pefion",
                "comuna": "7",
                "punto_referencia": "Parque",
                "nivel_granularidad": "barrio",
                "lat": None,
                "lon": None,
            }
        ),
    )


def _ejemplo_noticia() -> EjemploGold:
    """Construye un ejemplo gold no accionable.

    Returns:
        Ejemplo gold sin naturaleza ni ubicacion.

    """
    return EjemploGold(
        texto="vi en las noticias una alerta del clima",
        compuerta=Compuerta.model_validate(
            {
                "es_reporte_accionable": False,
                "temporalidad": "referencia_noticia",
                "intencion": "solicita_informacion",
            }
        ),
    )


class TestCargarCorpus:
    """Pruebas de cargar_corpus."""

    def test_lee_ejemplos_jsonl_con_gold(self, tmp_path) -> None:
        """Construye EjemploGold a partir de las lineas del corpus."""
        # Arrange
        ruta = tmp_path / "corpus.jsonl"
        ruta.write_text(
            json.dumps(
                {
                    "texto": "temblor en el centro",
                    "compuerta": {
                        "es_reporte_accionable": True,
                        "temporalidad": "ocurriendo_ahora",
                        "intencion": "solicita_ayuda",
                    },
                    "naturaleza": {
                        "tipo_evento": "sismo",
                        "servicio_de_respuesta": ["A"],
                    },
                    "ubicacion": {
                        "ubicacion_texto_literal": "Calle 5",
                        "barrio": "Centro",
                        "comuna": "3",
                        "punto_referencia": None,
                        "nivel_granularidad": "exacta",
                        "lat": None,
                        "lon": None,
                    },
                }
            )
            + "\n"
            + json.dumps(
                {
                    "texto": "vi una noticia",
                    "compuerta": {
                        "es_reporte_accionable": False,
                        "temporalidad": "referencia_noticia",
                        "intencion": "solicita_informacion",
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )

        # Act
        ejemplos = cargar_corpus(ruta)

        # Assert
        assert len(ejemplos) == 2
        assert ejemplos[0].naturaleza is not None
        assert ejemplos[0].ubicacion is not None
        assert ejemplos[0].ubicacion.barrio == "Centro"
        assert ejemplos[1].naturaleza is None
        assert ejemplos[1].ubicacion is None

    def test_salta_lineas_vacias(self, tmp_path) -> None:
        """Ignora lineas en blanco del archivo del corpus."""
        # Arrange
        ruta = tmp_path / "corpus.jsonl"
        ruta.write_text(
            json.dumps(
                {
                    "texto": "temblor",
                    "compuerta": {
                        "es_reporte_accionable": True,
                        "temporalidad": "ocurriendo_ahora",
                        "intencion": "solicita_ayuda",
                    },
                }
            )
            + "\n\n",
            encoding="utf-8",
        )

        # Act
        ejemplos = cargar_corpus(ruta)

        # Assert
        assert len(ejemplos) == 1

    def test_ruta_inexistente_levanta_error(self, tmp_path) -> None:
        """Falla con FileNotFoundError cuando no existe el archivo."""
        # Arrange & Act & Assert
        with pytest.raises(FileNotFoundError):
            cargar_corpus(tmp_path / "no_existe.jsonl")

    def test_linea_invalida_levanta_error(self, tmp_path) -> None:
        """Propaga el error de decodificado de una linea corrupta."""
        # Arrange
        ruta = tmp_path / "corpus.jsonl"
        ruta.write_text("{no valido}\n", encoding="utf-8")

        # Act & Assert
        with pytest.raises(json.JSONDecodeError):
            cargar_corpus(ruta)


class TestEvaluadorPrompts:
    """Pruebas de EvaluadorPrompts.evaluar."""

    def test_evalua_accionables_y_no_accionables(self) -> None:
        """Procesa cada ejemplo y respeta la etapa de compuerta."""
        # Arrange
        proveedor = ProveedorProgramado(
            compuertas=[
                COMPUERTA_ACCIONABLE,
                COMPUERTA_NO_ACCIONABLE,
                COMPUERTA_NO_ACCIONABLE,
            ],
            extracciones=[EXTRACCION_SISMO],
        )
        evaluador = EvaluadorPrompts(ServicioInferencia(proveedor))

        # Act
        resultados = evaluador.evaluar([_ejemplo_sismo(), _ejemplo_incendio(), _ejemplo_noticia()])

        # Assert
        assert len(resultados) == 3
        assert resultados[0].error is None
        assert resultados[0].compuerta is not None
        assert resultados[0].naturaleza is not None
        assert resultados[0].ubicacion is not None
        assert resultados[1].naturaleza is None  # no accionable en la etapa 1
        assert resultados[2].naturaleza is None

    def test_registra_rechazo_de_validacion(self) -> None:
        """Captura el rechazo del esquema como error del ejemplo."""
        # Arrange
        proveedor = ProveedorProgramado(compuertas=['{"es_reporte_accionable": "si"}'])
        evaluador = EvaluadorPrompts(ServicioInferencia(proveedor))

        # Act
        resultados = evaluador.evaluar([_ejemplo_sismo()])

        # Assert
        assert resultados[0].error is not None
        assert "compuerta" in resultados[0].error


class TestMetricas:
    """Pruebas de metricas_por_campo."""

    def test_corrida_perfecta_da_exactitud_y_f1_plenos(self) -> None:
        """Un desempeno identico al gold alcanza 1.0 en todo campo."""
        # Arrange
        gold = _ejemplo_sismo()
        resultado = EvaluacionEjemplo(
            texto=gold.texto,
            compuerta=gold.compuerta,
            naturaleza=gold.naturaleza,
            ubicacion=gold.ubicacion,
            latencia_ms=100.0,
        )

        # Act
        metricas = metricas_por_campo([gold], [resultado])

        # Assert
        for campo in metricas.campos:
            assert campo.exactitud == 1.0
            assert campo.f1 == 1.0
        assert metricas.errores_validacion == 0

    def test_f1_parcial_en_servicio_de_respuesta(self) -> None:
        """Un servicio faltante baja el F1 sin anular la exactitud del resto."""
        # Arrange
        gold = _ejemplo_incendio()
        resultado = EvaluacionEjemplo(
            texto=gold.texto,
            compuerta=gold.compuerta,
            naturaleza=Naturaleza.model_validate(
                {
                    "tipo_evento": "incendio_estructural",
                    "servicio_de_respuesta": ["B"],
                }
            ),
            ubicacion=gold.ubicacion,
        )

        # Act
        metricas = metricas_por_campo([gold], [resultado])

        # Assert
        servicios = next(
            campo for campo in metricas.campos if campo.campo == "servicio_de_respuesta"
        )
        assert servicios.exactitud == 0.0
        assert servicios.f1 == pytest.approx(2 / 3)

    def test_gold_sin_campo_no_penaliza(self) -> None:
        """Los campos opcionales sin gold no se evaluan."""
        # Arrange
        gold = _ejemplo_noticia()
        resultado = EvaluacionEjemplo(texto=gold.texto, compuerta=gold.compuerta)

        # Act
        metricas = metricas_por_campo([gold], [resultado])

        # Assert
        tipo_evento = next(campo for campo in metricas.campos if campo.campo == "tipo_evento")
        assert tipo_evento.evaluados == 0


class TestGenerarInforme:
    """Pruebas de generar_informe."""

    def test_escribe_informe_con_metricas(self, tmp_path) -> None:
        """Genera el archivo Markdown con las secciones esperadas."""
        # Arrange
        resultado = EvaluacionEjemplo(texto="temblor", latencia_ms=50.0)
        metricas = metricas_por_campo([_ejemplo_noticia()], [resultado])
        ruta = tmp_path / "informe.md"

        # Act
        generar_informe(metricas, [resultado], ruta)

        # Assert
        contenido = ruta.read_text(encoding="utf-8")
        assert "## Metricas por campo" in contenido
        assert "## Latencia" in contenido
        assert "| Campo | Evaluados | Exactitud | F1 |" in contenido

    def test_incluye_ejemplos_con_error(self, tmp_path) -> None:
        """Lista la seccion de errores cuando hay rechazos."""
        # Arrange
        resultado = EvaluacionEjemplo(texto="temblor", error="salida invalida", latencia_ms=10.0)
        metricas = metricas_por_campo([_ejemplo_sismo()], [resultado])
        ruta = tmp_path / "informe.md"

        # Act
        generar_informe(metricas, [resultado], ruta)

        # Assert
        contenido = ruta.read_text(encoding="utf-8")
        assert "## Ejemplos con error" in contenido
        assert "'temblor': salida invalida" in contenido

    def test_omite_matrices_cuando_no_se_calculan(self, tmp_path) -> None:
        """Sin matrices no aparecen las secciones de confusion."""
        # Arrange
        resultado = EvaluacionEjemplo(texto="temblor", latencia_ms=10.0)
        metricas = metricas_por_campo([_ejemplo_sismo()], [resultado])
        ruta = tmp_path / "informe.md"

        # Act
        generar_informe(metricas, [resultado], ruta)

        # Assert
        contenido = ruta.read_text(encoding="utf-8")
        assert "## Matrices de confusion" not in contenido
        assert "## Matrices con mayor error" not in contenido


class TestGenerarInformeMatrices:
    """Pruebas de las secciones legibles de matrices en generar_informe."""

    def test_incluye_tabla_por_campo_con_diagonal_y_totales(self, tmp_path) -> None:
        """Rinde una tabla por campo con la diagonal resaltada y totales."""
        # Arrange
        resultado = EvaluacionEjemplo(texto="temblor", latencia_ms=20.0)
        metricas = metricas_por_campo([_ejemplo_sismo()], [resultado])
        matrices = {
            "es_reporte_accionable": {
                "true": {"true": 160, "false": 57},
                "false": {"false": 120, "true": 3},
            },
            "tipo_evento": {"sismo": {"sismo": 14}},
        }
        ruta = tmp_path / "informe.md"

        # Act
        generar_informe(
            metricas,
            [resultado],
            ruta,
            matrices_confusion=matrices,
        )

        # Assert
        contenido = ruta.read_text(encoding="utf-8")
        assert "## Matrices de confusion" in contenido
        assert "### es_reporte_accionable" in contenido
        assert "| Oro \\ Predicho | true | false | Total |" in contenido
        assert "| **true** | **160** | 57 |" in contenido
        assert "**Total**" in contenido

    def test_destaca_matrices_con_mayor_error(self, tmp_path) -> None:
        """Explica los pares mas confundidos de las matrices de mayor error."""
        # Arrange
        resultado = EvaluacionEjemplo(texto="temblor", latencia_ms=20.0)
        metricas = metricas_por_campo([_ejemplo_sismo()], [resultado])
        matrices = {
            "es_reporte_accionable": {
                "true": {"true": 160, "false": 57},
                "false": {"false": 120, "true": 3},
            },
            "tipo_evento": {"sismo": {"sismo": 14}},
        }
        ruta = tmp_path / "informe.md"

        # Act
        generar_informe(
            metricas,
            [resultado],
            ruta,
            matrices_confusion=matrices,
        )

        # Assert
        contenido = ruta.read_text(encoding="utf-8")
        assert "## Matrices con mayor error" in contenido
        assert "60 errores de 340 evaluados" in contenido
        assert "reporte accionable clasificado como no accionable" in contenido
        assert "no accionable clasificado como accionable" in contenido

    def test_deja_seccion_vacia_sin_errores(self, tmp_path) -> None:
        """Avisa cuando ninguna matriz tiene confusion fuera de la diagonal."""
        # Arrange
        resultado = EvaluacionEjemplo(texto="temblor", latencia_ms=20.0)
        metricas = metricas_por_campo([_ejemplo_sismo()], [resultado])
        matrices = {"tipo_evento": {"sismo": {"sismo": 14}}}
        ruta = tmp_path / "informe.md"

        # Act
        generar_informe(
            metricas,
            [resultado],
            ruta,
            matrices_confusion=matrices,
        )

        # Assert
        contenido = ruta.read_text(encoding="utf-8")
        assert "## Matrices con mayor error" in contenido
        assert "no tuvo errores de clasificacion" in contenido

    def test_agrupa_valores_de_alta_cardinalidad_en_otros(self, tmp_path) -> None:
        """Trunca los textos libres de ubicacion bajo la etiqueta otros."""
        # Arrange
        resultado = EvaluacionEjemplo(texto="temblor", latencia_ms=20.0)
        metricas = metricas_por_campo([_ejemplo_sismo()], [resultado])
        matrices = {
            "ubicacion_texto_literal": {
                **{f"calle {i}": {f"calle {i}": 2} for i in range(1, 17)},
                **{f"avenida {i}": {f"avenida {i}": 1} for i in range(1, 11)},
            }
        }
        ruta = tmp_path / "informe.md"

        # Act
        generar_informe(
            metricas,
            [resultado],
            ruta,
            matrices_confusion=matrices,
        )

        # Assert
        contenido = ruta.read_text(encoding="utf-8")
        assert "### ubicacion_texto_literal" in contenido
        assert "| **calle 16** |" in contenido
        assert "otros" in contenido
        assert "avenida 1" not in contenido

    def test_etiqueta_valores_vacios(self, tmp_path) -> None:
        """Representa los textos libres vacios de forma legible."""
        # Arrange
        resultado = EvaluacionEjemplo(texto="temblor", latencia_ms=20.0)
        metricas = metricas_por_campo([_ejemplo_sismo()], [resultado])
        matrices = {"ubicacion_texto_literal": {"": {"": 16}, "calle 5": {"calle 5": 3}}}
        ruta = tmp_path / "informe.md"

        # Act
        generar_informe(
            metricas,
            [resultado],
            ruta,
            matrices_confusion=matrices,
        )

        # Assert
        contenido = ruta.read_text(encoding="utf-8")
        assert "_vacio_" in contenido
        assert "**16**" in contenido


class TestMatrizConfusion:
    """Pruebas de matriz_confusion."""

    def test_cuenta_aciertos_por_valor(self) -> None:
        """Cruza cada valor con su par exacto cuando no hay diferencias."""
        # Arrange
        gold = _ejemplo_sismo()
        resultado = EvaluacionEjemplo(
            texto=gold.texto,
            compuerta=gold.compuerta,
            naturaleza=gold.naturaleza,
            ubicacion=gold.ubicacion,
        )

        # Act
        matriz = matriz_confusion([gold], [resultado], "tipo_evento")

        # Assert
        assert matriz == {"sismo": {"sismo": 1}}

    def test_registra_valores_distintos(self) -> None:
        """Coloca en la fila del gold la columna del valor predicho."""
        # Arrange
        gold = _ejemplo_incendio()
        resultado = EvaluacionEjemplo(
            texto=gold.texto,
            compuerta=gold.compuerta,
            naturaleza=Naturaleza.model_validate(
                {
                    "tipo_evento": "sismo",
                    "servicio_de_respuesta": ["B"],
                }
            ),
            ubicacion=gold.ubicacion,
        )

        # Act
        matriz = matriz_confusion([gold], [resultado], "tipo_evento")

        # Assert
        assert matriz == {"incendio_estructural": {"sismo": 1}}

    def test_expande_campos_multivaluados(self) -> None:
        """Cuenta una celda por cada valor del servicio esperado."""
        # Arrange
        gold = _ejemplo_incendio()
        resultado = EvaluacionEjemplo(
            texto=gold.texto,
            compuerta=gold.compuerta,
            naturaleza=Naturaleza.model_validate(
                {
                    "tipo_evento": "incendio_estructural",
                    "servicio_de_respuesta": ["B"],
                }
            ),
            ubicacion=gold.ubicacion,
        )

        # Act
        matriz = matriz_confusion([gold], [resultado], "servicio_de_respuesta")

        # Assert
        assert matriz == {"b": {"b": 1}, "g": {"b": 1}}

    def test_ignora_ejemplos_sin_campo(self) -> None:
        """Deja fuera los ejemplos cuyo gold no tiene el campo evaluado."""
        # Arrange
        gold = _ejemplo_noticia()
        resultado = EvaluacionEjemplo(texto=gold.texto, compuerta=gold.compuerta)

        # Act
        matriz = matriz_confusion([gold], [resultado], "tipo_evento")

        # Assert
        assert matriz == {}
