"""Pruebas del registro de la configuracion ganadora en Azure ML.

El SDK de Azure se importa adentro de construir_modelo, no al tope del
modulo: la imagen del Environment trae azure-ai-ml, pero el entorno de
desarrollo no lo necesita y estas pruebas no deben requerirlo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import registrar
from inference.registro import _hash_prompt

DECISION: dict[str, Any] = {
    "ganador": "openai/gpt-oss-20b",
    "razon": "El F1 promedio de openai/gpt-oss-20b es mayor por 0.0310, no hay empate.",
    "f1_tipo_evento": 0.8125,
    "latencia_p95_ms": 1420.0,
}


def _resultados(tmp_path: Path, modelo: str) -> Path:
    """Crea una carpeta de resultados con metricas.json e informe.md.

    Args:
        tmp_path: Directorio temporal de la prueba.
        modelo: Nombre del modelo que se dice haber medido.

    Returns:
        Ruta de la carpeta de resultados creada.

    """
    carpeta = tmp_path / modelo.replace("/", "_")
    carpeta.mkdir()
    (carpeta / "metricas.json").write_text(
        json.dumps({"modelo": modelo, "latencia_p95_ms": 1000.0}),
        encoding="utf-8",
    )
    (carpeta / "informe.md").write_text(f"# Informe de {modelo}\n", encoding="utf-8")
    return carpeta


def _decision(tmp_path: Path) -> Path:
    """Escribe decision.json y devuelve su ruta.

    Args:
        tmp_path: Directorio temporal de la prueba.

    Returns:
        Ruta del archivo decision.json creado.

    """
    ruta = tmp_path / "decision.json"
    ruta.write_text(json.dumps(DECISION), encoding="utf-8")
    return ruta


def _ontologia(tmp_path: Path) -> Path:
    """Crea un config/ontologia.yaml de prueba y devuelve su ruta.

    Args:
        tmp_path: Directorio temporal de la prueba.

    Returns:
        Ruta del archivo de ontologia creado.

    """
    ruta = tmp_path / "config" / "ontologia.yaml"
    ruta.parent.mkdir()
    ruta.write_text("tipo_evento: {} es_reporte_accionable: {}\n", encoding="utf-8")
    return ruta


class _ModelosRegistrados:
    """Doble de la coleccion models del MLClient."""

    def __init__(self) -> None:
        self.creados: list[Any] = []

    def create_or_update(self, modelo: Any) -> None:
        """Guarda el modelo recibido.

        Args:
            modelo: Modelo que la production intento registrar.

        """
        self.creados.append(modelo)


class _Cliente:
    """Doble del MLClient con solo la coleccion models."""

    def __init__(self) -> None:
        self.models = _ModelosRegistrados()


class TestEnsamblarPaquete:
    """El paquete del modelo se arma con los artefactos que exige el plan."""

    def test_deja_la_ontologia_la_decision_el_informe_y_los_hashes(self, tmp_path: Path) -> None:
        # Arrange
        resultados_a = _resultados(tmp_path, "openai/gpt-oss-20b")
        resultados_b = _resultados(tmp_path, "openai/gpt-oss-120b")
        salida = tmp_path / "salida"

        # Act
        paquete = registrar.ensamblar_paquete(
            decision=_decision(tmp_path),
            resultados_a=resultados_a,
            resultados_b=resultados_b,
            salida=salida,
            ontologia=_ontologia(tmp_path),
        )

        # Assert
        assert (paquete / "config" / "ontologia.yaml").read_text(encoding="utf-8") == (
            "tipo_evento: {} es_reporte_accionable: {}\n"
        )
        assert json.loads((paquete / "decision.json").read_text(encoding="utf-8")) == DECISION
        assert (paquete / "informe.md").read_text(
            encoding="utf-8"
        ) == "# Informe de openai/gpt-oss-20b\n"
        assert (
            json.loads((paquete / "prompts.json").read_text(encoding="utf-8"))
            == registrar.hashes_prompts()
        )

    def test_falla_si_ningun_resultado_dice_ser_el_ganador(self, tmp_path: Path) -> None:
        # Arrange
        resultados_a = _resultados(tmp_path, "openai/gpt-oss-20b")
        resultados_b = _resultados(tmp_path, "openai/gpt-oss-120b")
        decision = tmp_path / "decision.json"
        decision.write_text(json.dumps({**DECISION, "ganador": "otro/modelo"}), encoding="utf-8")

        # Act y Assert
        with pytest.raises(registrar.SinInformeGanador, match="otro/modelo"):
            registrar.ensamblar_paquete(
                decision=decision,
                resultados_a=resultados_a,
                resultados_b=resultados_b,
                salida=tmp_path / "salida",
                ontologia=_ontologia(tmp_path),
            )

    def test_falla_si_el_ganador_no_tiene_informe(self, tmp_path: Path) -> None:
        # Arrange
        resultados_a = _resultados(tmp_path, "openai/gpt-oss-20b")
        resultados_b = _resultados(tmp_path, "openai/gpt-oss-120b")
        (resultados_a / "informe.md").unlink()

        # Act y Assert
        with pytest.raises(registrar.SinInformeGanador):
            registrar.ensamblar_paquete(
                decision=_decision(tmp_path),
                resultados_a=resultados_a,
                resultados_b=resultados_b,
                salida=tmp_path / "salida",
                ontologia=_ontologia(tmp_path),
            )


class TestHashesPrompts:
    """Los hashes de los prompts deben servirlos para rastrear la corrida."""

    def test_coinciden_con_los_que_registra_mlflow(self) -> None:
        # Arrange
        from inference.prompts import VERSION_PROMPTS, sistema_compuerta, sistema_extraccion

        # Act
        hashes = registrar.hashes_prompts()

        # Assert
        assert hashes == {
            "version_prompts": VERSION_PROMPTS,
            "compuerta": _hash_prompt(sistema_compuerta()),
            "extraccion": _hash_prompt(sistema_extraccion()),
        }


class TestDescripcion:
    """La descripcion del modelo lleva lo que el plan exige."""

    def test_exige_los_cinco_tags_del_plan(self, tmp_path: Path) -> None:
        # Act
        descripcion = registrar.descripcion(
            ruta=tmp_path / "paquete",
            decision=DECISION,
            job_id="run-123",
        )

        # Assert
        assert descripcion["name"] == "sirena-extractor"
        assert descripcion["type"] == "custom_model"
        assert descripcion["path"] == str(tmp_path / "paquete")
        assert descripcion["tags"] == {
            "modelo": "openai/gpt-oss-20b",
            "f1_tipo_evento": "0.8125",
            "latencia_p95_ms": "1420.0",
            "prompt_hash": descripcion["tags"]["prompt_hash"],
            "job_id": "run-123",
        }
        assert "compuerta=" in descripcion["tags"]["prompt_hash"]
        assert "extraccion=" in descripcion["tags"]["prompt_hash"]

    def test_el_nombre_del_ganador_aparece_en_la_descripcion(self) -> None:
        # Act
        descripcion = registrar.descripcion(
            ruta=Path("paquete"),
            decision=DECISION,
            job_id="run-123",
        )

        # Assert
        assert "openai/gpt-oss-20b" in descripcion["description"]


class TestRegistrar:
    """El registro escribe el modelo con la descripcion calculada."""

    def test_crea_o_actualiza_con_la_descripcion(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Arrange
        cliente = _Cliente()
        descripcion = {"name": "sirena-extractor", "path": str(tmp_path), "tags": {"modelo": "m"}}
        construida: list[dict[str, str]] = []
        monkeypatch.setattr(registrar, "construir_modelo", lambda d: construida.append(d) or d)

        # Act
        registrar.registrar(cliente, descripcion)

        # Assert
        assert construida == [descripcion]
        assert cliente.models.creados == [descripcion]
