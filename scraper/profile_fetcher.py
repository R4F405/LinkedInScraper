"""
scraper/profile_fetcher.py

Navega a cada URL de perfil de LinkedIn con el driver autenticado,
hace scroll para cargar el contenido dinámico, abre el modal de contacto,
extrae el email directamente con Selenium y guarda:
  - data/raw/<slug>.html   → HTML completo del perfil
  - data/raw/<slug>.json   → campos extraídos vía Selenium (email, etc.)
"""

import json
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from utils.config import RAW_HTML_DIR


def _scroll_to_load(driver: webdriver.Chrome, pauses: int = 3, pause_time: float = 1.5):
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(pauses):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_time)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def _extract_contact_from_modal(driver: webdriver.Chrome) -> dict:
    """
    Abre el modal 'Información de contacto' y extrae el email y teléfono con Selenium
    mientras el modal está activo en el DOM.
    Devuelve un dict con 'email' y 'phone', ambos string (vacío si no se encuentra).
    """
    # Intentar abrir el modal
    btn_selectors = [
        "a[href*='overlay/contact-info']",
        "#top-card-text-details-contact-info",
        "a[data-control-name='contact_see_more']",
    ]
    opened = False
    for sel in btn_selectors:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            # Scroll hasta el elemento para que no quede tapado por la navbar
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.5)
            # Usar JS click para evitar que la navbar lo intercepte
            driver.execute_script("arguments[0].click();", btn)
            # Esperar a que el modal aparezca
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.artdeco-modal"))
            )
            time.sleep(1.5)
            opened = True
            break
        except (TimeoutException, NoSuchElementException):
            continue

    if not opened:
        return {"email": "", "phone": ""}

    # Buscar el email dentro del modal — buscar cualquier enlace mailto:
    email_selectors = [
        "div.artdeco-modal a[href^='mailto:']",
        "section.ci-email a",
        "a[href^='mailto:']",
    ]
    email = ""
    for sel in email_selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            href = el.get_attribute("href") or ""
            text = el.text.strip()
            email = text if text else href.replace("mailto:", "").strip()
            if email:
                break
        except NoSuchElementException:
            continue

    # Buscar el teléfono dentro del modal — buscar cualquier enlace tel:
    phone_selectors = [
        "div.artdeco-modal a[href^='tel:']",
        "section.ci-phone a",
        "a[href^='tel:']",
    ]
    phone = ""
    for sel in phone_selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            href = el.get_attribute("href") or ""
            text = el.text.strip()
            phone = text if text else href.replace("tel:", "").strip()
            if phone:
                break
        except NoSuchElementException:
            continue

    # Cerrar el modal
    try:
        driver.find_element(By.CSS_SELECTOR,
            "button[aria-label='Descartar'], "
            "button.artdeco-modal__dismiss, "
            "button[aria-label='Dismiss']"
        ).click()
        time.sleep(0.5)
    except NoSuchElementException:
        pass

    return {"email": email, "phone": phone}


def fetch_profile(driver: webdriver.Chrome, url: str) -> Path:
    """
    Navega a un perfil, extrae el email del modal con Selenium,
    guarda el HTML y un JSON sidecar con el email.

    Returns:
        Path del archivo HTML guardado en data/raw/.
    """
    driver.get(url)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
        )
    except TimeoutException:
        pass

    _scroll_to_load(driver)

    # Extraer email y teléfono con Selenium mientras el modal está vivo
    contact = _extract_contact_from_modal(driver)

    # Guardar HTML
    slug = url.rstrip("/").split("/")[-1]
    html_path = RAW_HTML_DIR / f"{slug}.html"
    html_path.write_text(driver.page_source, encoding="utf-8")

    # Guardar JSON sidecar con email y teléfono
    json_path = RAW_HTML_DIR / f"{slug}.json"
    json_path.write_text(json.dumps(contact, ensure_ascii=False), encoding="utf-8")

    return html_path


def fetch_all_profiles(driver: webdriver.Chrome, urls: list[str]) -> list[Path]:
    """
    Navega y guarda el HTML de cada URL de la lista.
    Returns lista de Paths de los archivos HTML guardados.
    """
    saved = []
    for url in urls:
        try:
            path = fetch_profile(driver, url)
            saved.append(path)
            print(f"  [scraper] guardado → {path.name}")
            time.sleep(3)
        except Exception as e:
            print(f"  [scraper] ERROR en {url}: {e}")
    return saved

