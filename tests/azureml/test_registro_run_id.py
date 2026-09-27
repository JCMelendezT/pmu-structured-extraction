"""Pruebas del registro cuando la corrida ya la abrio el pipeline de Azure ML.

Dentro de un job de Azure ML, MLflow ya tiene una corrida abierta y la
variable MLFLOW_RUN_ID la apunta. Cambiar de experimento a mitad de camino
falla, asi que registrar_corrida tiene que respeta esa corrida en vez de abrir
una nueva.
"""

from pathlib import Path

import mlflow
import pytest

from inference.evaluacion import (
    EvaluacionEjemplo,
    EjemploGold,
    generar_informe,
    metricas_por_campo,
)
from inference.registro import EXPERIMENTO, registrar_corrida
from sirena_schema.schema import Compuerta, Naturaleza, Ubicacion


def _ejemplo() -> EjemploGold:
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
            {"tipo_evento": "sismo", "servicio_de_respuesta": ["A"]}
        ),
        ubicacion=Ubicacion.model_validate(
            {
                "ubicacion_texto_literal": "Calle 5",
                "barrio": "Centro",
                "comuna": "3",
                "punto_referencia": None,
                "nivel_granularidad": "exacta",
                "lat": None,
                "lon": None,
            }
        ),
    )


def _resultado(ejemplo: EjemploGold) -> EvaluacionEjemplo:
    """Construye el resultado que repite el gold del ejemplo.

    Args:
        ejemplo: Ejemplo gold que el resultado debe acertar.

    Returns:
        Resultado del servicio con la misma salida que el gold.

    """
    return EvaluacionEjemplo(
        texto=ejemplo.texto,
        compuerta=ejemplo.compuerta,
        naturaleza=ejemplo.naturaleza,
        ubicacion=ejemplo.ubicacion,
        latencia_ms=100.0,
    )


def _registrar(uri: str, tmp_path: Path) -> str | None:
    """Registra una corrida perfecta de un solo ejemplo.

    Args:
        uri: URI de tracking de MLflow sobre una base SQLite local.
        tmp_path: Directorio temporal donde se crean el informe y el corpus.

    Returns:
        Id del run registrado, o None si no hay URI configurada.

    """
    ejemplo = _ejemplo()
    resultado = _resultado(ejemplo)
    metricas = metricas_por_campo([ejemplo], [resultado])
    ruta_informe = tmp_path / "informe.md"
    generar_informe(metricas, [resultado], ruta_informe)
    corpus = tmp_path / "gold_v1" / "eval.jsonl"
    corpus.parent.mkdir(exist_ok=True)
    corpus.write_text("{}\n", encoding="utf-8")
    return registrar_corrida(
        metricas=metricas,
        ejemplos=[ejemplo],
        resultados=[resultado],
        ruta_informe=ruta_informe,
        corpus=corpus,
        tracking_uri=uri,
    )


def _corrida_padre(uri: str) -> str:
    """Crea la corrida que el pipeline padre ya tendria abierta.

    Args:
        uri: URI de tracking de MLflow sobre una base SQLite local.

    Returns:
        Id de la corrida creada.

    """
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(EXPERIMENTO)
    with mlflow.start_run() as run:
        mlflow.log_param("origen", "pipeline_padre")
    return run.info.run_id


def _experimento_id(uri: str) -> str:
    """Devuelve el id del experimento del harness.

    Args:
        uri: URI de tracking de MLflow sobre una base SQLite local.

    Returns:
        Id del experimento registrado.

    """
    return mlflow.tracking.MlflowClient(uri).get_experiment_by_name(EXPERIMENTO).experiment_id


class TestRegistrarCorridaConRunId:
    def test_no_llama_set_experiment(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        uri = f"sqlite:///{tmp_path / 'mlruns.db'}"
        monkeypatch.setenv("MLFLOW_RUN_ID", _corrida_padre(uri))
        llamadas: list[str] = []
        monkeypatch.setattr(mlflow, "set_experiment", lambda nombre: llamadas.append(nombre))

        # Act
        _registrar(uri, tmp_path)

        # Assert
        assert llamadas == []

    def test_no_crea_una_corrida_nueva(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        uri = f"sqlite:///{tmp_path / 'mlruns.db'}"
        monkeypatch.setenv("MLFLOW_RUN_ID", _corrida_padre(uri))
        cliente = mlflow.tracking.MlflowClient(uri)
        antes = len(cliente.search_runs([_experimento_id(uri)]))

        # Act
        _registrar(uri, tmp_path)

        # Assert
        assert len(cliente.search_runs([_experimento_id(uri)])) == antes

    def test_devuelve_el_id_de_la_corrida_del_padre(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        uri = f"sqlite:///{tmp_path / 'mlruns.db'}"
        id_padre = _corrida_padre(uri)
        monkeypatch.setenv("MLFLOW_RUN_ID", id_padre)

        # Act
        run_id = _registrar(uri, tmp_path)

        # Assert
        assert run_id == id_padre

    def test_escribe_las_metricas_en_la_corrida_del_padre(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        uri = f"sqlite:///{tmp_path / 'mlruns.db'}"
        id_padre = _corrida_padre(uri)
        monkeypatch.setenv("MLFLOW_RUN_ID", id_padre)
        cliente = mlflow.tracking.MlflowClient(uri)

        # Act
        _registrar(uri, tmp_path)

        # Assert
        corrida = cliente.get_run(id_padre)
        assert corrida.data.params["modelo"] == "openai/gpt-oss-20b"
        assert corrida.data.metrics["total_ejemplos"] == 1.0
        assert corrida.data.metrics["exactitud_tipo_evento"] == 1.0


class TestRegistrarCorridaSinRunId:
    def test_sigue_llamando_set_experiment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        uri = f"sqlite:///{tmp_path / 'mlruns.db'}"
        monkeypatch.delenv("MLFLOW_RUN_ID", raising=False)
        llamadas: list[str] = []
        original = mlflow.set_experiment
        monkeypatch.setattr(
            mlflow, "set_experiment", lambda nombre: llamadas.append(nombre) or original(nombre)
        )

        # Act
        run_id = _registrar(uri, tmp_path)

        # Assert
        assert llamadas == [EXPERIMENTO]
        assert run_id is not None

    def test_crea_una_corrida_nueva(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        uri = f"sqlite:///{tmp_path / 'mlruns.db'}"
        monkeypatch.delenv("MLFLOW_RUN_ID", raising=False)
        cliente = mlflow.tracking.MlflowClient(uri)

        # Act
        run_id = _registrar(uri, tmp_path)

        # Assert
        assert run_id is not None
        assert cliente.get_run(run_id).data.metrics["total_ejemplos"] == 1.0
