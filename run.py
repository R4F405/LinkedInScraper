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
import os

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
_MAX_CONNECTIONS_PER_FETCH = 10  # Límite temporal para acelerar pruebas
_OWN_CONNECTIONS_URL = "https://www.linkedin.com/mynetwork/invite-connect/connections/"


class CancelToMenu(Exception):
    """Señal de cancelación para volver al menú principal."""


def _is_usable_record(record: dict) -> bool:
    """Filtra filas vacías o de páginas intersticiales (captcha/verificación)."""
    name = (record.get("name") or "").strip().lower()
    email = (record.get("email") or "").strip()
    location = (record.get("location") or "").strip()
    company = (record.get("company") or "").strip()

    blocked = (
        "verificacion de seguridad",
        "verificación de seguridad",
        "iniciar sesion para ver el perfil completo",
        "iniciar sesión para ver el perfil completo",
        "sign in to view full profile",
        "iniciar sesion",
        "iniciar sesión",
        "hola de nuevo",
        "encuentra el empleo",
        "sitios web",
        "join now",
        "sign in",
    )
    if any(b in name for b in blocked):
        return False

    # Datos de empresa obviamente basura (solo dígitos) se tratan como vacíos
    if company.isdigit():
        company = ""

    # Si solo hay nombre pero no hay más señal útil, se descarta
    if name and not (email or location or company):
        return False

    # Si no tiene ningún dato útil, no se exporta
    return bool(name or email or location or company)


def _prompt_cancel(context: str) -> None:
    """
    Checkpoint interactivo para permitir cancelar y volver al menú.
    - Enter: continuar
    - c: cancelar ejecución actual y volver al menú
    """
    ans = input(f"  [{context}] Enter=seguir | c=volver al menú: ").strip().lower()
    if ans == "c":
        raise CancelToMenu()


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
    print(  "  [q] Salir")

    choice = input("\n  Elige opción (1/2/3/q): ").strip().lower()

    if choice == "q":
        return {"mode": 0, "own_url": own_url, "seed_urls": []}

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
    print("  (Escribe 'q' para volver al menú principal)")
    urls: list[str] = []
    while True:
        raw = input(f"  URL {len(urls) + 1}: ").strip()
        if not raw:
            break
        if raw.lower() == "q":
            return []
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

def run_mode_1_2(driver, seed_urls: list[str], own_url: str = "") -> tuple[list, str]:
    """
    Scrapea las conexiones de cada URL semilla (comportamiento original).
    Returns: (saved_paths, owner_slug) donde owner_slug es el slug del primer seed.
    """
    print("\n── Scraping perfiles semilla ──────────────────")
    counter = [0]
    already_scraped = set()
    
    # Primero scrapear el perfil del owner (primera seed) para tener su nombre
    owner_slug = seed_urls[0].rstrip("/").split("/")[-1] if seed_urls else ""
    saved = _scrape_batch(driver, [seed_urls[0]], already_scraped, counter) if seed_urls else []
    
    print("\n── Obteniendo conexiones ──────────────────────")
    all_urls: list[str] = []
    for seed in seed_urls:
        conns = get_connections(driver, seed, max_connections=_MAX_CONNECTIONS_PER_FETCH)
        # Fallback para perfil propio: algunos perfiles no muestran el enlace
        # de contactos en la top-card, pero sí en la sección de red propia.
        if not conns and own_url and _normalize(seed) == _normalize(own_url):
            print("  [connections] Fallback a lista de conexiones propia…")
            conns = get_connections(driver, _OWN_CONNECTIONS_URL, max_connections=_MAX_CONNECTIONS_PER_FETCH)
        all_urls.extend(conns)
    all_urls = list(dict.fromkeys(all_urls))
    print(f"Total conexiones únicas: {len(all_urls)}")
    if not all_urls:
        print("No se encontraron conexiones.")
        return (saved, owner_slug)

    print("\n── Scraping perfiles ──────────────────────────")
    saved.extend(_scrape_batch(driver, all_urls, already_scraped, counter))
    return (saved, owner_slug)


def run_mode_3(driver, own_url: str) -> tuple[list, str]:
    """
    Scraping profundo:
      1. Scrapea el perfil del usuario propio primero.
      2. Obtiene todas las conexiones directas del usuario (nivel 1).
      3. Por cada contacto de nivel 1:
           a. Scrapea su propio perfil.
           b. Obtiene TODAS sus conexiones (nivel 2) y las scrapea también.
    
    Returns: (saved_paths, owner_slug)
    """
    owner_slug = own_url.rstrip("/").split("/")[-1]
    all_saved: list = []
    already_scraped: set = set()
    counter = [0]
    
    # Primero scrapear el perfil propio del owner
    print("\n── Scraping perfil propio ─────────────────────")
    saved_owner = _scrape_batch(driver, [own_url], already_scraped, counter)
    all_saved.extend(saved_owner)
    
    print("\n── [Modo 3] Obteniendo tus conexiones directas ─")
    level1_urls = get_connections(driver, own_url, max_connections=_MAX_CONNECTIONS_PER_FETCH)
    level1_urls = list(dict.fromkeys(level1_urls))
    print(f"  Contactos directos encontrados: {len(level1_urls)}")
    if not level1_urls:
        print("  No se encontraron conexiones directas.")
        return (all_saved, owner_slug)

    for idx, contact_url in enumerate(level1_urls, 1):
        print(f"\n── Contacto {idx}/{len(level1_urls)}: {contact_url}")
        _prompt_cancel(f"contacto {idx}/{len(level1_urls)}")

        # a) Scrapear el perfil del contacto directo
        saved_lvl1 = _scrape_batch(driver, [contact_url], already_scraped, counter)
        all_saved.extend(saved_lvl1)

        # b) Obtener y scrapear sus conexiones (nivel 2)
        print(f"  Obteniendo conexiones de {contact_url} …")
        try:
            level2_urls = get_connections(driver, contact_url, max_connections=_MAX_CONNECTIONS_PER_FETCH)
            level2_urls = list(dict.fromkeys(level2_urls))
            print(f"  → {len(level2_urls)} conexiones de nivel 2")
            saved_lvl2 = _scrape_batch(driver, level2_urls, already_scraped, counter)
            all_saved.extend(saved_lvl2)
        except Exception as e:
            print(f"  ⚠  Error obteniendo conexiones de {contact_url}: {e}")

    return (all_saved, owner_slug)


# ---------------------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    headless_env = os.getenv("SCRAPER_HEADLESS", "true").strip().lower()
    headless = headless_env in ("1", "true", "yes", "on")
    driver = create_driver(headless=headless)
    saved_paths = []
    owner_slug = ""
    
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

        # Modo no interactivo para integración con la vista web
        noninteractive = os.getenv("SCRAPER_NONINTERACTIVE", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        scraper_mode = os.getenv("SCRAPER_MODE", "").strip().lower()
        seed_url_env = os.getenv("SCRAPER_SEED_URL", "").strip()

        if noninteractive and scraper_mode in ("url", "my_contacts"):
            if scraper_mode == "url":
                if not seed_url_env or "linkedin.com/in/" not in seed_url_env:
                    print("ERROR: SCRAPER_SEED_URL inválida. Debe ser una URL de perfil (/in/).")
                    raise SystemExit(1)
                seed_urls = [_normalize(seed_url_env)]
                saved_paths, owner_slug = run_mode_1_2(driver, seed_urls)
            else:  # my_contacts
                if not own_url:
                    print("ERROR: no se pudo detectar el perfil propio; no se pueden obtener tus contactos.")
                    raise SystemExit(1)
                saved_paths, owner_slug = run_mode_1_2(driver, [own_url])
        else:
            # Modo interactivo por terminal (flujo original)
            while True:
                config = choose_mode(driver, own_url)

                if config["mode"] == 0:
                    print("Saliendo.")
                    raise SystemExit(0)

                try:
                    if config["mode"] == 3:
                        saved_paths, owner_slug = run_mode_3(driver, config["own_url"])
                    else:
                        if not config["seed_urls"]:
                            print("No se introdujo ninguna URL.")
                            continue
                        saved_paths, owner_slug = run_mode_1_2(
                            driver,
                            config["seed_urls"],
                            own_url=config.get("own_url", ""),
                        )
                    break
                except CancelToMenu:
                    print("\n  Cancelado por usuario. Volviendo al menú principal...\n")

    finally:
        quit_driver(driver)

    if not saved_paths:
        print("No se descargó ningún perfil.")
        raise SystemExit(1)

    print("\n── Parseando HTML ──────────────────────────────")
    records = []
    missing_files = 0
    for p in saved_paths:
        try:
            records.append(parse_profile_file(p))
        except FileNotFoundError:
            missing_files += 1
            print(f"  ⚠  Archivo no encontrado, se omite: {p}")

    print(f"  {len(records)} perfiles parseados")
    if missing_files:
        print(f"  ⚠  {missing_files} perfiles omitidos por HTML inexistente")

    filtered_records = [r for r in records if _is_usable_record(r)]
    dropped = len(records) - len(filtered_records)
    if dropped:
        print(f"  ⚠  {dropped} perfiles omitidos por datos vacíos/intersticiales")

    if not filtered_records:
        print("No hay perfiles parseables para exportar.")
        print("Finalizando sin error para evitar reinicios en bucle.")
        raise SystemExit(0)

    for r in filtered_records:
        print(f"  · {r['name']:30s} | {r['company']:25s} | {r['location']}")

    # Extraer el nombre del owner buscando el record que coincida con owner_slug
    owner_name = ""
    if owner_slug:
        # Buscar en saved_paths el archivo que coincida con owner_slug
        for path in saved_paths:
            if path.stem == owner_slug:  # path.stem es el nombre sin extensión
                # Parsear solo ese archivo para obtener el nombre
                try:
                    owner_record = parse_profile_file(path)
                    owner_name = owner_record.get("name", "")
                except FileNotFoundError:
                    owner_name = ""
                break
        
        # Si no lo encontramos en saved_paths, usar el slug formateado
        if not owner_name:
            # Convertir slug a nombre legible: "miquel-font-barrot" → "MiquelFontBarrot"
            owner_name = "".join(word.capitalize() for word in owner_slug.replace("-", " ").split())

    print("\n── Exportando resultados ───────────────────────")
    if owner_name:
        print(f"  Propietario: {owner_name}")
    paths = export_results(filtered_records, fmt="both", owner_name=owner_name)
    for p in paths:
        print(f"  → {p}")
