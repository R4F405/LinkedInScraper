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