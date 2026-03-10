"""
scraper/profile_fetcher.py

Navega a cada URL de perfil de LinkedIn con el driver autenticado,
hace scroll para cargar el contenido dinámico, abre el modal de contacto,
extrae el email directamente con Selenium y guarda:
  - data/raw/<slug>.html   → HTML completo del perfil
  - data/raw/<slug>.json   → campos extraídos vía Selenium (email, etc.)
"""

import json
import random
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from utils.config import RAW_HTML_DIR

def _human_pause(min_s: float = 0.4, max_s: float = 1.2):
    """Pausa aleatoria para simular tiempos de reacción humanos."""
    time.sleep(random.uniform(min_s, max_s))

def _random_mouse_move(driver: webdriver.Chrome) -> None:
    """
    Mueve el puntero a una posición aleatoria de la ventana para que el
    tracker del navegador registre movimiento de ratón como un humano.
    Se captura cualquier excepción (elementos fuera de bounds, etc.).
    """
    try:
        w = driver.execute_script("return window.innerWidth")  or 1280
        h = driver.execute_script("return window.innerHeight") or  768
        x = random.randint(80, max(81, w - 80))
        y = random.randint(80, max(81, h - 80))
        ActionChains(driver).move_by_offset(x, y).perform()
        # Volver al origen para que no acumule offsets
        ActionChains(driver).move_by_offset(-x, -y).perform()
    except Exception:
        pass

def _scroll_to_load(driver: webdriver.Chrome):
    """
    Scroll humano: avanza en pequeños saltos aleatorios, con micro-pausas y
    ocasionales retrocesos cortos para imitar la lectura real de la página.
    Añade movimientos de ratón esporádicos y pausas de "lectura" extra.
    """
    total_height = driver.execute_script("return document.body.scrollHeight")
    current_pos = 0
    last_height = total_height

    while current_pos < last_height:
        # Salto aleatorio: entre 200 y 600 px (una porción de viewport)
        step = random.randint(200, 600)
        current_pos = min(current_pos + step, last_height)
        driver.execute_script(f"window.scrollTo(0, {current_pos});")
        _human_pause(0.08, 0.25)

        # Retroceso ocasional (30 %) para simular lectura
        if random.random() < 0.3:
            back = random.randint(30, 120)
            driver.execute_script(f"window.scrollTo(0, {max(0, current_pos - back)});")
            _human_pause(0.05, 0.15)
            driver.execute_script(f"window.scrollTo(0, {current_pos});")
            _human_pause(0.05, 0.15)

        # Movimiento de ratón ocasional (20 %)
        if random.random() < 0.20:
            _random_mouse_move(driver)

        # Pausa larga de "lectura" ocasional (8 %) — el usuario se detiene a leer
        if random.random() < 0.08:
            _human_pause(0.5, 1.5)

        # Actualizar altura por si cargó contenido nuevo
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height > last_height:
            last_height = new_height

    # Pausa final al terminar de leer la página
    _human_pause(0.3, 0.8)

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
            _human_pause(0.2, 0.5)
            # Usar JS click para evitar que la navbar lo intercepte
            driver.execute_script("arguments[0].click();", btn)
            # Esperar a que el modal aparezca
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.artdeco-modal"))
            )
            _human_pause(0.5, 1.2)
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

    # Buscar el teléfono dentro del modal:
    # LinkedIn lo muestra en un <span> plain, NO en un <a href="tel:">
    # Buscamos la sección cuyo <h3> contenga "tel" (Teléfono / Phone)
    phone = ""
    try:
        sections = driver.find_elements(By.CSS_SELECTOR, "section.pv-contact-info__contact-type")
        for sec in sections:
            try:
                heading = sec.find_element(By.CSS_SELECTOR, "h3.pv-contact-info__header")
                if "tel" in heading.text.lower() or "phone" in heading.text.lower():
                    # El número está en el primer span sin la clase --light
                    spans = sec.find_elements(By.CSS_SELECTOR, "ul span")
                    for sp in spans:
                        text = sp.text.strip()
                        classes = sp.get_attribute("class") or ""
                        if text and "t-black--light" not in classes:
                            phone = text
                            break
                    break
            except NoSuchElementException:
                continue
    except NoSuchElementException:
        pass

    # Cerrar el modal
    try:
        driver.find_element(By.CSS_SELECTOR,
            "button[aria-label='Descartar'], "
            "button.artdeco-modal__dismiss, "
            "button[aria-label='Dismiss']"
        ).click()
        _human_pause(0.15, 0.4)
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

    # Pausa inicial: simula que el usuario lee el perfil antes de actuar
    _human_pause(0.5, 1.2)
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
            delay = random.uniform(1, 3)
            print(f"  [scraper] esperando {delay:.1f}s antes del siguiente perfil...")
            time.sleep(delay)
        except Exception as e:
            print(f"  [scraper] ERROR en {url}: {e}")
    return saved