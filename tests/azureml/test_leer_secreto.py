"""Pruebas de la obtencion de la clave de Groq dentro del job."""

import logging

import pytest

from leer_secreto import SecretoNoEncontrado, leer_secreto

CLAVE = "gsk-no-debe-aparecer-en-los-logs-1234"


class TestLeerSecreto:
    def test_devuelve_el_valor_de_la_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        monkeypatch.setenv("GROQ_API_KEY", CLAVE)

        # Act
        clave = leer_secreto("GROQ_API_KEY")

        # Assert
        assert clave == CLAVE

    def test_falla_con_error_explicito_si_falta_la_variable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        monkeypatch.delenv("GROQ_API_KEY", raising=False)

        # Act / Assert
        with pytest.raises(SecretoNoEncontrado) as error:
            leer_secreto("GROQ_API_KEY")

        assert "GROQ_API_KEY" in str(error.value)
        assert "key vault" in str(error.value).lower()

    def test_trata_un_valor_vacio_como_ausente(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Arrange
        monkeypatch.setenv("GROQ_API_KEY", "")

        # Act / Assert
        with pytest.raises(SecretoNoEncontrado):
            leer_secreto("GROQ_API_KEY")

    def test_no_escribe_la_clave_en_el_log(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Arrange
        monkeypatch.setenv("GROQ_API_KEY", CLAVE)

        # Act
        with caplog.at_level(logging.DEBUG):
            clave = leer_secreto("GROQ_API_KEY")

        # Assert
        assert clave == CLAVE
        assert not caplog.records
        assert CLAVE not in caplog.text

    def test_no_toma_el_valor_de_otra_variable_del_entorno(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        senuelo = "gsk-senuelo-que-no-debe-aparecer"
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.setenv("OTRA_CLAVE", senuelo)

        # Act / Assert
        with pytest.raises(SecretoNoEncontrado) as error:
            leer_secreto("GROQ_API_KEY")

        assert senuelo not in str(error.value)
