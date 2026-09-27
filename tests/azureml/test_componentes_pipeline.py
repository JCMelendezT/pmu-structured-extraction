"""Pruebas de coherencia entre los componentes y el pipeline de sirena-eval.

Azure ML valida los nombres en el momento de crear el job, no antes. Si el
pipeline le pasa a un componente un input que ese componente no declara, o
le pide un output que el componente no produce, el error aparece en Azure,
con el job a medio crear y un mensaje que no senala el YAML. Estas pruebas
mueven esa falla para adentro de la suite, que es donde se puede leer.

Lo que se comprueba:

- que los cuatro componentes existan y esten bien formados;
- que cada `component:` del pipeline apunte a un archivo real;
- que cada input que el pipeline le pasa a un job exista, con el mismo
  nombre y el mismo tipo, en el componente que lo consume;
- que cada `${{parent.jobs.X.outputs.Y}}` apunte a un output que X produce;
- que los defaults y el environment coincidan con los del plan.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

RAIZ_AZUREML = Path(__file__).resolve().parents[2] / "azureml"
PIPELINE = RAIZ_AZUREML / "pipeline.yml"
DIRECTORIO_COMPONENTES = RAIZ_AZUREML / "components"

COMPONENTES = {
    "validar": "sirena_validar_corpus.yml",
    "evaluar": "sirena_evaluar_modelo.yml",
    "comparar": "sirena_comparar_modelos.yml",
    "registrar": "sirena_registrar_configuracion.yml",
}

# Los cinco pasos del grafo, en orden.
JOBS = ["validar", "evaluar_20b", "evaluar_120b", "comparar", "registrar"]

# El pipeline nombra sus cables segun el rol que cumplen en el grafo; los
# componentes los nombran segun su funcion. La traduccion se declara de forma
# explicita para que un cable nuevo no pase por DEFAULT.
RENOMBRES_POR_JOB = {
    "validar": {"gold"},
    "evaluar_20b": {"corpus"},
    "evaluar_120b": {"corpus"},
    "comparar": {"resultados_a", "resultados_b"},
    "registrar": {
        "decision",
        "resultados_a",
        "resultados_b",
        "subscription_id",
        "resource_group",
        "workspace",
    },
}


def _cargar(ruta: Path) -> dict[str, Any]:
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pipeline() -> dict[str, Any]:
    return _cargar(PIPELINE)


def _componente_de(pipeline: dict[str, Any], job: str) -> dict[str, Any]:
    """Devuelve el YAML del componente que consume un job del pipeline."""
    declaracion = pipeline["jobs"][job]["component"]
    return _cargar((RAIZ_AZUREML / declaracion).resolve())


def _tipo_del_cable(pipeline: dict[str, Any], valor: Any) -> str | None:
    """Resuelve el tipo que Azure ML vera para un input del pipeline, o None si es literal.

    Un valor puede ser un literal, un `{type, default}` o una referencia a un
    input del pipeline o a la salida de otro job. En los dos ultimos casos el
    tipo no es el texto de la referencia sino el de lo que se esta citando, y
    por eso hay que mirar alli antes de comparar.
    """
    if isinstance(valor, dict):
        return valor.get("type")
    desde_entrada = re.fullmatch(r"\$\{\{parent\.inputs\.([a-z0-9_]+)\}\}", str(valor))
    if desde_entrada is not None:
        return pipeline["inputs"][desde_entrada.group(1)].get("type")
    referencia = re.fullmatch(
        r"\$\{\{parent\.jobs\.([a-z0-9_]+)\.outputs\.([a-z0-9_]+)\}\}", str(valor)
    )
    if referencia is None:
        return None
    origen, salida = referencia.groups()
    return _componente_de(pipeline, origen)["outputs"].get(salida, {}).get("type")


class TestComponentes:
    """Cada componente existe y declara lo minimo que Azure ML exige."""

    @pytest.mark.parametrize("nombre", sorted(COMPONENTES.values()))
    def test_el_componente_existe(self, nombre: str) -> None:
        # Arrange
        ruta = DIRECTORIO_COMPONENTES / nombre
        # Act / Assert
        assert ruta.is_file(), f"Falta el componente {ruta}"

    @pytest.mark.parametrize("nombre", sorted(COMPONENTES.values()))
    def test_el_componente_es_command_valido(self, nombre: str) -> None:
        # Arrange
        ruta = DIRECTORIO_COMPONENTES / nombre
        # Act
        componente = _cargar(ruta)
        # Assert
        assert componente["type"] == "command"
        assert componente["version"] >= 1
        assert componente["command"].strip(), "el comando no puede estar vacio"
        assert componente["$schema"].endswith("commandComponent.schema.json")

    @pytest.mark.parametrize("nombre", sorted(COMPONENTES.values()))
    def test_el_componente_usa_el_environment_sirena(self, nombre: str) -> None:
        # Arrange
        ruta = DIRECTORIO_COMPONENTES / nombre
        # Act
        componente = _cargar(ruta)
        # Assert
        assert componente["environment"] == "azureml:sirena-eval@latest"

    @pytest.mark.parametrize("nombre", sorted(COMPONENTES.values()))
    def test_el_componente_sube_el_repo_como_codigo(self, nombre: str) -> None:
        """`code` es relativo al archivo, asi que ../.. desde components/ es la raiz."""
        # Arrange
        ruta = DIRECTORIO_COMPONENTES / nombre
        # Act
        componente = _cargar(ruta)
        # Assert
        assert componente["code"] == "../.."
        assert (ruta.parent / componente["code"] / "azureml" / "src").is_dir()

    def test_el_nombre_interno_no_repita_el_sirena_del_archivo(self) -> None:
        """El prefijo sirena_ va una vez: en el archivo o en name, no en los dos."""
        # Arrange
        nombres = {
            archivo: _cargar(DIRECTORIO_COMPONENTES / archivo)["name"]
            for archivo in COMPONENTES.values()
        }
        # Act / Assert
        for archivo, nombre in nombres.items():
            assert nombre == archivo.removesuffix(".yml"), (
                f"{archivo} declara name: {nombre}, no coincide con el archivo"
            )

    def test_la_clave_de_groq_no_aparece_en_ningun_comando(self) -> None:
        """La clave viaja por el Key Vault, no por el comando del job.

        Un `export GROQ_API_KEY=$(...)` deja la clave en el log del job, que se
        conserva y ve cualquiera con acceso al workspace.
        """
        # Arrange
        comandos = {
            archivo: _cargar(DIRECTORIO_COMPONENTES / archivo)["command"]
            for archivo in COMPONENTES.values()
        }
        # Act / Assert
        for archivo, comando in comandos.items():
            assert "GROQ_API_KEY" not in comando, f"{archivo} menciona GROQ_API_KEY en el comando"

    def test_el_componente_de_evaluar_usa_la_credencial_gestionada(self) -> None:
        """AZURE_TOKEN_CREDENTIALS fija la credencial en vez de dejarla al azar."""
        # Arrange
        ruta = DIRECTORIO_COMPONENTES / COMPONENTES["evaluar"]
        # Act
        componente = _cargar(ruta)
        # Assert
        assert componente["environment_variables"]["AZURE_TOKEN_CREDENTIALS"] == (
            "ManagedIdentityCredential"
        )
        assert componente["environment_variables"]["KEY_VAULT_URL"].startswith("${{inputs.")

    def test_el_componente_de_evaluar_expone_el_modelo_ganador(self) -> None:
        """Sin este input, registrar no podria aplicar el desempate por costo."""
        # Arrange
        ruta = DIRECTORIO_COMPONENTES / COMPONENTES["evaluar"]
        # Act
        componente = _cargar(ruta)
        # Assert
        assert componente["inputs"]["modelo"]["default"] == "openai/gpt-oss-20b"

    def test_el_registrador_usa_una_credencial_gestionada(self) -> None:
        """Registrar modelo en Azure ML tambien necesita identidad."""
        # Arrange
        ruta = DIRECTORIO_COMPONENTES / COMPONENTES["registrar"]
        # Act
        componente = _cargar(ruta)
        # Assert
        assert componente["environment_variables"]["AZURE_TOKEN_CREDENTIALS"] == (
            "ManagedIdentityCredential"
        )

    def test_el_componente_registrador_no_declara_identity(self) -> None:
        """El esquema del command component no tiene clave identity.

        Ponerla ahi pasa la revision del autor y falla al crear el job. La
        identidad se declara en el job del pipeline.

        """
        # Arrange
        ruta = DIRECTORIO_COMPONENTES / COMPONENTES["registrar"]
        # Act
        componente = _cargar(ruta)
        # Assert
        assert "identity" not in componente


class TestPipeline:
    """El pipeline es coherente con los componentes que invoca."""

    def test_el_pipeline_declara_su_experiment_y_compute(self, pipeline: dict) -> None:
        # Arrange
        # Act
        esperado = {
            "experiment_name": "sirena-evaluacion",
            "display_name": "sirena-eval",
        }
        # Assert
        for clave, valor in esperado.items():
            assert pipeline[clave] == valor
        assert pipeline["settings"]["default_compute"] == "azureml:cpu-sirena"

    def test_los_cinco_pasos_del_plan_estan(self, pipeline: dict[str, Any]) -> None:
        # Arrange
        esperados = set(JOBS)
        # Act
        jobs = set(pipeline["jobs"])
        # Assert
        assert jobs == esperados, f"Faltan o sobran pasos: {esperados.symmetric_difference(jobs)}"

    def test_ningun_identificador_de_azure_lleva_default(self, pipeline: dict[str, Any]) -> None:
        """El repositorio es publico: un default filtraria el workspace.

        El MLClient no deduce estos tres valores dentro de un job, asi que se
        pasan al crear el job. Si alguien les pone default para "ahorrar" el
        comando, el identificador queda en un archivo versionado.
        """
        # Arrange
        identificadores = {"subscription_id", "resource_group", "workspace"}
        # Act
        con_default = {
            nombre
            for nombre, definicion in pipeline["inputs"].items()
            if nombre in identificadores and "default" in definicion
        }
        # Assert
        assert not con_default, f"Identificadores de Azure con default: {con_default}"

    @pytest.mark.parametrize("job", JOBS)
    def test_cada_job_apunta_a_un_componente_existente(
        self, pipeline: dict[str, Any], job: str
    ) -> None:
        # Arrange
        declaracion = pipeline["jobs"][job]["component"]
        # Act
        ruta = (RAIZ_AZUREML / declaracion).resolve()
        # Assert
        assert ruta.is_file(), f"{job} apunta a {declaracion}, que no existe"

    def test_las_dos_evaluaciones_usan_el_mismo_componente(self, pipeline: dict) -> None:
        """Es lo que hace comparables los dos puntajes: mismo codigo, distinto modelo."""
        # Arrange
        jobs = pipeline["jobs"]
        # Act / Assert
        assert jobs["evaluar_20b"]["component"] == jobs["evaluar_120b"]["component"]

    def test_el_job_registrador_usa_la_identidad_gestionada(self, pipeline: dict[str, Any]) -> None:
        """Registrar es escribir en Azure: AMLToken no alcanza.

        Solo el job registrar la necesita. Ponerla en todos seria pedir un
        permiso que los demas jobs no usan.

        """
        # Arrange
        jobs = pipeline["jobs"]
        # Act
        identidades = {job: jobs[job].get("identity") for job in JOBS}
        # Assert
        assert identidades["registrar"] == {"type": "managed"}
        assert [job for job, valor in identidades.items() if valor is not None] == ["registrar"]

    def test_las_dos_evaluaciones_no_comparten_el_corpus_por_casualidad(
        self, pipeline: dict[str, Any]
    ) -> None:
        """Cada evaluacion apunta a la salida de validar, no a la del otro job."""
        # Arrange
        jobs = pipeline["jobs"]
        # Act
        entrada_20b = jobs["evaluar_20b"]["inputs"]["corpus"]
        entrada_120b = jobs["evaluar_120b"]["inputs"]["corpus"]
        # Assert
        esperado = "${{parent.jobs.validar.outputs.corpus_validado}}"
        assert entrada_20b == esperado
        assert entrada_120b == esperado

    def test_los_dos_modelos_candidatos_son_distintos(self, pipeline: dict[str, Any]) -> None:
        # Arrange
        jobs = pipeline["jobs"]
        # Act
        modelos = {
            jobs["evaluar_20b"]["inputs"]["modelo"],
            jobs["evaluar_120b"]["inputs"]["modelo"],
        }
        # Assert
        assert modelos == {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}

    def test_el_limite_del_pipeline_es_el_del_plan(self, pipeline: dict[str, Any]) -> None:
        """340 es el tamano de eval.jsonl; la corrida corta lo sobreescribe con --set."""
        # Arrange
        # Act / Assert
        assert pipeline["inputs"]["limite"]["default"] == 340


class TestCoherenciaDeNombres:
    """Cada input y output cruzados entre pipeline y componente existe."""

    @pytest.mark.parametrize("job", JOBS)
    def test_los_inputs_del_job_existen_en_su_componente(
        self, pipeline: dict[str, Any], job: str
    ) -> None:
        # Arrange
        declarados = _componente_de(pipeline, job)["inputs"]
        recibidos = pipeline["jobs"][job].get("inputs", {})
        # Act
        huerfanos = {
            nombre
            for nombre in recibidos
            if nombre not in declarados and nombre not in RENOMBRES_POR_JOB[job]
        }
        # Assert
        assert not huerfanos, f"{job} pasa {huerfanos} y el componente no los declara"

    @pytest.mark.parametrize("job", ["evaluar_20b", "comparar", "registrar"])
    def test_los_tipos_de_los_inputs_coinciden(self, pipeline: dict[str, Any], job: str) -> None:
        """Un cable hereda el tipo de la salida que viene, no el texto de la referencia.

        Los valores literales (`modelo: openai/gpt-oss-20b`) se saltan: ahi el
        tipo lo define el propio componente, y compararlo contra si mismo no
        probaria nada.
        """
        # Arrange
        declarados = _componente_de(pipeline, job)["inputs"]
        recibidos = pipeline["jobs"][job].get("inputs", {})
        # Act / Assert
        for nombre, valor in recibidos.items():
            if nombre not in declarados:
                continue
            tipo_recibido = _tipo_del_cable(pipeline, valor)
            if tipo_recibido is None:
                continue
            assert tipo_recibido == declarados[nombre]["type"], (
                f"{job}.{nombre}: pipeline dice {tipo_recibido}, "
                f"componente dice {declarados[nombre]['type']}"
            )

    @pytest.mark.parametrize("job", JOBS)
    def test_las_referencias_a_outputs_apuntan_a_outputs_reales(
        self, pipeline: dict[str, Any], job: str
    ) -> None:
        """Un output mal nombrado rompe el grafo en Azure, no en la suite."""
        # Arrange
        recibidos = pipeline["jobs"][job].get("inputs", {})
        # Act
        referencias = {
            (origen, salida)
            for valor in recibidos.values()
            for origen, salida in re.findall(
                r"\$\{\{parent\.jobs\.([a-z0-9_]+)\.outputs\.([a-z0-9_]+)\}\}",
                str(valor),
            )
        }
        # Assert
        for origen, salida in referencias:
            salida_real = _componente_de(pipeline, origen)["outputs"]
            assert salida in salida_real, (
                f"{job} lee {salida} de {origen}, que solo produce {sorted(salida_real)}"
            )

    def test_el_pipeline_no_usa_referencias_nativas_de_key_vault(
        self, pipeline: dict[str, Any]
    ) -> None:
        """`${{keyvault:...}}` solo existe para online endpoints y deployments.

        Para command y pipeline jobs no funciona, y el Environment tampoco
        admite variables de entorno con referencias a secretos. La clave la
        lee el propio proceso con SecretClient.
        """
        # Arrange
        texto = PIPELINE.read_text(encoding="utf-8")
        # Act / Assert
        assert "${{keyvault:" not in texto
        assert "${{secrets:" not in texto
