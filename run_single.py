"""
run_single.py — Ejecuta el scraping de una sola URL de perfil de LinkedIn.

Uso (desde la raíz del proyecto):
    python run_single.py "https://www.linkedin.com/in/nombre-perfil/"

Pensado para ser invocado por la app web (subprocess). Hace login, descarga
el perfil, parsea y exporta a data/output/.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scraper.driver import create_driver, quit_driver
from scraper.login import login
from scraper.profile_fetcher import fetch_all_profiles
from parser.profile_parser import parse_profile_file
from exporter.export import export_results


def main():
    if len(sys.argv) < 2:
        print("Uso: python run_single.py <url_perfil_linkedin>")
        sys.exit(1)
    url = sys.argv[1].strip()
    if not url.startswith("http") or "linkedin.com/in/" not in url:
        print("URL inválida. Debe ser un perfil de LinkedIn.")
        sys.exit(1)

    driver = create_driver(headless=False)
    try:
        if not login(driver):
            print("ERROR: login fallido.")
            sys.exit(1)
        saved_paths = fetch_all_profiles(driver, [url])
    finally:
        quit_driver(driver)

    if not saved_paths:
        print("No se guardó ningún perfil.")
        sys.exit(1)

    records = [parse_profile_file(p) for p in saved_paths]
    export_results(records, fmt="both")
    print("OK")


if __name__ == "__main__":
    main()
