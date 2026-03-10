from pathlib import Path

# Raíz del proyecto
ROOT_DIR = Path(__file__).resolve().parent.parent

# Carpeta donde Miquel deposita los HTML crudos
RAW_HTML_DIR = ROOT_DIR / "data" / "raw"

# Carpeta de resultados
OUTPUT_DIR = ROOT_DIR / "data" / "output"

# Carpeta de sesiones (cookies persistentes para evitar login repetido)
SESSION_DIR = ROOT_DIR / "data" / "sessions"

RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SESSION_DIR.mkdir(parents=True, exist_ok=True)
