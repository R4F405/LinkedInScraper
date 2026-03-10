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


def _get_scrollable_container(driver: webdriver.Chrome):
    """Busca un contenedor con overflow scroll (LinkedIn suele usar un div para la lista)."""
    try:
        containers = driver.find_elements(
            By.CSS_SELECTOR,
            "div[class*='scaffold-layout__main'], div[class*='ph5'][class*='overflow'], section[role='dialog'] .scroller, [class*='connections']"
        )
        for c in containers:
            overflow = c.get_attribute("style") or ""
            if "overflow" in overflow.lower() or "scroll" in overflow.lower():
                return c
            try:
                oy = driver.execute_script("return arguments[0].style.overflowY || getComputedStyle(arguments[0]).overflowY", c)
                if oy in ("auto", "scroll"):
                    return c
            except Exception:
                pass
    except Exception:
        pass
    return None


def _scroll_current_page(driver: webdriver.Chrome):
    """
    Scroll humano en la lista de conexiones. Prueba a scrollar el contenedor
    interno de LinkedIn; si no, scroll de ventana. Varias pasadas hasta que
    no aparezcan más tarjetas (carga bajo demanda).
    """
    container = _get_scrollable_container(driver)
    stable_rounds = 0
    last_count = 0
    max_stable = 2  # parar tras 2 pasadas sin nuevos contactos

    while stable_rounds < max_stable:
        total_height = driver.execute_script(
            "return arguments[0] ? arguments[0].scrollHeight : document.body.scrollHeight",
            container
        )
        current_pos = 0
        last_height = total_height

        while current_pos < last_height:
            step = random.randint(280, 500)
            current_pos = min(current_pos + step, last_height)
            if container:
                try:
                    driver.execute_script("arguments[0].scrollTop = arguments[1];", container, current_pos)
                except Exception:
                    driver.execute_script(f"window.scrollTo(0, {current_pos});")
            else:
                driver.execute_script(f"window.scrollTo(0, {current_pos});")
            _human_pause(0.25, 0.7)

            if random.random() < 0.2:
                back = random.randint(50, 120)
                current_pos = max(0, current_pos - back)
                if container:
                    try:
                        driver.execute_script("arguments[0].scrollTop = arguments[1];", container, current_pos)
                    except Exception:
                        pass
                _human_pause(0.1, 0.3)

            new_height = driver.execute_script(
                "return arguments[0] ? arguments[0].scrollHeight : document.body.scrollHeight",
                container
            )
            if new_height > last_height:
                last_height = new_height
            # Pausa larga de "lectura" ocasional (6 %)
            if random.random() < 0.06:
                _human_pause(0.5, 1.5)

            cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='linkedin.com/in/']")
            if len(cards) == last_count and current_pos >= last_height:
                break
            last_count = len(cards)

        # Esperar carga bajo demanda
        time.sleep(random.uniform(1.2, 2.5))
        cards_now = driver.find_elements(By.CSS_SELECTOR, "a[href*='linkedin.com/in/']")
        if len(cards_now) == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_count = len(cards_now)

    _human_pause(0.5, 1.2)


def _collect_all_pages(driver: webdriver.Chrome, collected: set, max_pages: int = 20):
    """
    Recorre todas las páginas de resultados clicando 'Siguiente' / 'Next'.
    Acumula las URLs limpias en `collected`. Extrae solo del contenedor de la lista
    para no duplicar enlaces del menú.
    """
    list_container = None
    for page_num in range(1, max_pages + 1):
        _scroll_current_page(driver)
        list_container = _find_connections_list_container(driver) or list_container
        urls_page = _extract_profile_urls(driver, root=list_container)
        before = len(collected)
        collected.update(urls_page)
        new_this_page = len(collected) - before
        print(f"    página {page_num}: {len(urls_page)} tarjetas, {new_this_page} nuevas ({len(collected)} total)")

        if new_this_page == 0 and page_num > 1:
            print(f"    Misma lista que la página anterior; puede que no haya más páginas reales.")
            break

        next_btn = None
        for label in ["Siguiente", "Next", "See next", "Ver más", "See more", "Seguent", "Weiter"]:
            try:
                candidates = driver.find_elements(
                    By.XPATH,
                    f"//button[@aria-label='{label}'] | //a[@aria-label='{label}'] | "
                    f"//button[contains(@aria-label, '{label}')] | //a[contains(@aria-label, '{label}')]"
                )
                for btn in candidates:
                    if btn.is_displayed() and btn.is_enabled():
                        next_btn = btn
                        break
                if next_btn:
                    break
            except Exception:
                pass

        if not next_btn:
            try:
                for xpath in [
                    "//button[contains(normalize-space(), 'Siguiente') or contains(normalize-space(), 'Next') or contains(normalize-space(), 'Ver más')]",
                    "//a[contains(normalize-space(), 'Siguiente') or contains(normalize-space(), 'Next')]",
                    "//button[@type='button']//span[contains(text(), 'Next') or contains(text(), 'Siguiente')]",
                    "//li[contains(@class, 'pagination')]//button[not(@disabled)]",
                ]:
                    candidates = driver.find_elements(By.XPATH, xpath)
                    for btn in candidates:
                        if btn.is_displayed() and btn.is_enabled():
                            next_btn = btn
                            break
                    if next_btn:
                        break
            except Exception:
                pass

        if not next_btn:
            print(f"    No hay más páginas (total recogido: {len(collected)}).")
            break

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
        _human_pause(0.5, 1.0)
        driver.execute_script("arguments[0].click();", next_btn)
        time.sleep(random.uniform(3.0, 5.5))

        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/in/')]"))
            )
        except TimeoutException:
            break
        time.sleep(random.uniform(1.5, 3.0))


def _find_connections_list_container(driver: webdriver.Chrome):
    """Busca el contenedor que tiene la lista de conexiones (no el menú lateral)."""
    try:
        all_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='linkedin.com/in/'], a[href^='/in/']")
        if not all_links:
            return None
        for link in all_links:
            try:
                parent = link
                for _ in range(15):
                    parent = driver.execute_script("return arguments[0].parentElement;", parent)
                    if not parent:
                        break
                    child_links = parent.find_elements(By.CSS_SELECTOR, "a[href*='/in/']")
                    if len(child_links) >= 5:
                        return parent
            except Exception:
                continue
    except Exception:
        pass
    return None


def _extract_profile_urls(driver: webdriver.Chrome, root=None) -> list[str]:
    """Extrae y deduplica URLs de perfil. Si root está definido, solo busca dentro de root (lista de contactos)."""
    scope = root if root else driver
    elements = scope.find_elements(By.CSS_SELECTOR, "a[href*='linkedin.com/in/'], a[href^='/in/']")
    seen = set()
    urls = []
    for el in elements:
        href = el.get_attribute("href") or ""
        if href.startswith("/in/"):
            href = "https://www.linkedin.com" + href
        base = href.split("?")[0].rstrip("/")
        parts = base.split("/in/")
        if len(parts) != 2:
            continue
        slug = parts[1].strip("/")
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
    _human_pause(0.2, 0.5)
    driver.execute_script("arguments[0].click();", connection_link)
    print(f"  [connections] Enlace 'contactos' clicado")
    time.sleep(random.uniform(3.0, 5.0))

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/in/')]"))
        )
    except TimeoutException:
        print(f"  [connections] No cargaron resultados para {slug}")
        return []
    time.sleep(random.uniform(2.0, 4.0))

    collected = set()
    _collect_all_pages(driver, collected)
    urls = [u for u in collected if (u.rstrip("/").split("/")[-1] or "") != slug]
    print(f"  [connections] {len(urls)} conexiones encontradas para {slug}")
    return urls

