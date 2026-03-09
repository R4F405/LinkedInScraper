"""
run.py — Orquestador principal.

Flujo completo:
  1. Lee las URLs semilla de profiles.txt
  2. Abre Chrome, inicia sesión en LinkedIn
  3. Por cada URL semilla, obtiene todas sus conexiones
  4. Navega cada perfil de conexión y guarda el HTML + email en data/raw/
  5. Parsea los HTML
  6. Exporta CSV + Excel a data/output/

Uso:
    python run.py
"""

from pathlib import Path

from scraper.driver import create_driver, quit_driver
from scraper.login import login
from scraper.connection_fetcher import get_connections
from scraper.profile_fetcher import fetch_all_profiles
from exporter.export import export_results

PROFILES_FILE = Path("profiles.txt")


def load_urls() -> list[str]:
    if not PROFILES_FILE.exists():
        print(f"ERROR: no existe '{PROFILES_FILE}'.")
        print("Crea el archivo con una URL de LinkedIn por línea.")
        return []
    urls = [
        line.strip()
        for line in PROFILES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    print(f"Perfiles semilla: {len(urls)}")
    return urls


if __name__ == "__main__":
    seed_urls = load_urls()
    if not seed_urls:
        raise SystemExit(1)

    driver = create_driver(headless=False)
    try:
        print("\n── Login ──────────────────────────────")
        ok = login(driver)
        if not ok:
            print("ERROR: el login falló. Revisa el .env y vuelve a intentarlo.")
            raise SystemExit(1)
        print("Login correcto ✓")

        print("\n── Obteniendo conexiones ──────────────")
        all_connection_urls: list[str] = []
        for seed in seed_urls:
            connections = get_connections(driver, seed)
            all_connection_urls.extend(connections)

        # Deduplicar por si varios semillas comparten conexiones
        all_connection_urls = list(dict.fromkeys(all_connection_urls))
        print(f"Total conexiones únicas a scrapear: {len(all_connection_urls)}")

        if not all_connection_urls:
            print("No se encontraron conexiones. Revisa que el perfil tenga conexiones visibles.")
            raise SystemExit(1)

        print("\n── Scraping perfiles ──────────────────")
        saved_paths = fetch_all_profiles(driver, all_connection_urls)

    finally:
        quit_driver(driver)

    print("\n── Parseando HTML ─────────────────────")
    from parser.profile_parser import parse_profile_file
    records = [parse_profile_file(p) for p in saved_paths]
    if not records:
        print("No se descargó ningún perfil.")
        raise SystemExit(1)

    for r in records:
        print(f"  · {r['name']:30s} | {r['company']:25s} | {r['location']}")

    print("\n── Exportando resultados ──────────────")
    paths = export_results(records, fmt="both")
    for p in paths:
        print(f"  → {p}")
