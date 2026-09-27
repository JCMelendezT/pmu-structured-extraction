"""Pruebas de la regla de seleccion del modelo ganador.

La regla es una decision del equipo, escrita en el plan antes de ver los
resultados: gana el mayor promedio de f1 de tipo_evento y
es_reporte_accionable, y si la diferencia es menor a 0,02 gana el modelo
barato porque cuesta menos.
"""

import json
from pathlib import Path

import pytest

from comparar import MODELO_BARATO, UMBRAL, elegir, main

CAMPO_TIPO_EVENTO = "tipo_evento"
CAMPO_ESPERA = "es_reporte_accionable"
MODELO_CARO = "openai/gpt-oss-120b"


def _metricas(modelo: str, f1_tipo_evento: float, f1_espera: float, p95: float = 900.0) -> dict:
    """Construye un metricas.json con la forma que escribe evaluar.py.

    Args:
        modelo: Nombre del modelo evaluado.
        f1_tipo_evento: F1 del campo tipo_evento.
        f1_espera: F1 del campo es_reporte_accionable.
        p95: Latencia percentil 95 de la corrida.

    Returns:
        Diccionario con las metricas serializadas de la corrida.

    """
    return {
        "modelo": modelo,
        "campos": [
            {
                "campo": CAMPO_TIPO_EVENTO,
                "evaluados": 340,
                "exactitud": f1_tipo_evento,
                "f1": f1_tipo_evento,
            },
            {
                "campo": CAMPO_ESPERA,
                "evaluados": 400,
                "exactitud": f1_espera,
                "f1": f1_espera,
            },
        ],
        "latencia_media_ms": 400.0,
        "latencia_p95_ms": p95,
        "errores_validacion": 0,
        "total_ejemplos": 340,
    }


def _escribir(directorio: Path, metricas: dict) -> Path:
    """Vierte unas metricas en la carpeta de salida de un job.

    Args:
        directorio: Carpeta que representa la salida del job evaluado.
        metricas: Contenido del metricas.json a escribir.

    Returns:
        Ruta del directorio usado.

    """
    directorio.mkdir(parents=True, exist_ok=True)
    (directorio / "metricas.json").write_text(
        json.dumps(metricas, ensure_ascii=False), encoding="utf-8"
    )
    return directorio


class TestElegirConDiferenciaClara:
    def test_gana_el_mayor_puntaje(self) -> None:
        # Arrange
        a = _metricas(MODELO_BARATO, 0.90, 0.92)
        b = _metricas(MODELO_CARO, 0.95, 0.96)

        # Act
        decision = elegir(a, b)

        # Assert
        assert decision["ganador"] == MODELO_CARO

    def test_gana_el_mayor_puntaje_todavia_gana_si_es_el_barato(self) -> None:
        # Arrange
        a = _metricas(MODELO_BARATO, 0.95, 0.96)
        b = _metricas(MODELO_CARO, 0.90, 0.92)

        # Act
        decision = elegir(a, b)

        # Assert
        assert decision["ganador"] == MODELO_BARATO

    def test_usa_el_promedio_y_no_un_solo_campo(self) -> None:
        # Arrange: 20b gana en tipo_evento y 120b en es_reporte_accionable.
        a = _metricas(MODELO_BARATO, 0.99, 0.50)
        b = _metricas(MODELO_CARO, 0.50, 0.99)

        # Act
        decision = elegir(a, b)

        # Assert: los dos promedios dan 0.745, asi que es empate y gana el barato.
        assert decision["ganador"] == MODELO_BARATO


class TestElegirConEmpate:
    def test_gana_el_barato_si_la_diferencia_es_menor_al_umbral(self) -> None:
        # Arrange
        barato = _metricas(MODELO_BARATO, 0.90, 0.90)
        caro = _metricas(MODELO_CARO, 0.90 + UMBRAL - 0.0001, 0.90 + UMBRAL - 0.0001)

        # Act
        decision = elegir(barato, caro)

        # Assert
        assert decision["ganador"] == MODELO_BARATO

    def test_gana_el_mayor_si_la_diferencia_iguala_el_umbral(self) -> None:
        # Arrange
        barato = _metricas(MODELO_BARATO, 0.90, 0.90)
        caro = _metricas(MODELO_CARO, 0.90 + UMBRAL, 0.90 + UMBRAL)

        # Act
        decision = elegir(barato, caro)

        # Assert: el umbral es estricto, a exactamente 0,02 ya no es empate.
        assert decision["ganador"] == MODELO_CARO

    def test_la_razon_invoca_el_costo(self) -> None:
        # Arrange
        barato = _metricas(MODELO_BARATO, 0.90, 0.90)
        caro = _metricas(MODELO_CARO, 0.905, 0.90)

        # Act
        decision = elegir(barato, caro)

        # Assert
        assert "costo" in decision["razon"].lower()


class TestElegirConDatosInvalidos:
    def test_falla_si_falta_un_campo_decisivo(self) -> None:
        # Arrange
        a = _metricas(MODELO_BARATO, 0.90, 0.90)
        b = _metricas(MODELO_CARO, 0.95, 0.96)
        b["campos"] = [c for c in b["campos"] if c["campo"] != CAMPO_ESPERA]

        # Act / Assert
        with pytest.raises(ValueError, match=CAMPO_ESPERA):
            elegir(a, b)

    def test_falla_si_ningun_candidato_es_el_barato_y_hay_empate(self) -> None:
        # Arrange
        a = _metricas("modelo-x", 0.90, 0.90)
        b = _metricas("modelo-y", 0.90, 0.90)

        # Act / Assert
        with pytest.raises(ValueError, match=MODELO_BARATO):
            elegir(a, b)


class TestCompararDesdeArchivos:
    def test_escribe_la_decision_en_la_salida(self, tmp_path: Path) -> None:
        # Arrange
        a = _escribir(tmp_path / "a", _metricas(MODELO_BARATO, 0.80, 0.82))
        b = _escribir(tmp_path / "b", _metricas(MODELO_CARO, 0.95, 0.96))
        salida = tmp_path / "decision"

        # Act
        codigo = main(
            [
                "--resultados-a",
                str(a),
                "--resultados-b",
                str(b),
                "--salida",
                str(salida),
            ]
        )

        # Assert
        decision = json.loads((salida / "decision.json").read_text(encoding="utf-8"))
        assert codigo == 0
        assert decision["ganador"] == MODELO_CARO
        assert decision["f1_tipo_evento"] == pytest.approx(0.95)
        assert decision["latencia_p95_ms"] == 900.0
        assert decision["razon"]

    def test_falla_con_codigo_1_si_una_carpeta_no_tiene_metricas(self, tmp_path: Path) -> None:
        # Arrange
        a = _escribir(tmp_path / "a", _metricas(MODELO_BARATO, 0.80, 0.82))
        (tmp_path / "b").mkdir()
        salida = tmp_path / "decision"

        # Act
        codigo = main(
            [
                "--resultados-a",
                str(a),
                "--resultados-b",
                str(tmp_path / "b"),
                "--salida",
                str(salida),
            ]
        )

        # Assert
        assert codigo == 1
        assert not (salida / "decision.json").exists()
