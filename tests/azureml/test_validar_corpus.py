"""Pruebas de la validacion del corpus gold_v1 antes de evaluar."""

import hashlib
import json
from pathlib import Path

import pytest

from validar_corpus import ChecksumNoCoincide, leer_checksums, validar

ARCHIVOS_CON_CHECKSUM = ("dev.jsonl", "eval.jsonl", "gold_standard_v1.jsonl")


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _corpus(tmp_path: Path, lineas: dict[str, int]) -> Path:
    """Crea un gold_v1 sintetico con los conteos pedidos y su README."""
    raiz = tmp_path / "gold_v1"
    raiz.mkdir()
    for nombre, cantidad in lineas.items():
        (raiz / nombre).write_text(
            "".join(f'{{"i": {i}}}\n' for i in range(cantidad)), encoding="utf-8"
        )
    (raiz / "concordancia_interanotador.md").write_text("# Concordancia\n", encoding="utf-8")

    filas = "\n".join(
        f"| `{nombre}` | `{_sha256(raiz / nombre)}` |"
        for nombre in lineas
        if nombre.endswith(".jsonl")
    )
    (raiz / "README_gold_v1.md").write_text(
        "# Gold standard v1\n\n## Checksums\n\n| Archivo | SHA-256 |\n|---------|---------|\n"
        f"{filas}\n",
        encoding="utf-8",
    )
    return raiz


class TestLeerChecksums:
    def test_extrae_un_archivo_por_fila_de_la_tabla(self, tmp_path: Path) -> None:
        # Arrange
        raiz = _corpus(tmp_path, {"dev.jsonl": 2, "eval.jsonl": 3})

        # Act
        checksums = leer_checksums(raiz / "README_gold_v1.md")

        # Assert
        assert set(checksums) == {"dev.jsonl", "eval.jsonl"}


class TestValidar:
    def test_falla_si_el_readme_no_declara_un_archivo_requerido(self, tmp_path: Path) -> None:
        # Arrange
        raiz = _corpus(tmp_path, {"dev.jsonl": 2})
        (raiz / "README_gold_v1.md").write_text(
            "# Gold standard v1\n\n## Checksums\n\n| Archivo | SHA-256 |\n|---------|---------|\n"
            f"| `dev.jsonl` | `{_sha256(raiz / 'dev.jsonl')}` |\n",
            encoding="utf-8",
        )

        # Act / Assert
        with pytest.raises(ChecksumNoCoincide, match="eval.jsonl"):
            validar(raiz, tmp_path / "salida")

    def test_escribe_el_eval_jsonl_bajo_gold_v1(self, tmp_path: Path) -> None:
        # Arrange
        raiz = _corpus(tmp_path, {"dev.jsonl": 2, "eval.jsonl": 3, "gold_standard_v1.jsonl": 5})
        salida = tmp_path / "salida"

        # Act
        validar(raiz, salida)

        # Assert
        destino = salida / "gold_v1" / "eval.jsonl"
        assert destino.exists()
        assert destino.read_bytes() == (raiz / "eval.jsonl").read_bytes()

    def test_manifesto_lista_los_cinco_archivos(self, tmp_path: Path) -> None:
        # Arrange
        raiz = _corpus(tmp_path, {"dev.jsonl": 2, "eval.jsonl": 3, "gold_standard_v1.jsonl": 5})
        salida = tmp_path / "salida"

        # Act
        validar(raiz, salida)

        # Assert
        manifiesto = json.loads((salida / "manifest.json").read_text(encoding="utf-8"))
        nombres = [archivo["nombre"] for archivo in manifiesto["archivos"]]
        assert set(nombres) == {
            "dev.jsonl",
            "eval.jsonl",
            "gold_standard_v1.jsonl",
            "concordancia_interanotador.md",
            "README_gold_v1.md",
        }

    def test_manifesto_pone_checksum_solo_en_los_tres_jsonl(self, tmp_path: Path) -> None:
        # Arrange
        raiz = _corpus(tmp_path, {"dev.jsonl": 2, "eval.jsonl": 3, "gold_standard_v1.jsonl": 5})
        salida = tmp_path / "salida"

        # Act
        validar(raiz, salida)

        # Assert
        manifiesto = json.loads((salida / "manifest.json").read_text(encoding="utf-8"))
        con_hash = {a["nombre"] for a in manifiesto["archivos"] if a["sha256"] is not None}
        sin_hash = {a["nombre"] for a in manifiesto["archivos"] if a["sha256"] is None}
        assert con_hash == set(ARCHIVOS_CON_CHECKSUM)
        assert sin_hash == {"concordancia_interanotador.md", "README_gold_v1.md"}

    def test_manifesto_incluye_el_conteo_de_ejemplos(self, tmp_path: Path) -> None:
        # Arrange
        raiz = _corpus(tmp_path, {"dev.jsonl": 2, "eval.jsonl": 3, "gold_standard_v1.jsonl": 5})
        salida = tmp_path / "salida"

        # Act
        manifiesto = validar(raiz, salida)

        # Assert
        conteos = {a["nombre"]: a["conteo"] for a in manifiesto["archivos"]}
        assert conteos == {
            "dev.jsonl": 2,
            "eval.jsonl": 3,
            "gold_standard_v1.jsonl": 5,
            "concordancia_interanotador.md": None,
            "README_gold_v1.md": None,
        }

    def test_falla_si_un_checksum_no_coincide(self, tmp_path: Path) -> None:
        # Arrange
        raiz = _corpus(tmp_path, {"dev.jsonl": 2, "eval.jsonl": 3, "gold_standard_v1.jsonl": 5})
        (raiz / "dev.jsonl").write_text('{"i": 0}\n', encoding="utf-8")

        # Act / Assert
        with pytest.raises(ChecksumNoCoincide, match="dev.jsonl"):
            validar(raiz, tmp_path / "salida")

    def test_no_escribe_salida_si_falla(self, tmp_path: Path) -> None:
        # Arrange
        raiz = _corpus(tmp_path, {"dev.jsonl": 2, "eval.jsonl": 3, "gold_standard_v1.jsonl": 5})
        (raiz / "eval.jsonl").write_text("corrupto\n", encoding="utf-8")
        salida = tmp_path / "salida"

        # Act
        with pytest.raises(ChecksumNoCoincide):
            validar(raiz, salida)

        # Assert
        assert not (salida / "manifest.json").exists()
