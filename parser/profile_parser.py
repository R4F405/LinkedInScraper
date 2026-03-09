"""
parser/profile_parser.py

Lee archivos HTML guardados por Miquel en data/raw/ y extrae los campos
del perfil de LinkedIn: nombre, email, headline y localización.

Uso standalone:
    from parser.profile_parser import parse_profile_file, parse_all_profiles
"""

from pathlib import Path
from bs4 import BeautifulSoup

from utils.config import RAW_HTML_DIR


# ---------------------------------------------------------------------------
# Selectores  (ajustar si LinkedIn cambia su HTML)
# ---------------------------------------------------------------------------
_NAME_SELECTORS = [
    "h1.text-heading-xlarge",
    "h1.inline.t-24.v-align-middle.break-words",
    ".pv-top-card--list li:first-child",
]

_HEADLINE_SELECTORS = [
    ".text-body-medium.break-words",
    ".pv-text-details__left-panel .text-body-medium",
    "div.ph5 .text-body-medium",
]

_LOCATION_SELECTORS = [
    ".text-body-small.inline.t-black--light.break-words",
    ".pv-text-details__left-panel .text-body-small",
    "div.ph5 span.text-body-small",
]

_EMAIL_SELECTORS = [
    "section.pv-contact-info__contact-type.ci-email a",
    ".ci-email .pv-contact-info__contact-link",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    """Devuelve el texto del primer selector que encuentre contenido."""
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return ""


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def parse_profile_html(html: str) -> dict:
    """
    Recibe el HTML completo de un perfil de LinkedIn (string) y devuelve
    un dict con los campos extraídos.

    Returns:
        {
            "name": str,
            "email": str,
            "headline": str,
            "location": str,
        }
    """
    soup = BeautifulSoup(html, "lxml")

    return {
        "name":     _first_text(soup, _NAME_SELECTORS),
        "email":    _first_text(soup, _EMAIL_SELECTORS),
        "headline": _first_text(soup, _HEADLINE_SELECTORS),
        "location": _first_text(soup, _LOCATION_SELECTORS),
    }


def parse_profile_file(html_path: Path) -> dict:
    """
    Lee un archivo HTML de disco y lo parsea.
    Añade la clave 'source_file' con el nombre del archivo.
    """
    html = html_path.read_text(encoding="utf-8")
    data = parse_profile_html(html)
    data["source_file"] = html_path.name
    return data


def parse_all_profiles(directory: Path = RAW_HTML_DIR) -> list[dict]:
    """
    Parsea todos los *.html de un directorio y devuelve una lista de dicts.
    """
    html_files = sorted(directory.glob("*.html"))
    if not html_files:
        return []
    return [parse_profile_file(f) for f in html_files]
