"""
tests/test_scraper.py

Tests para scraper/login.py y scraper/profile_fetcher.py.
Usan mocks — no abren navegador real ni hacen peticiones de red.
"""

from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import pytest

from scraper.login import login
from scraper.profile_fetcher import fetch_profile, fetch_all_profiles, _safe_filename, _scroll_to_bottom


# ===========================================================================
# Tests — login
# ===========================================================================

class TestLogin:

    @patch("scraper.login.os.getenv")
    def test_raises_if_no_credentials(self, mock_getenv):
        mock_getenv.return_value = None
        driver = MagicMock()
        with pytest.raises(ValueError, match="Faltan"):
            login(driver)

    @patch("scraper.login.WebDriverWait")
    @patch("scraper.login.os.getenv", side_effect=["test@email.com", "password123"])
    def test_login_exitoso_retorna_true(self, mock_getenv, mock_wait):
        driver = MagicMock()
        driver.current_url = "https://www.linkedin.com/feed"

        mock_wait.return_value.until.return_value = MagicMock()
        driver.find_element.return_value = MagicMock()

        # Simular que la URL contiene /feed tras el click
        driver.current_url = "https://www.linkedin.com/feed"
        mock_wait.return_value.until.side_effect = [MagicMock(), True]

        result = login(driver)
        assert result is True

    @patch("scraper.login.WebDriverWait")
    @patch("scraper.login.os.getenv", side_effect=["test@email.com", "password123"])
    def test_login_fallido_retorna_false(self, mock_getenv, mock_wait):
        from selenium.common.exceptions import TimeoutException
        driver = MagicMock()
        mock_wait.return_value.until.side_effect = TimeoutException()

        result = login(driver)
        assert result is False


# ===========================================================================
# Tests — profile_fetcher
# ===========================================================================

class TestSafeFilename:

    def test_extrae_nombre_de_url(self):
        url = "https://www.linkedin.com/in/maria-garcia/"
        assert _safe_filename(url) == "maria-garcia.html"

    def test_funciona_sin_trailing_slash(self):
        url = "https://www.linkedin.com/in/john-doe"
        assert _safe_filename(url) == "john-doe.html"


class TestScrollToBottom:

    def test_ejecuta_script_varias_veces(self):
        driver = MagicMock()
        _scroll_to_bottom(driver, pauses=3)
        assert driver.execute_script.call_count == 3


class TestFetchProfile:

    @patch("scraper.profile_fetcher.WebDriverWait")
    @patch("scraper.profile_fetcher.time.sleep")
    def test_guarda_html_y_retorna_path(self, mock_sleep, mock_wait, tmp_path):
        driver = MagicMock()
        driver.page_source = "<html><h1>Maria García</h1></html>"
        mock_wait.return_value.until.return_value = MagicMock()

        result = fetch_profile(driver, "https://www.linkedin.com/in/maria-garcia/", tmp_path)

        assert result == tmp_path / "maria-garcia.html"
        assert result.exists()
        assert "Maria García" in result.read_text(encoding="utf-8")

    @patch("scraper.profile_fetcher.WebDriverWait")
    def test_raises_timeout_si_no_carga(self, mock_wait, tmp_path):
        from selenium.common.exceptions import TimeoutException
        driver = MagicMock()
        mock_wait.return_value.until.side_effect = TimeoutException()

        with pytest.raises(TimeoutException):
            fetch_profile(driver, "https://www.linkedin.com/in/alguien/", tmp_path)


class TestFetchAllProfiles:

    @patch("scraper.profile_fetcher.fetch_profile")
    @patch("scraper.profile_fetcher.time.sleep")
    def test_retorna_lista_de_paths(self, mock_sleep, mock_fetch, tmp_path):
        mock_fetch.side_effect = [
            tmp_path / "perfil-1.html",
            tmp_path / "perfil-2.html",
        ]
        urls = [
            "https://www.linkedin.com/in/perfil-1/",
            "https://www.linkedin.com/in/perfil-2/",
        ]
        results = fetch_all_profiles(MagicMock(), urls, tmp_path)
        assert len(results) == 2

    @patch("scraper.profile_fetcher.fetch_profile")
    @patch("scraper.profile_fetcher.time.sleep")
    def test_espera_entre_perfiles(self, mock_sleep, mock_fetch, tmp_path):
        mock_fetch.return_value = tmp_path / "perfil.html"
        fetch_all_profiles(MagicMock(), ["https://www.linkedin.com/in/a/"], tmp_path, delay=2.0)
        mock_sleep.assert_called_with(2.0)