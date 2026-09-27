"""Pruebas del registro de corridas de evaluacion en MLflow."""

import json
from pathlib import Path

import mlflow

from inference.evaluacion import (
    EvaluacionEjemplo,
    EjemploGold,
    generar_informe,
    metricas_por_campo,
    matriz_confusion,
)
from inference.registro import EXPERIMENTO, registrar_corrida
from sirena_schema.schema import Compuerta, Naturaleza, Ubicacion


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
                "punto_referencia": None,
                "nivel_granularidad": "exacta",
                "lat": None,
                "lon": None,
            }
        ),
    )


def _resultado_identico(ejemplo: EjemploGold) -> EvaluacionEjemplo:
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


def _corpus_en_tmp(tmp_path: Path, version: str = "gold_v1") -> Path:
    """Crea un corpus JSONL dentro de un directorio versionado.

    Args:
        tmp_path: Directorio temporal de la prueba.
        version: Nombre del directorio que identifica la version del corpus.

    Returns:
        Ruta del archivo del corpus.

    """
    ruta = tmp_path / version / "eval.jsonl"
    ruta.parent.mkdir(exist_ok=True)
    ruta.write_text("{}\n", encoding="utf-8")
    return ruta


def _uri_sqlite(tmp_path: Path) -> str:
    """Construye una URI de almacenamiento SQLite dentro del directorio temporal.

    Args:
        tmp_path: Directorio temporal de la prueba.

    Returns:
        URI de tracking de MLflow sobre una base SQLite local.

    """
    return f"sqlite:///{tmp_path / 'mlruns.db'}"


def _registrar_en(
    uri: str | None,
    tmp_path: Path,
    *,
    matrices: bool = True,
    **kwargs,
) -> str | None:
    """Registra una corrida perfecta de un solo ejemplo.

    Args:
        uri: URI del servidor MLflow, o None para usar la variable de entorno.
        tmp_path: Directorio temporal donde se crea el informe y el corpus.
        matrices: Si se calculan las matrices de confusion para el artefacto.
        kwargs: Parametros adicionales de registrar_corrida (autor, rama, pr).

    Returns:
        Id del run registrado, o None si no hay URI configurada.

    """
    ejemplo = _ejemplo_sismo()
    resultado = _resultado_identico(ejemplo)
    metricas = metricas_por_campo([ejemplo], [resultado])
    ruta_informe = tmp_path / "informe.md"
    generar_informe(metricas, [resultado], ruta_informe)
    return registrar_corrida(
        metricas=metricas,
        ejemplos=[ejemplo],
        resultados=[resultado],
        ruta_informe=ruta_informe,
        corpus=_corpus_en_tmp(tmp_path),
        matrices_confusion=(
            matriz_confusion([ejemplo], [resultado], "tipo_evento") if matrices else None
        ),
        tracking_uri=uri,
        **kwargs,
    )


def _buscar_artefacto(directorio: Path, nombre: str) -> Path:
    """Ubica un artefacto dentro del directorio descargado.

    Args:
        directorio: Directorio con los artefactos descargados del run.
        nombre: Nombre del archivo del artefacto a localizar.

    Returns:
        Ruta del primer archivo que coincide con el nombre.

    """
    return next(directorio.rglob(nombre))


class TestRegistrarCorrida:
    """Pruebas de registrar_corrida."""

    def test_sin_uri_no_registra(self, monkeypatch) -> None:
        """Devuelve None y no registra cuando falta la URI de seguimiento."""
        # Arrange
        monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
        ejemplo = _ejemplo_sismo()
        resultado = _resultado_identico(ejemplo)
        metricas = metricas_por_campo([ejemplo], [resultado])

        # Act
        run_id = registrar_corrida(
            metricas=metricas,
            ejemplos=[ejemplo],
            resultados=[resultado],
            ruta_informe=Path("informe.md"),
            corpus=Path("eval.jsonl"),
        )

        # Assert
        assert run_id is None

    def test_registra_y_crea_experimento(self, tmp_path) -> None:
        """Guarda params, metricas y tags en el experimento esperado."""
        # Arrange
        uri = _uri_sqlite(tmp_path)

        # Act
        run_id = _registrar_en(uri, tmp_path, autor="Autor Prueba", rama="feature/prueba", pr="123")

        # Assert
        assert run_id is not None
        cliente = mlflow.tracking.MlflowClient(uri)
        assert cliente.get_experiment_by_name(EXPERIMENTO) is not None
        corrida = cliente.get_run(run_id)
        assert corrida.data.params["modelo"] == "openai/gpt-oss-20b"
        assert corrida.data.params["proveedor"] == "groq"
        assert corrida.data.params["temperatura"] == "0.0"
        assert corrida.data.params["intentos"] == "3"
        assert corrida.data.params["version_corpus"] == "gold_v1"
        assert corrida.data.params["umbral_compuerta"] == "no_aplica"
        assert corrida.data.params["prompt_compuerta_hash"]
        assert corrida.data.params["prompt_extraccion_hash"]
        assert corrida.data.metrics["total_ejemplos"] == 1.0
        assert corrida.data.metrics["exactitud_tipo_evento"] == 1.0
        assert corrida.data.metrics["f1_tipo_evento"] == 1.0
        assert corrida.data.metrics["latencia_media_ms"] == 100.0
        assert corrida.data.tags["licencia"] == "MIT"
        assert corrida.data.tags["equipo"] == "SIRENA"
        assert corrida.data.tags["ambiente"] == "dev"
        assert corrida.data.tags["autor"] == "Autor Prueba"
        assert corrida.data.tags["rama"] == "feature/prueba"
        assert corrida.data.tags["pr"] == "123"

    def test_lee_uri_desde_entorno(self, tmp_path, monkeypatch) -> None:
        """Usa MLFLOW_TRACKING_URI cuando no se pasa una URI explicita."""
        # Arrange
        uri = _uri_sqlite(tmp_path)
        monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)

        # Act
        run_id = _registrar_en(None, tmp_path)

        # Assert
        assert run_id is not None
        corrida = mlflow.tracking.MlflowClient(uri).get_run(run_id)
        assert corrida.info.run_id == run_id

    def test_registra_artefactos_y_matrices(self, tmp_path) -> None:
        """Sube el informe, las predicciones y las matrices del run."""
        # Arrange
        uri = _uri_sqlite(tmp_path)

        # Act
        run_id = _registrar_en(uri, tmp_path)

        # Assert
        directorio = Path(mlflow.artifacts.download_artifacts(run_id=run_id, tracking_uri=uri))
        for nombre in ("informe.md", "ejemplos_prediccion.json", "matrices_confusion.json"):
            assert _buscar_artefacto(directorio, nombre).exists()
        matrices = json.loads(
            _buscar_artefacto(directorio, "matrices_confusion.json").read_text(encoding="utf-8")
        )
        assert matrices == {"sismo": {"sismo": 1}}
        ejemplos = json.loads(
            _buscar_artefacto(directorio, "ejemplos_prediccion.json").read_text(encoding="utf-8")
        )
        assert ejemplos[0]["texto"] == "temblor en el centro, me estoy quedando sin oxigeno"

    def test_omite_matrices_sin_calcular(self, tmp_path) -> None:
        """No sube el artefacto de matrices cuando no se calcularon."""
        # Arrange
        uri = _uri_sqlite(tmp_path)

        # Act
        run_id = _registrar_en(uri, tmp_path, matrices=False)

        # Assert
        directorio = Path(mlflow.artifacts.download_artifacts(run_id=run_id, tracking_uri=uri))
        assert _buscar_artefacto(directorio, "informe.md").exists()
        assert not any(ruta.name == "matrices_confusion.json" for ruta in directorio.rglob("*"))
