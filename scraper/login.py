"""
scraper/login.py

Autentica en LinkedIn usando credenciales del .env.
"""

import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv

load_dotenv()

LINKEDIN_URL = "https://www.linkedin.com/login"
HOME_URL = "https://www.linkedin.com/feed"


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
        email_field.send_keys(email)

        password_field = driver.find_element(By.ID, "password")
        password_field.send_keys(password)

        driver.find_element(By.XPATH, '//button[@type="submit"]').click()

        # Verificar que llegamos al feed
        wait.until(EC.url_contains("/feed"))
        return True

    except TimeoutException:
        return False


def get_own_profile_url(driver: webdriver.Chrome) -> str:
    """
    Obtiene la URL del perfil del usuario que ha iniciado sesión.
    Prueba tres estrategias en cascada:
      1. Enlace al perfil propio en la barra de navegación (más fiable).
      2. Navegar a /in/me y capturar la redirección.
      3. Enlace en el panel lateral del feed.

    Returns:
        URL completa del perfil propio, p.ej. 'https://www.linkedin.com/in/mi-usuario/'
        o '' si no se pudo resolver.
    """
    def _clean(url: str) -> str:
        return url.split("?")[0].rstrip("/") + "/"

    def _is_real_profile(url: str) -> bool:
        cleaned = _clean(url)
        return (
            "/in/" in cleaned
            and cleaned != "https://www.linkedin.com/in/me/"
            and "linkedin.com/in/" in cleaned
        )

    # ── Estrategia 1: nav bar ──────────────────────────────────────────────
    # Después del login estamos en el feed. La barra de nav contiene
    # un enlace con href="/in/<slug>" o "linkedin.com/in/<slug>" bajo el
    # botón "Yo" / "Me".
    try:
        nav_selectors = [
            "a[href*='/in/'][data-control-name='identity_welcome_message']",
            "a.ember-view[href*='/in/']",
            "nav a[href*='/in/']",
            "a[data-test-app-aware-link][href*='/in/']",
        ]
        for sel in nav_selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                href = el.get_attribute("href") or ""
                if _is_real_profile(href):
                    return _clean(href)
    except Exception:
        pass

    # ── Estrategia 2: /in/me redirect ─────────────────────────────────────
    try:
        current_page = driver.current_url  # guardamos para volver si falla
        driver.get("https://www.linkedin.com/in/me")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
        )
        url = driver.current_url
        if _is_real_profile(url):
            return _clean(url)
        # Si no redirigió, intentar leer el canonical desde el HTML
        try:
            canonical = driver.find_element(By.CSS_SELECTOR, "link[rel='canonical']")
            href = canonical.get_attribute("href") or ""
            if _is_real_profile(href):
                return _clean(href)
        except Exception:
            pass
        # Volver al feed para no dejar el driver en estado raro
        driver.get("https://www.linkedin.com/feed")
    except TimeoutException:
        pass

    # ── Estrategia 3: panel lateral del feed ──────────────────────────────
    try:
        driver.get("https://www.linkedin.com/feed")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/in/']"))
        )
        els = driver.find_elements(By.CSS_SELECTOR, "a[href*='/in/']")
        for el in els:
            href = el.get_attribute("href") or ""
            if _is_real_profile(href):
                return _clean(href)
    except Exception:
        pass

    return ""