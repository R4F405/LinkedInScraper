"""
run.py — Orquestador principal.

Flujo completo:
  1. Pide al usuario la URL de perfil de LinkedIn por terminal
     (o detecta automáticamente el perfil del usuario que inicia sesión)
  2. Abre Chrome, inicia sesión en LinkedIn
  3. Por cada URL semilla, entra al perfil y obtiene todas sus conexiones
  4. Navega cada perfil de conexión y guarda el HTML + contacto en data/raw/
  5. Parsea los HTML
  6. Exporta CSV + Excel a data/output/

Uso:
    python run.py

Nota para integración con GUI:
    Sustituye la función `get_seed_urls()` por la que proporcione la interfaz
    gráfica. El resto del flujo no cambia.
"""

from pathlib import Path

from scraper.driver import create_driver, quit_driver
from scraper.login import login, get_own_profile_url
from scraper.connection_fetcher import get_connections
from scraper.profile_fetcher import fetch_all_profiles
from exporter.export import export_results


# ---------------------------------------------------------------------------
# Punto de entrada de datos  ← LA GUI REEMPLAZA SOLO ESTA FUNCIÓN
# ---------------------------------------------------------------------------

def get_seed_urls(driver=None) -> list[str]:
    """
    Pregunta al usuario si quiere usar su propio perfil (detectado
    automáticamente tras el login) o introducir URLs manualmente.

    Parámetro `driver`: si se pasa (ya autenticado), se intenta
    detectar el perfil propio. Si es None, solo se ofrece la entrada manual.

    Para integrar con GUI: reemplaza esta función por otra que devuelva
    la misma list[str] obtenida desde la interfaz gráfica.
    """
    own_url = ""
    if driver is not None:
        own_url = get_own_profile_url(driver)

    print("\n¿De qué perfiles quieres obtener las conexiones?")
    if own_url:
        print(f"  [1] Mi propio perfil (detectado: {own_url})")
        print("  [2] Introducir URLs manualmente")
        choice = input("  Elige opción (1/2): ").strip()
        if choice != "2":
            print(f"  ✓ Usando perfil propio: {own_url}")
            return [own_url]

    # Entrada manual
    print("\nIntroduce las URLs de perfil de LinkedIn a scrapear.")
    print("  · Formato esperado: https://www.linkedin.com/in/<usuario>/")
    print("  · Pulsa Enter sin escribir nada para terminar.\n")

    urls: list[str] = []
    while True:
        raw = input(f"  URL {len(urls) + 1} (o Enter para continuar): ").strip()
        if not raw:
            break
        if "linkedin.com/in/" not in raw:
            print("    ⚠  No parece una URL de perfil de LinkedIn (/in/). Inténtalo de nuevo.")
            continue
        if not raw.startswith("http"):
            raw = "https://" + raw
        if not raw.endswith("/"):
            raw += "/"
        urls.append(raw)
        print(f"    ✓ Añadido: {raw}")

    return urls


# ---------------------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    driver = create_driver(headless=False)
    try:
        print("\n── Login ──────────────────────────────")
        ok = login(driver)
        if not ok:
            print("ERROR: el login falló. Revisa el .env y vuelve a intentarlo.")
            raise SystemExit(1)
        print("Login correcto ✓")

        # Pedir URLs DESPUÉS del login para poder detectar el perfil propio
        seed_urls = get_seed_urls(driver)
        if not seed_urls:
            print("No se introdujo ninguna URL. Saliendo.")
            raise SystemExit(1)

        print("\n── Obteniendo conexiones ──────────────")
        all_connection_urls: list[str] = []
        for seed in seed_urls:
            connections = get_connections(driver, seed)
            all_connection_urls.extend(connections)

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
