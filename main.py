"""
main.py

Punto de entrada del scraper.
Ejecutar: python main.py
"""

from scraper.driver import create_driver, quit_driver
from scraper.login import login
from scraper.profile_fetcher import fetch_all_profiles
from parser.profile_parser import parse_all_profiles
from exporter.export import export_results
from utils.config import RAW_HTML_DIR

# Lista de perfiles a scrapear
PROFILE_URLS = [
    "https://www.linkedin.com/in/ejemplo-perfil-1/",
    "https://www.linkedin.com/in/ejemplo-perfil-2/",
]


def main():
    driver = create_driver(headless=False)

    try:
        print("🔐 Iniciando sesión...")
        if not login(driver):
            print("❌ Login fallido. Revisa las credenciales en .env")
            return

        print("✅ Login exitoso.")

        print(f"📥 Descargando {len(PROFILE_URLS)} perfiles...")
        fetch_all_profiles(driver, PROFILE_URLS)

        print("🔍 Parseando HTMLs...")
        records = parse_all_profiles(RAW_HTML_DIR)

        if not records:
            print("⚠️  No se encontraron perfiles en data/raw/")
            return

        print(f"📤 Exportando {len(records)} registros...")
        paths = export_results(records)

        print("✅ Hecho. Archivos generados:")
        for p in paths:
            print(f"   {p}")

    finally:
        quit_driver(driver)


if __name__ == "__main__":
    main()