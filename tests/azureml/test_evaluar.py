"""Pruebas del envoltorio de evaluacion para los jobs de Azure ML.

Lo que hay que vigilar aqui no son las metricas, que las calcula el harness
probado, sino tres cosas propias del job: que la clave de Groq se resuelva
sin filtrarse al log, que el metricas.json que viaja al job de comparacion
diga que modelo midio, y que autor y rama lleguen al registro.
"""

import json
import os
from pathlib import Path

import pytest

import evaluar
from evaluar import main

LINEA_SISMO = {
    "texto": "se desprendio un muro de contencion y amenaza con caerse",
    "compuerta": {
        "es_reporte_accionable": True,
        "temporalidad": "ocurriendo_ahora",
        "intencion": "solicita_ayuda",
    },
    "naturaleza": {"tipo_evento": "movimiento_en_masa", "servicio_de_respuesta": ["G"]},
    "ubicacion": {
        "ubicacion_texto_literal": "sector de Colinas del Sur",
        "barrio": "Colinas del Sur",
        "comuna": "18",
        "punto_referencia": None,
        "nivel_granularidad": "barrio",
        "lat": None,
        "lon": None,
    },
}
CLAVE_FALSA = "gsk-clave-de-prueba"


class _EvaluadorStub:
    """Sustituye al evaluador real para no llamar a Groq en las pruebas."""

    def __init__(self, servicio: object) -> None:
        self.servicio = servicio

    def evaluar(self, ejemplos):
        """Devuelve el gold repetido, que es una prediccion perfecta.

        Args:
            ejemplos: Ejemplos gold que el job pidio evaluar.

        Returns:
            Una prediccion correcta por cada ejemplo.

        """
        from inference.evaluacion import EvaluacionEjemplo

        return [
            EvaluacionEjemplo(
                texto=ejemplo.texto,
                compuerta=ejemplo.compuerta,
                naturaleza=ejemplo.naturaleza,
                ubicacion=ejemplo.ubicacion,
                latencia_ms=100.0,
            )
            for ejemplo in ejemplos
        ]


def _corpus(tmp_path: Path, cantidad: int = 2) -> Path:
    """Escribe un corpus JSONL minimo y valido.

    Args:
        tmp_path: Directorio temporal de la prueba.
        cantidad: Cuantas lineas repetir en el corpus.

    Returns:
        Ruta del corpus escrito.

    """
    ruta = tmp_path / "gold_v1" / "eval.jsonl"
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text(
        "\n".join(json.dumps(LINEA_SISMO) for _ in range(cantidad)) + "\n", encoding="utf-8"
    )
    return ruta


def _entorno_limpio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deja el entorno sin ninguna fuente de clave.

    Args:
        monkeypatch: Fixture de pytest para parchear el entorno.

    """
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("KEY_VAULT_URL", raising=False)


class TestResolverClave:
    def test_usa_la_clave_del_entorno_sin_tocar_el_key_vault(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _entorno_limpio(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", CLAVE_FALSA)
        monkeypatch.setenv("KEY_VAULT_URL", "https://vault.example/")
        llamado: list[str] = []
        monkeypatch.setattr(evaluar, "_leer_secreto", lambda url: llamado.append(url) or "otra")

        # Act
        evaluar._resolver_clave()

        # Assert
        assert llamado == []
        assert os.environ["GROQ_API_KEY"] == CLAVE_FALSA

    def test_lee_el_secreto_cuando_no_hay_clave_en_el_entorno(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _entorno_limpio(monkeypatch)
        monkeypatch.setenv("KEY_VAULT_URL", "https://vault.example/")
        pedidos: list[str] = []
        monkeypatch.setattr(
            evaluar,
            "_leer_secreto",
            lambda url: pedidos.append(url) or "gks-desde-el-vault",
        )

        # Act
        evaluar._resolver_clave()

        # Assert
        assert pedidos == ["https://vault.example/"]
        assert os.environ["GROQ_API_KEY"] == "gks-desde-el-vault"

    def test_falla_con_un_mensaje_claro_sin_ninguna_fuente(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _entorno_limpio(monkeypatch)

        # Act / Assert
        with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
            evaluar._resolver_clave()

    def test_no_imprime_la_clave(self, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        # Arrange
        _entorno_limpio(monkeypatch)
        monkeypatch.setenv("KEY_VAULT_URL", "https://vault.example/")
        monkeypatch.setattr(evaluar, "_leer_secreto", lambda url: CLAVE_FALSA)

        # Act
        evaluar._resolver_clave()

        # Assert
        assert CLAVE_FALSA not in capsys.readouterr().out


class TestMainEscribeLaSalida:
    def test_escribe_metricas_json_con_el_modelo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _entorno_limpio(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", CLAVE_FALSA)
        monkeypatch.setenv("INFERENCE_MODELO", "openai/gpt-oss-120b")
        monkeypatch.setattr(evaluar, "EvaluadorPrompts", _EvaluadorStub)
        corpus = _corpus(tmp_path)
        salida = tmp_path / "salida"

        # Act
        codigo = main(["--corpus", str(corpus), "--salida", str(salida)])

        # Assert
        metricas = json.loads((salida / "metricas.json").read_text(encoding="utf-8"))
        assert codigo == 0
        assert metricas["modelo"] == "openai/gpt-oss-120b"
        assert metricas["total_ejemplos"] == 2
        assert {c["campo"] for c in metricas["campos"]} >= {"tipo_evento", "es_reporte_accionable"}

    def test_escribe_el_informe(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        _entorno_limpio(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", CLAVE_FALSA)
        monkeypatch.setattr(evaluar, "EvaluadorPrompts", _EvaluadorStub)
        corpus = _corpus(tmp_path)
        salida = tmp_path / "salida"

        # Act
        main(["--corpus", str(corpus), "--salida", str(salida)])

        # Assert
        assert (salida / "informe.md").exists()

    def test_el_limite_recorta_el_corpus(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _entorno_limpio(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", CLAVE_FALSA)
        monkeypatch.setattr(evaluar, "EvaluadorPrompts", _EvaluadorStub)
        corpus = _corpus(tmp_path, cantidad=5)
        salida = tmp_path / "salida"

        # Act
        main(["--corpus", str(corpus), "--salida", str(salida), "--limite", "1"])

        # Assert
        metricas = json.loads((salida / "metricas.json").read_text(encoding="utf-8"))
        assert metricas["total_ejemplos"] == 1


class TestMainRegistraLaCorrida:
    def test_pasa_autor_y_rama_al_registro(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _entorno_limpio(monkeypatch)
        monkeypatch.setenv("GROQ_API_KEY", CLAVE_FALSA)
        monkeypatch.setattr(evaluar, "EvaluadorPrompts", _EvaluadorStub)
        recibido: dict = {}
        monkeypatch.setattr(
            evaluar, "registrar_corrida", lambda **kwargs: recibido.update(kwargs) or "run-1"
        )
        corpus = _corpus(tmp_path)

        # Act
        main(
            [
                "--corpus",
                str(corpus),
                "--salida",
                str(tmp_path / "salida"),
                "--autor",
                "Juan",
                "--rama",
                "feature/azureml-pipeline",
            ]
        )

        # Assert
        assert recibido["autor"] == "Juan"
        assert recibido["rama"] == "feature/azureml-pipeline"

    def test_falla_con_codigo_1_si_no_hay_clave(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        _entorno_limpio(monkeypatch)
        corpus = _corpus(tmp_path)
        salida = tmp_path / "salida"

        # Act
        codigo = main(["--corpus", str(corpus), "--salida", str(salida)])

        # Assert
        assert codigo == 1
        assert not (salida / "metricas.json").exists()
