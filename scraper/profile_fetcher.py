"""
scraper/profile_fetcher.py

Navega a cada perfil de LinkedIn, hace scroll para cargar
el contenido dinámico y guarda el HTML en data/raw/.
"""

import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from utils.config import RAW_HTML_DIR


def _scroll_to_bottom(driver: webdriver.Chrome, pauses: int = 3) -> None:
    """Hace scroll progresivo para que LinkedIn cargue el contenido dinámico."""
    for _ in range(pauses):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)


def _safe_filename(url: str) -> str:
    """Convierte una URL de perfil en un nombre de archivo seguro."""
    # https://www.linkedin.com/in/nombre-apellido/ -> nombre-apellido.html
    parts = [p for p in url.rstrip("/").split("/") if p]
    return f"{parts[-1]}.html"


def fetch_profile(driver: webdriver.Chrome, url: str, output_dir: Path = RAW_HTML_DIR) -> Path:
    """
    Navega a un perfil, espera que cargue, hace scroll y guarda el HTML.

    Args:
        driver:     Instancia de Chrome ya autenticada.
        url:        URL del perfil de LinkedIn.
        output_dir: Directorio donde guardar el HTML.

    Returns:
        Path del archivo HTML guardado.
    """
    driver.get(url)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
    except TimeoutException:
        raise TimeoutException(f"El perfil no cargó a tiempo: {url}")

    _scroll_to_bottom(driver)

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(url)
    filepath = output_dir / filename
    filepath.write_text(driver.page_source, encoding="utf-8")

    return filepath


def fetch_all_profiles(
    driver: webdriver.Chrome,
    urls: list[str],
    output_dir: Path = RAW_HTML_DIR,
    delay: float = 2.0,
) -> list[Path]:
    """
    Itera sobre una lista de URLs, descarga cada perfil y lo guarda.

    Args:
        delay: Segundos de espera entre perfiles para evitar detección.

    Returns:
        Lista de Paths de los archivos guardados.
    """
    saved = []
    for url in urls:
        filepath = fetch_profile(driver, url, output_dir)
        saved.append(filepath)
        time.sleep(delay)
    return saved