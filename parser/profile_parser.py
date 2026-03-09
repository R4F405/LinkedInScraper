"""
parser/profile_parser.py

Lee archivos HTML guardados por Miquel en data/raw/ y extrae los campos
del perfil de LinkedIn: nombre, email, headline, localización, empresa y estudios.

El email se lee del JSON sidecar (<slug>.json) generado por profile_fetcher,
ya que LinkedIn lo carga dinámicamente en un modal que no queda en el HTML estático.

Uso standalone:
    from parser.profile_parser import parse_profile_file, parse_all_profiles
"""

import json
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
    "section.ci-email a",
    "div.pv-profile-section__section-info a[href^='mailto:']",
    "a[href^='mailto:']",
]

# Empresa: primera experiencia laboral (sección Experience)
_COMPANY_SELECTORS = [
    "#experience ~ .pvs-list__outer-container .pvs-entity span[aria-hidden='true']",
    "section[id*='experience'] .pv-profile-section__list-item .pv-entity__secondary-title",
    "li.artdeco-list__item .t-14.t-normal span[aria-hidden='true']",
]

# Estudios: primera entrada en Education
_EDUCATION_SELECTORS = [
    "#education ~ .pvs-list__outer-container .pvs-entity span[aria-hidden='true']",
    "section[id*='education'] .pv-profile-section__list-item .pv-entity__school-name",
    "li.pv-education-entity .pv-entity__school-name",
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


def _extract_company(soup: BeautifulSoup) -> str:
    """
    Extrae la empresa de la primera entrada de la sección Experience.
    Intenta primero selectores CSS; si no, busca el section por texto.
    """
    # Intento por selectores directos
    text = _first_text(soup, _COMPANY_SELECTORS)
    if text:
        return text

    # Fallback: buscar la sección Experience y leer el primer item
    for section in soup.find_all("section"):
        heading = section.find(["h2", "div", "span"], string=lambda t: t and "Experience" in t)
        if heading:
            items = section.select("span[aria-hidden='true']")
            # El primer span suele ser el título, el segundo la empresa
            if len(items) >= 2:
                return items[1].get_text(strip=True)
            if items:
                return items[0].get_text(strip=True)
    return ""


def _extract_education(soup: BeautifulSoup) -> str:
    """
    Extrae la institución educativa de la primera entrada de la sección Education.
    """
    text = _first_text(soup, _EDUCATION_SELECTORS)
    if text:
        return text

    for section in soup.find_all("section"):
        heading = section.find(["h2", "div", "span"], string=lambda t: t and "Education" in t)
        if heading:
            items = section.select("span[aria-hidden='true']")
            if items:
                return items[0].get_text(strip=True)
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
            "company": str,
            "education": str,
        }
    """
    soup = BeautifulSoup(html, "lxml")

    return {
        "name":      _first_text(soup, _NAME_SELECTORS),
        "email":     _first_text(soup, _EMAIL_SELECTORS),
        "headline":  _first_text(soup, _HEADLINE_SELECTORS),
        "location":  _first_text(soup, _LOCATION_SELECTORS),
        "company":   _extract_company(soup),
        "education": _extract_education(soup),
    }


def parse_profile_file(html_path: Path) -> dict:
    """
    Lee un archivo HTML de disco y lo parsea.
    Si existe un JSON sidecar con el mismo nombre, usa su email.
    Añade la clave 'source_file' con el nombre del archivo.
    """
    html = html_path.read_text(encoding="utf-8")
    data = parse_profile_html(html)

    # Leer email del JSON sidecar generado por profile_fetcher
    json_path = html_path.with_suffix(".json")
    if json_path.exists():
        try:
            sidecar = json.loads(json_path.read_text(encoding="utf-8"))
            data["email"] = sidecar.get("email", "") or data["email"]
        except (json.JSONDecodeError, KeyError):
            pass

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
