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

_PHONE_SELECTORS = [
    "section.pv-contact-info__contact-type.ci-phone a",
    ".ci-phone .pv-contact-info__contact-link",
    "section.ci-phone a",
    "a[href^='tel:']",
]

_NAME_REJECT_TOKENS = (
    "linkedin",
    "informacion de contacto",
    "información de contacto",
    "datos destacados",
    "acerca de",
    "contactos",
    "notificaciones",
)

_COMPANY_ROLE_HINTS = (
    "developer",
    "desarroll",
    "responsable",
    "mozo",
    "manager",
    "ingenier",
    "consultor",
    "analyst",
    "director",
    "software",
    "full stack",
)


def _extract_phone(soup: BeautifulSoup) -> str:
    """
    Extrae el teléfono del modal de contacto guardado en el HTML.
    LinkedIn no usa <a href='tel:'>, sino un <span> plain dentro de la
    sección cuyo <h3> contiene 'teléfono' o 'phone'.
    """
    for section in soup.find_all("section", class_="pv-contact-info__contact-type"):
        heading = section.find("h3", class_="pv-contact-info__header")
        if not heading:
            continue
        if "tel" not in heading.get_text().lower() and "phone" not in heading.get_text().lower():
            continue
        ul = section.find("ul")
        if not ul:
            continue
        for span in ul.find_all("span"):
            classes = " ".join(span.get("class", []))
            text = span.get_text(strip=True)
            if text and "t-black--light" not in classes:
                return text
    # Fallback: selector CSS por si alguna versión sí usa enlace tel:
    return _first_text(soup, _PHONE_SELECTORS)

# Empresa: primera experiencia laboral (sección Experience)
# NOTA: el tercer selector era demasiado amplio y recogía textos de seguimiento/saludos.
_COMPANY_SELECTORS = [
    "#experience ~ .pvs-list__outer-container .pvs-entity span[aria-hidden='true']",
    "section[id*='experience'] .pv-profile-section__list-item .pv-entity__secondary-title",
]

# Patrones de texto que NO son nombres de empresa (saludos, botones, etc.)
_COMPANY_REJECT = ("hola ", "hello ", "siguiendo", "following", "conectar", "connect", "mensaje")

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


def _normalize_ws(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _looks_like_name(text: str) -> bool:
    t = _normalize_ws(text)
    if not t or len(t) > 80:
        return False
    low = t.lower()
    if any(tok in low for tok in _NAME_REJECT_TOKENS):
        return False
    if "@" in t or "http" in low:
        return False
    if any(ch.isdigit() for ch in t):
        return False
    return any(ch.isalpha() for ch in t)


def _extract_name(soup: BeautifulSoup) -> str:
    # 1) Selectores tradicionales
    name = _first_text(soup, _NAME_SELECTORS)
    if _looks_like_name(name):
        return name

    # 2) Top card moderno: heading principal en <h2>
    for h2 in soup.find_all("h2"):
        text = _normalize_ws(h2.get_text(" ", strip=True))
        if _looks_like_name(text):
            return text

    # 3) Titulo del documento: "Nombre | LinkedIn"
    if soup.title and soup.title.string:
        title = _normalize_ws(soup.title.string)
        if "|" in title:
            candidate = _normalize_ws(title.split("|", 1)[0])
            if _looks_like_name(candidate):
                return candidate

    # 4) Modal de contacto: "Perfil de X"
    for p in soup.find_all("p"):
        text = _normalize_ws(p.get_text(" ", strip=True))
        low = text.lower()
        if low.startswith("perfil de ") and len(text) > len("Perfil de "):
            candidate = text[len("Perfil de "):].strip()
            if _looks_like_name(candidate):
                return candidate

    return ""


def _extract_location(soup: BeautifulSoup) -> str:
    # 1) Selectores tradicionales
    text = _first_text(soup, _LOCATION_SELECTORS)
    if text:
        return text

    # 2) En el top-card moderno, justo antes del enlace de contacto
    anchor = soup.find("a", href=lambda h: h and "overlay/contact-info" in h)
    if anchor:
        container = anchor.parent
        if container:
            for sib in container.find_previous_siblings("p"):
                t = _normalize_ws(sib.get_text(" ", strip=True))
                if not t or t == "·":
                    continue
                low = t.lower()
                if "@" in t or "contacto" in low or "seguidores" in low:
                    continue
                if len(t) <= 100:
                    return t

    # 3) Fallback: primera frase corta con pinta de ubicación
    for p in soup.find_all("p"):
        t = _normalize_ws(p.get_text(" ", strip=True))
        low = t.lower()
        if not t or len(t) > 100:
            continue
        if "@" in t or "http" in low:
            continue
        if any(bad in low for bad in ("seguidores", "contacto", "acerca", "hola", "mensaje")):
            continue
        if "," in t or "alrededores" in low:
            return t

    return ""


def _extract_company(soup: BeautifulSoup) -> str:
    """
    Extrae la empresa actual del perfil.

    Estrategia 1 (más fiable): top card — botones con aria-label que empieza
    por "Empresa actual:" / "Current company:". El nombre se saca del propio
    aria-label (entre ': ' y '.') para evitar ruido del DOM interior.

    Estrategia 2: sección Experience en el cuerpo del perfil, acotada por
    su id o por el heading h2, filtrando textos que no sean empresas.
    """
    def _is_valid_company(text: str) -> bool:
        if not text:
            return False
        low = text.lower()
        if low.startswith(_COMPANY_REJECT):
            return False
        if any(hint in low for hint in _COMPANY_ROLE_HINTS):
            return False
        return True

    # Intento 1: aria-label en el top card
    prefixes = ("empresa actual:", "current company:", "empresa:")
    for btn in soup.find_all(True, attrs={"aria-label": True}):
        label = btn["aria-label"].strip()
        label_lower = label.lower()
        for prefix in prefixes:
            if label_lower.startswith(prefix):
                # Extraer lo que hay entre ": " y el primer "."
                rest = label[len(prefix):].strip()
                company = rest.split(".")[0].strip()
                if _is_valid_company(company):
                    return company

    # Intento 2: selector CSS acotado a #experience
    for sel in _COMPANY_SELECTORS:
        for el in soup.select(sel):
            text = el.get_text(strip=True)
            if _is_valid_company(text):
                return text

    # Intento 2b: tarjeta de empresa del top-card moderno
    for svg in soup.find_all("svg", id=lambda v: v and str(v).startswith("company-accent")):
        parent = svg.find_parent()
        if not parent:
            continue
        p = parent.find_next("p")
        if not p:
            continue
        text = _normalize_ws(p.get_text(" ", strip=True))
        if _is_valid_company(text):
            return text

    # Intento 2c: línea resumen tipo "Empresa · Centro"
    for p in soup.find_all("p"):
        text = _normalize_ws(p.get_text(" ", strip=True))
        if "·" not in text:
            continue
        low = text.lower()
        if any(bad in low for bad in ("1er", "2º", "2o", "contacto", "seguidores", "mensaje")):
            continue
        first = _normalize_ws(text.split("·", 1)[0])
        if _is_valid_company(first):
            return first

    # Intento 3: buscar el <section> cuyo h2 diga "Experiencia" / "Experience"
    for section in soup.find_all("section"):
        heading = section.find(["h2"], string=lambda t: t and (
            "experience" in t.lower() or "experiencia" in t.lower()
        ))
        if not heading:
            continue
        items = section.select("span[aria-hidden='true']")
        candidates = [i.get_text(strip=True) for i in items if _is_valid_company(i.get_text(strip=True))]
        if len(candidates) >= 2:
            return candidates[1]
        if candidates:
            return candidates[0]
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
        "name":      _extract_name(soup),
        "email":     _first_text(soup, _EMAIL_SELECTORS),
        "phone":     _extract_phone(soup),
        "location":  _extract_location(soup),
        "company":   _extract_company(soup),
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
            data["phone"] = sidecar.get("phone", "") or data["phone"]
        except (json.JSONDecodeError, KeyError):
            pass

    return data


def parse_all_profiles(directory: Path = RAW_HTML_DIR) -> list[dict]:
    """
    Parsea todos los *.html de un directorio y devuelve una lista de dicts.
    """
    html_files = sorted(directory.glob("*.html"))
    if not html_files:
        return []
    return [parse_profile_file(f) for f in html_files]
