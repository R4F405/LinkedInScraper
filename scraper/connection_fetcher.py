"""
scraper/connection_fetcher.py

Dado un perfil de LinkedIn, hace clic en el enlace "X contactos" de la
propia página del perfil, hace scroll hasta cargar todos y devuelve sus URLs.
"""

import random
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def _human_pause(min_s: float = 0.4, max_s: float = 1.2):
    """Pausa aleatoria para simular tiempos de reacción humanos."""
    time.sleep(random.uniform(min_s, max_s))


def _random_mouse_move(driver: webdriver.Chrome) -> None:
    """Movimiento aleatorio del puntero para registrar actividad de ratón."""
    try:
        w = driver.execute_script("return window.innerWidth")  or 1280
        h = driver.execute_script("return window.innerHeight") or  768
        x = random.randint(60, max(61, w - 60))
        y = random.randint(60, max(61, h - 60))
        ActionChains(driver).move_by_offset(x, y).perform()
        ActionChains(driver).move_by_offset(-x, -y).perform()
    except Exception:
        pass


def _scroll_current_page(driver: webdriver.Chrome):
    """
    Scroll humano en la lista de conexiones: avanza en pasos aleatorios
    con micro-pausas, retrocesos ocasionales y movimientos de ratón.
    """
    last_count = 0
    total_height = driver.execute_script("return document.body.scrollHeight")
    current_pos = 0
    last_height = total_height

    while current_pos < last_height:
        step = random.randint(250, 550)
        current_pos = min(current_pos + step, last_height)
        driver.execute_script(f"window.scrollTo(0, {current_pos});")
        _human_pause(0.1, 0.3)

        if random.random() < 0.25:
            back = random.randint(40, 150)
            driver.execute_script(f"window.scrollTo(0, {max(0, current_pos - back)});")
            _human_pause(0.05, 0.15)
            driver.execute_script(f"window.scrollTo(0, {current_pos});")

        # Movimiento de ratón ocasional (20 %)
        if random.random() < 0.20:
            _random_mouse_move(driver)

        # Pausa larga de "lectura" ocasional (6 %)
        if random.random() < 0.06:
            _human_pause(0.5, 1.5)

        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height > last_height:
            last_height = new_height

        cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='linkedin.com/in/']")
        if len(cards) == last_count and current_pos >= last_height:
            break
        last_count = len(cards)

    _human_pause(0.3, 0.8)


def _collect_all_pages(driver: webdriver.Chrome, collected: set, max_pages: int = 20):
    """
    Recorre todas las páginas de resultados clicando 'Siguiente' / 'Next'.
    Acumula las URLs limpias en `collected`.
    """
    for page_num in range(1, max_pages + 1):
        _scroll_current_page(driver)
        # Extraer perfiles de la página actual
        urls_page = _extract_profile_urls(driver)
        before = len(collected)
        collected.update(urls_page)
        print(f"    página {page_num}: {len(urls_page)} tarjetas, {len(collected) - before} nuevas ({len(collected)} total)")

        # Buscar botón "Siguiente" / "Next"
        next_btn = None
        for label in ["Siguiente", "Next"]:
            try:
                next_btn = driver.find_element(
                    By.XPATH,
                    f"//button[@aria-label='{label}'] | //a[@aria-label='{label}']"
                )
                if next_btn.is_enabled():
                    break
                else:
                    next_btn = None
            except NoSuchElementException:
                pass

        if not next_btn:
            # También intentar por texto visible
            try:
                next_btn = driver.find_element(
                    By.XPATH,
                    "//button[contains(normalize-space(), 'Siguiente') or contains(normalize-space(), 'Next')]"
                )
                if not next_btn.is_enabled():
                    next_btn = None
            except NoSuchElementException:
                pass

        if not next_btn:
            print(f"    No hay más páginas.")
            break

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
        _human_pause(0.2, 0.5)
        driver.execute_script("arguments[0].click();", next_btn)
        _human_pause(0.8, 1.8)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/in/')]"))
            )
        except TimeoutException:
            break


def _extract_profile_urls(driver: webdriver.Chrome) -> list[str]:
    """Extrae y deduplica todas las URLs de perfil visibles en la página."""
    elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='linkedin.com/in/'], a[href^='/in/']")
    seen = set()
    urls = []
    for el in elements:
        href = el.get_attribute("href") or ""
        # Normalizar a URL absoluta
        if href.startswith("/in/"):
            href = "https://www.linkedin.com" + href
        base = href.split("?")[0].rstrip("/")
        # Solo URLs de perfil, no sub-páginas como /in/xxx/details/
        parts = base.split("/in/")
        if len(parts) != 2:
            continue
        slug = parts[1].strip("/")
        # Ignorar slugs vacíos o sub-páginas (contienen /)
        if not slug or "/" in slug:
            continue
        clean = f"https://www.linkedin.com/in/{slug}/"
        if clean not in seen:
            seen.add(clean)
            urls.append(clean)
    return urls


def get_connections(driver: webdriver.Chrome, profile_url: str) -> list[str]:
    """
    Si profile_url es una URL de búsqueda/resultados de LinkedIn, la carga
    directamente y extrae los perfiles. Si es una URL de perfil /in/, busca
    y clica el enlace 'X contactos'.

    Returns:
        Lista de URLs de perfil de cada conexión.
    """
    # Caso A: ya es una página de resultados (el usuario pegó la URL de contactos)
    if "/search/results/" in profile_url or "connectionOf=" in profile_url:
        print(f"  [connections] URL de resultados detectada, cargando directamente...")
        driver.get(profile_url)
        _human_pause(0.8, 1.5)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/in/')]"))
            )
        except TimeoutException:
            print(f"  [connections] No cargaron resultados")
            return []
        collected = set()
        _collect_all_pages(driver, collected)
        urls = list(collected)
        print(f"  [connections] {len(urls)} perfiles encontrados")
        return urls

    # Caso B: es una URL de perfil /in/ — buscar y clicar "X contactos"
    slug = profile_url.rstrip("/").split("/")[-1]
    print(f"  [connections] Navegando al perfil: {slug}")
    driver.get(profile_url)

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
        )
    except TimeoutException:
        pass
    _human_pause(0.8, 1.8)

    # Buscar el enlace "X contactos" en la página del perfil
    connection_link = None
    for sel in [
        "a[href*='connections']",
        "a[href*='/in/'][href*='connection']",
        "a[href*='/search/results/people/'][href*='connectionOf=']",
    ]:
        try:
            links = driver.find_elements(By.CSS_SELECTOR, sel)
            for link in links:
                text = link.text.lower()
                href = (link.get_attribute("href") or "").lower()
                if (
                    "contacto" in text
                    or "connection" in text
                    or "network" in text
                    or "connectionof=" in href
                    or "/search/results/people/" in href
                ):
                    connection_link = link
                    break
            if connection_link:
                break
        except NoSuchElementException:
            continue

    if not connection_link:
        try:
            connection_link = driver.find_element(
                By.XPATH,
                "//*[contains(translate(normalize-space(), 'CONTACTOS', 'contactos'), 'contactos') and (self::a or self::button)]"
            )
        except NoSuchElementException:
            pass

    if not connection_link:
        # Fallback adicional: cualquier enlace a resultados de personas con connectionOf
        try:
            connection_link = driver.find_element(
                By.XPATH,
                "//a[contains(@href, '/search/results/people/') and contains(@href, 'connectionOf=')]"
            )
        except NoSuchElementException:
            pass

    if not connection_link:
        print(f"  [connections] No se encontró el enlace 'contactos' en {slug}")
        return []

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", connection_link)
    _human_pause(0.2, 0.5)
    driver.execute_script("arguments[0].click();", connection_link)
    print(f"  [connections] Enlace 'contactos' clicado")
    _human_pause(1.0, 2.0)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/in/')]"))
        )
    except TimeoutException:
        print(f"  [connections] No cargaron resultados para {slug}")
        return []

    collected = set()
    _collect_all_pages(driver, collected)
    urls = [u for u in collected if slug not in u]
    print(f"  [connections] {len(urls)} conexiones encontradas para {slug}")
    return urls

