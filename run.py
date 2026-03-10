"""
run.py — Orquestador principal.

Opciones disponibles al ejecutar:
  [1] Scraping de conexiones de un perfil concreto (URL manual)
  [2] Scraping de las conexiones del perfil propio del usuario que inicia sesión
  [3] Scraping profundo: conexiones del usuario propio + contactos de cada contacto

Uso:
    python run.py

Nota para integración con GUI:
    La función `choose_mode(driver, own_url)` devuelve un dict con:
        {
            "mode":      1 | 2 | 3,
            "own_url":   str,          # URL del perfil propio (puede ser "")
            "seed_urls": list[str],    # URLs semilla introducidas por el usuario
        }
    Reemplaza esa función con la lógica equivalente de la GUI.
"""

import random
import time

from scraper.driver import create_driver, quit_driver
from scraper.login import login, get_own_profile_url
from scraper.connection_fetcher import get_connections
from scraper.profile_fetcher import fetch_profile
from parser.profile_parser import parse_profile_file
from exporter.export import export_results
from utils.config import RAW_HTML_DIR

# Pausa anti-bot: cada N perfiles scrapeados, descanso largo
_BREAK_EVERY = 300
_BREAK_MIN_S = 15 * 60   # 15 min
_BREAK_MAX_S = 35 * 60   # 35 min


# ---------------------------------------------------------------------------
# Utilidades compartidas
# ---------------------------------------------------------------------------

def _scrape_batch(driver, urls: list[str], already_scraped: set, counter: list) -> list:
    """
    Scrapea una lista de URLs de perfil aplicando la pausa anti-bot cada
    _BREAK_EVERY perfiles. Devuelve los Path guardados.
    Modifica `counter[0]` (int mutable vía lista) y `already_scraped` (set).
    """
    saved = []
    for url in urls:
        if url in already_scraped:
            continue
        already_scraped.add(url)
        try:
            path = fetch_profile(driver, url)
            saved.append(path)
            counter[0] += 1
            print(f"  [scraper] #{counter[0]:>4} guardado → {path.name}")

            if counter[0] % _BREAK_EVERY == 0:
                minutes = random.uniform(_BREAK_MIN_S, _BREAK_MAX_S) / 60
                secs = minutes * 60
                print(f"\n  ☕  Pausa anti-bot tras {counter[0]} perfiles "
                      f"({minutes:.0f} min)… reanudaremos a las "
                      f"{time.strftime('%H:%M', time.localtime(time.time() + secs))}")
                time.sleep(secs)
                print("  ▶  Reanudando scraping…\n")
        except Exception as e:
            print(f"  [scraper] ERROR en {url}: {e}")
    return saved


# ---------------------------------------------------------------------------
# Punto de entrada de datos  ← LA GUI REEMPLAZA SOLO ESTA FUNCIÓN
# ---------------------------------------------------------------------------

def choose_mode(driver, own_url: str) -> dict:
    """
    Muestra el menú de opciones y devuelve un dict con:
        mode      : 1, 2 o 3
        own_url   : URL propia detectada (o "")
        seed_urls : lista de URLs que el usuario introdujo manualmente (solo modo 1)

    Para integrar con GUI: reemplaza esta función.
    """
    print("\n¿Qué quieres hacer?")
    if own_url:
        print(f"  [1] Scrapear conexiones de mi perfil          ({own_url})")
    else:
        print( "  [1] Scrapear conexiones de un perfil concreto (introducir URL)")
    print(  "  [2] Introducir URLs de perfil manualmente")
    print(  "  [3] Scraping profundo: mis contactos + contactos de cada contacto")

    choice = input("\n  Elige opción (1/2/3): ").strip()

    if choice == "3":
        if not own_url:
            print("  ⚠  No se detectó el perfil propio. Introduce tu URL:")
            own_url = _ask_single_url()
        return {"mode": 3, "own_url": own_url, "seed_urls": []}

    if choice == "1" and own_url:
        return {"mode": 1, "own_url": own_url, "seed_urls": [own_url]}

    # Modo 2 o modo 1 sin own_url detectado
    seed_urls = _ask_urls()
    return {"mode": 1, "own_url": own_url, "seed_urls": seed_urls}


def _ask_single_url() -> str:
    while True:
        raw = input("  URL del perfil: ").strip()
        if "linkedin.com/in/" in raw:
            return _normalize(raw)
        print("  ⚠  No parece una URL de LinkedIn (/in/).")


def _ask_urls() -> list[str]:
    print("\nIntroduce las URLs de perfil (Enter vacío para terminar):")
    urls: list[str] = []
    while True:
        raw = input(f"  URL {len(urls) + 1}: ").strip()
        if not raw:
            break
        if "linkedin.com/in/" not in raw:
            print("  ⚠  No parece una URL de LinkedIn (/in/). Inténtalo de nuevo.")
            continue
        urls.append(_normalize(raw))
        print(f"  ✓ Añadido: {urls[-1]}")
    return urls


def _normalize(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    return url.rstrip("/") + "/"


# ---------------------------------------------------------------------------
# Modos de ejecución
# ---------------------------------------------------------------------------

def run_mode_1_2(driver, seed_urls: list[str]) -> list:
    """Scrapea las conexiones de cada URL semilla (comportamiento original)."""
    print("\n── Obteniendo conexiones ──────────────────────")
    all_urls: list[str] = []
    for seed in seed_urls:
        conns = get_connections(driver, seed)
        all_urls.extend(conns)
    all_urls = list(dict.fromkeys(all_urls))
    print(f"Total conexiones únicas: {len(all_urls)}")
    if not all_urls:
        print("No se encontraron conexiones.")
        return []

    print("\n── Scraping perfiles ──────────────────────────")
    counter = [0]
    saved = _scrape_batch(driver, all_urls, set(), counter)
    return saved


def run_mode_3(driver, own_url: str) -> list:
    """
    Scraping profundo:
      1. Obtiene todas las conexiones directas del usuario (nivel 1).
      2. Por cada contacto de nivel 1:
           a. Scrapea su propio perfil.
           b. Obtiene TODAS sus conexiones (nivel 2) y las scrapea también.
    """
    print("\n── [Modo 3] Obteniendo tus conexiones directas ─")
    level1_urls = get_connections(driver, own_url)
    level1_urls = list(dict.fromkeys(level1_urls))
    print(f"  Contactos directos encontrados: {len(level1_urls)}")
    if not level1_urls:
        print("  No se encontraron conexiones directas.")
        return []

    all_saved: list = []
    already_scraped: set = set()
    counter = [0]

    for idx, contact_url in enumerate(level1_urls, 1):
        print(f"\n── Contacto {idx}/{len(level1_urls)}: {contact_url}")

        # a) Scrapear el perfil del contacto directo
        saved_lvl1 = _scrape_batch(driver, [contact_url], already_scraped, counter)
        all_saved.extend(saved_lvl1)

        # b) Obtener y scrapear sus conexiones (nivel 2)
        print(f"  Obteniendo conexiones de {contact_url} …")
        try:
            level2_urls = get_connections(driver, contact_url)
            level2_urls = list(dict.fromkeys(level2_urls))
            print(f"  → {len(level2_urls)} conexiones de nivel 2")
            saved_lvl2 = _scrape_batch(driver, level2_urls, already_scraped, counter)
            all_saved.extend(saved_lvl2)
        except Exception as e:
            print(f"  ⚠  Error obteniendo conexiones de {contact_url}: {e}")

    return all_saved


# ---------------------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    driver = create_driver(headless=False)
    saved_paths = []
    try:
        print("\n── Login ───────────────────────────────────────")
        if not login(driver):
            print("ERROR: el login falló. Revisa el .env.")
            raise SystemExit(1)
        print("Login correcto ✓")

        print("  Detectando perfil propio…")
        own_url = get_own_profile_url(driver)
        if own_url:
            print(f"  Perfil propio: {own_url}")
        else:
            print("  (No se pudo detectar automáticamente)")

        config = choose_mode(driver, own_url)

        if config["mode"] == 3:
            saved_paths = run_mode_3(driver, config["own_url"])
        else:
            if not config["seed_urls"]:
                print("No se introdujo ninguna URL. Saliendo.")
                raise SystemExit(1)
            saved_paths = run_mode_1_2(driver, config["seed_urls"])

    finally:
        quit_driver(driver)

    if not saved_paths:
        print("No se descargó ningún perfil.")
        raise SystemExit(1)

    print("\n── Parseando HTML ──────────────────────────────")
    records = [parse_profile_file(p) for p in saved_paths]
    print(f"  {len(records)} perfiles parseados")

    for r in records:
        print(f"  · {r['name']:30s} | {r['company']:25s} | {r['location']}")

    print("\n── Exportando resultados ───────────────────────")
    paths = export_results(records, fmt="both")
    for p in paths:
        print(f"  → {p}")
