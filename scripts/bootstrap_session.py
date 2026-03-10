"""
scripts/bootstrap_session.py

Genera una sesión válida de LinkedIn abriendo Chrome EN MODO VISIBLE
para que puedas resolver manualmente el CAPTCHA o la verificación.

USO (ejecutar en local, NO dentro de Docker):
    python scripts/bootstrap_session.py

Una vez finalizado, las cookies quedan guardadas en:
    data/sessions/linkedin_session.pkl

Después puedes arrancar Docker y reutilizará esa sesión:
    docker compose down && docker compose up -d
"""

import sys
import os

# Añadir el directorio raíz al path para poder importar los módulos del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.driver import create_driver, quit_driver
from scraper.login import login
from utils.config import SESSION_DIR


def main():
    print("=" * 55)
    print("  Bootstrap de sesión LinkedIn")
    print("=" * 55)
    print()
    print("Se abrirá Chrome en modo VISIBLE.")
    print("Si LinkedIn pide verificación o CAPTCHA, resuélvelo")
    print("manualmente en el navegador. El script esperará.")
    print()

    # Forzar headless=False para que se vea el navegador
    os.environ["SCRAPER_HEADLESS"] = "false"

    driver = create_driver(headless=False)

    try:
        success = login(driver, force_fresh=True)

        if success:
            print()
            print("=" * 55)
            print("  ✓ Sesión guardada correctamente en:")
            print(f"    {SESSION_DIR / 'linkedin_session.pkl'}")
            print()
            print("  Ahora puedes arrancar Docker:")
            print("    docker compose down && docker compose up -d")
            print("=" * 55)
        else:
            print()
            print("=" * 55)
            print("  ✗ El login falló. Revisa las credenciales en .env")
            print("=" * 55)
            sys.exit(1)

    finally:
        quit_driver(driver)


if __name__ == "__main__":
    main()
