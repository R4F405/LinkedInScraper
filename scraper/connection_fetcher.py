"""
scraper/connection_fetcher.py

Dado un perfil de LinkedIn, hace clic en el enlace "X contactos" de la
propia página del perfil, hace scroll hasta cargar todos y devuelve sus URLs.
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def _scroll_current_page(driver: webdriver.Chrome, pause: float = 1.5):
    """Hace scroll en la página actual para asegurarse de que carguen todas las tarjetas."""
    last_count = 0
    for _ in range(10):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='linkedin.com/in/']")
        if len(cards) == last_count:
            break
        last_count = len(cards)


def _collect_all_pages(driver: webdriver.Chrome, collected: set, pause: float = 2.5, max_pages: int = 20):
    """
    Recorre todas las páginas de resultados clicando 'Siguiente' / 'Next'.
    Acumula las URLs limpias en `collected`.
    """
    for page_num in range(1, max_pages + 1):
        _scroll_current_page(driver, pause)
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
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", next_btn)
        time.sleep(pause)

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
        time.sleep(3)
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
    time.sleep(2)

    # Buscar el enlace "X contactos" en la página del perfil
    connection_link = None
    for sel in ["a[href*='connections']", "a[href*='/in/'][href*='connection']"]:
        try:
            links = driver.find_elements(By.CSS_SELECTOR, sel)
            for link in links:
                text = link.text.lower()
                if "contacto" in text or "connection" in text:
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
        print(f"  [connections] No se encontró el enlace 'contactos' en {slug}")
        return []

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", connection_link)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", connection_link)
    print(f"  [connections] Enlace 'contactos' clicado")
    time.sleep(3)

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

