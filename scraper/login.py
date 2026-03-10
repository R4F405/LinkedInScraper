"""
scraper/login.py

Autentica en LinkedIn usando credenciales del .env.
"""

import re
import time
import random
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv

load_dotenv()

LINKEDIN_URL = "https://www.linkedin.com/login"
HOME_URL = "https://www.linkedin.com/feed"


def _type_like_human(element, text: str) -> None:
    """
    Escribe `text` carácter a carácter con velocidades humanas variables.
    Incluye pausas largas ocasionales (como quien piensa mientras teclea) y
    micro-errores de velocidad (rafagas rápidas seguidas de descansos).
    """
    for ch in text:
        element.send_keys(ch)
        # ~60-180 WPM depending on burst
        delay = random.gauss(0.10, 0.045)          # media 100 ms, σ 45 ms
        delay = max(0.03, min(delay, 0.45))         # clamp a [30 ms, 450 ms]
        time.sleep(delay)
        # 5 % de probabilidad de pausa larga "pensando"
        if random.random() < 0.05:
            time.sleep(random.uniform(0.4, 1.2))


def login(driver: webdriver.Chrome) -> bool:
    """
    Navega a LinkedIn e inicia sesión con las credenciales del .env.

    Returns:
        True si el login fue exitoso, False si falló.
    """
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")

    if not email or not password:
        raise ValueError("Faltan LINKEDIN_EMAIL o LINKEDIN_PASSWORD en el .env")

    driver.get(LINKEDIN_URL)

    try:
        wait = WebDriverWait(driver, 10)

        email_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        # Mover el ratón al campo antes de hacer clic (comportamiento humano)
        ActionChains(driver).move_to_element(email_field).pause(
            random.uniform(0.2, 0.6)
        ).click().perform()
        time.sleep(random.uniform(0.3, 0.8))
        _type_like_human(email_field, email)

        # Pausa natural entre campos
        time.sleep(random.uniform(0.5, 1.4))

        password_field = driver.find_element(By.ID, "password")
        ActionChains(driver).move_to_element(password_field).pause(
            random.uniform(0.2, 0.5)
        ).click().perform()
        time.sleep(random.uniform(0.2, 0.6))
        _type_like_human(password_field, password)

        # Pausa antes de enviar
        time.sleep(random.uniform(0.4, 1.0))
        driver.find_element(By.XPATH, '//button[@type="submit"]').click()

        # Verificar que llegamos al feed
        wait.until(EC.url_contains("/feed"))
        return True

    except TimeoutException:
        return False


def get_own_profile_url(driver: webdriver.Chrome) -> str:
    """
    Obtiene la URL del perfil del usuario que ha iniciado sesión.

    Estrategias en cascada (de más a menos fiable):
      1. Extrae publicProfileUrl / vanityName del JSON embebido en la página
         (LinkedIn siempre serializa los datos del usuario en el HTML).
      2. XPath: busca el enlace de nav "Yo" / "Me" por texto.
      3. Primeros enlaces /in/ del feed (sidebar izquierda = perfil propio).
      4. Navega a /in/me y espera la redirección + lee canonical.

    Returns:
        URL completa del perfil propio, p.ej. 'https://www.linkedin.com/in/mi-usuario/'
        o '' si ninguna estrategia funciona.
    """

    def _clean(url: str) -> str:
        return url.split("?")[0].rstrip("/") + "/"

    def _is_real(url: str) -> bool:
        c = _clean(url)
        if not c.startswith("https://www.linkedin.com/in/"):
            if not c.startswith("https://linkedin.com/in/"):
                return False
        slug = c.split("/in/", 1)[1].rstrip("/")
        return bool(slug) and slug != "me" and "/" not in slug

    def _from_source(source: str) -> str:
        """Extrae la URL del perfil desde el JSON embebido por LinkedIn."""
        # Buscar publicProfileUrl completo
        m = re.search(
            r'"publicProfileUrl"\s*:\s*"(https://www\.linkedin\.com/in/[^"?/]+/?)"',
            source,
        )
        if m:
            url = _clean(m.group(1))
            if _is_real(url):
                return url
        # Buscar vanityName (slug del perfil)
        m = re.search(r'"vanityName"\s*:\s*"([a-zA-Z0-9_%\-]+)"', source)
        if m:
            url = f"https://www.linkedin.com/in/{m.group(1)}/"
            if _is_real(url):
                return url
        return ""

    # Asegurar que estamos en el feed antes de empezar
    try:
        if "/feed" not in driver.current_url:
            driver.get("https://www.linkedin.com/feed/")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)
    except Exception:
        pass

    # ── Estrategia 1: JSON embebido en el feed ────────────────────────────
    try:
        result = _from_source(driver.page_source)
        if result:
            return result
    except Exception:
        pass

    # ── Estrategia 2: enlace de nav "Yo" / "Me" por texto ────────────────
    try:
        for label in ["Yo", "Me"]:
            els = driver.find_elements(
                By.XPATH,
                f"//a[@href and (.//span[normalize-space()='{label}']"
                f" or normalize-space(.)='{label}')]",
            )
            for el in els:
                href = el.get_attribute("href") or ""
                if _is_real(href):
                    return _clean(href)
    except Exception:
        pass

    # ── Estrategia 3: primeros enlaces /in/ del feed (sidebar izquierda) ─
    try:
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/in/']")
        for link in links[:15]:
            href = link.get_attribute("href") or ""
            if _is_real(href):
                return _clean(href)
    except Exception:
        pass

    # ── Estrategia 4: /in/me con espera larga + canonical ────────────────
    try:
        driver.get("https://www.linkedin.com/in/me")
        time.sleep(5)
        url = driver.current_url
        if _is_real(url):
            return _clean(url)
        # canonical
        try:
            c = driver.find_element(By.CSS_SELECTOR, "link[rel='canonical']")
            href = c.get_attribute("href") or ""
            if _is_real(href):
                return _clean(href)
        except Exception:
            pass
        # JSON embebido en la página /in/me
        result = _from_source(driver.page_source)
        if result:
            return result
        driver.get("https://www.linkedin.com/feed/")
    except Exception:
        pass

    return ""