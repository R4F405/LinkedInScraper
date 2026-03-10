"""
scraper/login.py

Autentica en LinkedIn usando credenciales del .env.
Soporte de sesiones persistentes: guarda cookies tras login exitoso
y las reutiliza en ejecuciones posteriores para evitar logins repetidos.
"""

import re
import time
import random
import os
import pickle
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from dotenv import load_dotenv

from utils.config import SESSION_DIR

load_dotenv()

LINKEDIN_URL = "https://www.linkedin.com/login"
HOME_URL = "https://www.linkedin.com/feed"
LOGIN_MAX_WAIT_S = 45
COOKIES_FILE = SESSION_DIR / "linkedin_session.pkl"


def _wait_for_login_success(driver: webdriver.Chrome, max_wait_s: int = LOGIN_MAX_WAIT_S) -> bool:
    """
    Espera hasta `max_wait_s` segundos para permitir resolver CAPTCHA/manual checks
    antes de dar el login por fallido.
    """
    print(f"  Esperando verificación de login/CAPTCHA (hasta {max_wait_s}s)...")
    end_time = time.time() + max_wait_s

    while time.time() < end_time:
        current = driver.current_url.lower()

        # LinkedIn suele llevar al feed, y a veces al checkpoint de seguridad
        # antes de redirigir al feed.
        if "/feed" in current:
            return True
        if "/checkpoint" in current or "captcha" in current or "challenge" in current:
            time.sleep(2)
            continue

        # Fallback DOM: detectar elementos comunes de sesión iniciada.
        try:
            driver.find_element(By.CSS_SELECTOR, "a[href*='/mynetwork/'], a[href*='/feed/']")
            return True
        except Exception:
            pass

        time.sleep(1.5)

    return False


def _save_cookies(driver: webdriver.Chrome) -> None:
    """Guarda las cookies de la sesión actual en disco."""
    try:
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print(f"  ✓ Cookies guardadas en {COOKIES_FILE.name}")
    except Exception as e:
        print(f"  ⚠ No se pudieron guardar cookies: {e}")


def _load_cookies(driver: webdriver.Chrome) -> bool:
    """
    Carga cookies guardadas previamente.
    Returns True si existían y se cargaron, False si no.
    """
    if not COOKIES_FILE.exists():
        return False
    try:
        driver.get("https://www.linkedin.com")  # Navegar primero al dominio
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
        for cookie in cookies:
            # Selenium 4+ requiere que 'sameSite' sea válido o None
            if 'sameSite' in cookie and cookie['sameSite'] not in ['Strict', 'Lax', 'None']:
                cookie['sameSite'] = 'None'
            driver.add_cookie(cookie)
        return True
    except Exception as e:
        print(f"  ⚠ Error cargando cookies: {e}")
        # Eliminar archivo corrupto
        try:
            COOKIES_FILE.unlink()
        except:
            pass
        return False


def _check_session_active(driver: webdriver.Chrome) -> bool:
    """
    Verifica si la sesión actual es válida navegando al feed.
    Returns True si está logueado, False si no.
    """
    try:
        driver.get(HOME_URL)
        time.sleep(random.uniform(0.8, 1.5))
        current = driver.current_url.lower()
        # Si nos redirige a login o checkpoint, la sesión no es válida
        if "/login" in current or "/uas/login" in current:
            return False
        # Verificar presencia de elementos del feed
        try:
            driver.find_element(By.CSS_SELECTOR, "a[href*='/mynetwork/'], a[href*='/feed/']")
            return True
        except:
            return False
    except Exception:
        return False


def _type_like_human(element, text: str) -> None:
    """
    Escribe `text` carácter a carácter con velocidades humanas variables.
    Incluye pausas largas ocasionales (como quien piensa mientras teclea) y
    micro-errores de velocidad (rafagas rápidas seguidas de descansos).
    """
    for ch in text:
        element.send_keys(ch)
        # Velocidad rápida pero variable
        delay = random.gauss(0.05, 0.025)          # media 50 ms, σ 25 ms
        delay = max(0.02, min(delay, 0.15))         # clamp a [20 ms, 150 ms]
        time.sleep(delay)
        # 3 % de probabilidad de pausa breve
        if random.random() < 0.03:
            time.sleep(random.uniform(0.2, 0.5))


def login(driver: webdriver.Chrome, force_fresh: bool = False) -> bool:
    """
    Inicia sesión en LinkedIn. Primero intenta restaurar sesión guardada.
    Si no existe o ha expirado, hace login con credenciales.

    Args:
        driver: Instancia de Chrome WebDriver
        force_fresh: Si True, ignora cookies guardadas y fuerza login fresco

    Returns:
        True si el login fue exitoso, False si falló.
    """
    email = os.getenv("LINKEDIN_EMAIL")
    password = os.getenv("LINKEDIN_PASSWORD")

    if not email or not password:
        raise ValueError("Faltan LINKEDIN_EMAIL o LINKEDIN_PASSWORD en el .env")

    # Intentar restaurar sesión si no se fuerza login fresco
    if not force_fresh:
        print("  Intentando restaurar sesión guardada...")
        if _load_cookies(driver):
            print("  Cookies cargadas, verificando sesión...")
            if _check_session_active(driver):
                print("  ✓ Sesión restaurada correctamente (sin login)")
                return True
            else:
                print("  ✗ Sesión expirada, procediendo con login...")
        else:
            print("  No hay sesión guardada, procediendo con login...")

    # Login fresco
    driver.get(LINKEDIN_URL)

    try:
        wait = WebDriverWait(driver, 20)

        email_field = wait.until(EC.presence_of_element_located((By.ID, "username")))
        # Mover el ratón al campo antes de hacer clic (comportamiento humano)
        ActionChains(driver).move_to_element(email_field).pause(
            random.uniform(0.1, 0.3)
        ).click().perform()
        time.sleep(random.uniform(0.1, 0.3))
        _type_like_human(email_field, email)

        # Pausa natural entre campos
        time.sleep(random.uniform(0.2, 0.6))

        password_field = driver.find_element(By.ID, "password")
        ActionChains(driver).move_to_element(password_field).pause(
            random.uniform(0.1, 0.3)
        ).click().perform()
        time.sleep(random.uniform(0.1, 0.3))
        _type_like_human(password_field, password)

        # Pausa antes de enviar
        time.sleep(random.uniform(0.2, 0.5))
        driver.find_element(By.XPATH, '//button[@type="submit"]').click()

        # Dar ventana amplia para resolver CAPTCHA/manual check si aparece.
        login_success = _wait_for_login_success(driver)
        
        # Si el login fue exitoso, guardar cookies para próximas ejecuciones
        if login_success:
            _save_cookies(driver)
        
        return login_success

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