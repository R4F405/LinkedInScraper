"""
app.py — Vista web para gestionar scrapeos de LinkedIn.
"""

import os
import re
import subprocess
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from datetime import datetime

import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file

from utils.config import OUTPUT_DIR, ROOT_DIR
from exporter.export import export_to_pdf

app = Flask(__name__, template_folder=str(ROOT_DIR / "templates"))

# Archivos de resultados: results_YYYYMMDD_HHMMSS o ContactosNombre_YYYYMMDD_HHMMSS
RESULTS_PATTERN = re.compile(r"^.+_\d{8}_\d{6}$")


def _list_scrape_ids():
    """Devuelve lista de IDs de scrapeo (basename sin extensión) ordenados por fecha descendente."""
    if not OUTPUT_DIR.exists():
        return []
    ids = set()
    for f in OUTPUT_DIR.iterdir():
        if f.suffix.lower() in (".csv", ".xlsx") and RESULTS_PATTERN.match(f.stem):
            ids.add(f.stem)
    return sorted(ids, reverse=True)


def _scrape_record_count(scrape_id: str) -> int:
    """Cuenta las filas del CSV (sin cabecera) para el scrape_id dado."""
    csv_path = OUTPUT_DIR / f"{scrape_id}.csv"
    if not csv_path.exists():
        return 0
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
        return len(df)
    except Exception:
        return 0


def _parse_timestamp(scrape_id: str) -> str:
    """Extrae timestamp legible del ID (…_20260309_130049 -> 09/03/2026 13:00)."""
    m = re.search(r"_(\d{8}_\d{6})$", scrape_id)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
            return dt.strftime("%d/%m/%Y %H:%M")
        except ValueError:
            pass
    return scrape_id


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scrapes", methods=["GET"])
def api_list_scrapes():
    """Lista todos los scrapeos con id, fecha y número de registros."""
    ids = _list_scrape_ids()
    items = [
        {
            "id": sid,
            "date": _parse_timestamp(sid),
            "count": _scrape_record_count(sid),
        }
        for sid in ids
    ]
    return jsonify(items)


@app.route("/api/scrapes/<scrape_id>/data", methods=["GET"])
def api_scrape_data(scrape_id: str):
    """Devuelve los datos (registros) del scrapeo como JSON."""
    if not RESULTS_PATTERN.match(scrape_id):
        return jsonify({"error": "ID inválido"}), 400
    csv_path = OUTPUT_DIR / f"{scrape_id}.csv"
    if not csv_path.exists():
        return jsonify({"error": "No existe ese scrapeo"}), 404
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
        # Rellenar NaN para JSON
        data = df.fillna("").to_dict(orient="records")
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scrape", methods=["POST"])
def api_start_scrape():
    """Inicia el scraping de una URL (perfil + sus contactos) vía run.py. En macOS abre una ventana de Terminal."""
    body = request.get_json() or {}
    url = (body.get("url") or "").strip()
    if not url or "linkedin.com/in/" not in url:
        return jsonify({"ok": False, "error": "URL inválida. Debe ser un perfil de LinkedIn."}), 400
    script = ROOT_DIR / "run.py"
    if not script.exists():
        return jsonify({"ok": False, "error": "run.py no encontrado"}), 500
    try:
        if sys.platform == "darwin":
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".command", delete=False, dir=str(ROOT_DIR)
            ) as f:
                f.write("#!/bin/bash\n")
                f.write(f"cd {str(ROOT_DIR)!r}\n")
                f.write(f"exec {sys.executable!r} run.py --url {url!r}\n")
                f.write('echo ""\nread -p "Pulsa Enter para cerrar..."\n')
            os.chmod(f.name, 0o755)
            subprocess.Popen(
                ["open", "-a", "Terminal", f.name],
                env=os.environ.copy(),
            )
        else:
            subprocess.Popen(
                [sys.executable, str(script), "--url", url],
                cwd=str(ROOT_DIR),
                env=os.environ.copy(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    if sys.platform == "darwin":
        msg = "Se ha abierto una ventana de Terminal. Se scrapeará ese perfil y sus contactos; al terminar, actualiza la lista."
    else:
        msg = "Scraping iniciado (perfil + contactos). Al terminar, actualiza la lista."
    return jsonify({"ok": True, "message": msg})


@app.route("/api/scrape-my-contacts", methods=["POST"])
def api_scrape_my_contacts():
    """Inicia el scraping de los contactos de quien inicia sesión (email y contraseña en el body)."""
    body = request.get_json() or {}
    email = (body.get("email") or "").strip()
    password = (body.get("password") or "").strip()
    if not email or not password:
        return jsonify({"ok": False, "error": "Indica email y contraseña de LinkedIn."}), 400
    script = ROOT_DIR / "run_my_contacts.py"
    if not script.exists():
        return jsonify({"ok": False, "error": "run_my_contacts.py no encontrado"}), 500
    try:
        # Archivo temporal con credenciales (run_my_contacts.py lo lee y lo borra)
        env_fd, env_path = tempfile.mkstemp(prefix="linkedin_creds_", suffix=".env", text=True)
        with os.fdopen(env_fd, "w", encoding="utf-8") as f:
            f.write(f"LINKEDIN_EMAIL={email}\n")
            f.write(f"LINKEDIN_PASSWORD={password}\n")
        try:
            if sys.platform == "darwin":
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".command", delete=False, dir=str(ROOT_DIR)
                ) as f:
                    f.write("#!/bin/bash\n")
                    f.write(f"cd {str(ROOT_DIR)!r}\n")
                    f.write(f"exec {sys.executable!r} run_my_contacts.py --env-file {env_path!r}\n")
                    f.write('echo ""\nread -p "Pulsa Enter para cerrar..."\n')
                os.chmod(f.name, 0o755)
                subprocess.Popen(
                    ["open", "-a", "Terminal", f.name],
                    env=os.environ.copy(),
                )
            else:
                subprocess.Popen(
                    [sys.executable, str(script), "--env-file", env_path],
                    cwd=str(ROOT_DIR),
                    env=os.environ.copy(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            try:
                os.unlink(env_path)
            except Exception:
                pass
            raise
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    msg = (
        "Se ha abierto una ventana de Terminal. Chrome iniciará sesión con tus datos y descargará tus contactos. "
        "Al terminar, actualiza la lista."
    ) if sys.platform == "darwin" else "Scraping de tus contactos iniciado. Al terminar, actualiza la lista."
    return jsonify({"ok": True, "message": msg})


@app.route("/api/download/<scrape_id>", methods=["GET"])
def api_download(scrape_id: str):
    """Descarga el scrapeo en formato csv, excel o pdf."""
    fmt = (request.args.get("fmt") or "csv").lower()
    if fmt not in ("csv", "excel", "xlsx", "pdf"):
        return jsonify({"error": "Formato no válido"}), 400
    if not RESULTS_PATTERN.match(scrape_id):
        return jsonify({"error": "ID inválido"}), 400
    csv_path = OUTPUT_DIR / f"{scrape_id}.csv"
    if not csv_path.exists():
        return jsonify({"error": "No existe ese scrapeo"}), 404

    if fmt == "csv":
        return send_file(csv_path, as_attachment=True, download_name=f"{scrape_id}.csv", mimetype="text/csv")
    if fmt in ("excel", "xlsx"):
        xlsx_path = OUTPUT_DIR / f"{scrape_id}.xlsx"
        if not xlsx_path.exists():
            df = pd.read_csv(csv_path, encoding="utf-8")
            xlsx_path = OUTPUT_DIR / f"{scrape_id}.xlsx"
            df.to_excel(xlsx_path, index=False, engine="openpyxl")
        return send_file(
            xlsx_path,
            as_attachment=True,
            download_name=f"{scrape_id}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    # pdf
    df = pd.read_csv(csv_path, encoding="utf-8")
    pdf_path = OUTPUT_DIR / f"{scrape_id}.pdf"
    export_to_pdf(df, pdf_path)
    return send_file(pdf_path, as_attachment=True, download_name=f"{scrape_id}.pdf", mimetype="application/pdf")


@app.route("/api/export-filtered", methods=["POST"])
def api_export_filtered():
    """Exporta solo los registros enviados en el body (ej. lo filtrado en la vista)."""
    body = request.get_json() or {}
    records = body.get("records", [])
    fmt = (body.get("fmt") or "excel").lower()
    if fmt not in ("csv", "excel", "xlsx", "pdf"):
        return jsonify({"error": "Formato no válido"}), 400
    if not records or not isinstance(records, list):
        return jsonify({"error": "No hay datos para exportar"}), 400
    df = pd.DataFrame(records)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"contactos_filtrados_{timestamp}"
    if fmt == "csv":
        buf = BytesIO()
        df.to_csv(buf, index=False, encoding="utf-8")
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f"{name}.csv", mimetype="text/csv")
    if fmt in ("excel", "xlsx"):
        buf = BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name=f"{name}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = Path(f.name)
    try:
        export_to_pdf(df, pdf_path)
        return send_file(pdf_path, as_attachment=True, download_name=f"{name}.pdf", mimetype="application/pdf")
    finally:
        pdf_path.unlink(missing_ok=True)


if __name__ == "__main__":
    # Puerto 5001: en macOS el 5000 suele estar ocupado por AirPlay Receiver
    app.run(debug=True, host="0.0.0.0", port=5001)
