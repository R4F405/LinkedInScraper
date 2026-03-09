import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv

load_dotenv()


def create_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()

    if headless:
        options.add_argument("--headless")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver_path = ChromeDriverManager().install()
    # Bug conocido en webdriver-manager < 4.0.2: devuelve THIRD_PARTY_NOTICES.chromedriver en lugar del ejecutable
    if "THIRD_PARTY_NOTICES" in driver_path:
        driver_path = driver_path.replace("THIRD_PARTY_NOTICES.chromedriver", "chromedriver")
    # Por si acaso: si la ruta no es ejecutable, buscar "chromedriver" en la misma carpeta
    if os.path.isfile(driver_path) and not os.access(driver_path, os.X_OK):
        parent = os.path.dirname(driver_path)
        for name in ("chromedriver", "chromedriver.exe"):
            candidate = os.path.join(parent, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                driver_path = candidate
                break
    elif os.path.isdir(driver_path):
        for name in ("chromedriver", "chromedriver.exe"):
            candidate = os.path.join(driver_path, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                driver_path = candidate
                break

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def quit_driver(driver) -> None:
    if driver:
        driver.quit()