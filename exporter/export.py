"""
exporter/export.py

Convierte la lista de dicts producida por parser/ en un DataFrame de pandas
y lo exporta a CSV y/o Excel en data/output/.

Uso standalone:
    from exporter.export import export_results
"""

from pathlib import Path
from datetime import datetime

import pandas as pd

from utils.config import OUTPUT_DIR

FIELDNAMES = ["name", "email", "phone", "location", "company"]


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def to_dataframe(records: list[dict]) -> pd.DataFrame:
    """
    Convierte una lista de dicts (salida de parse_all_profiles) en un DataFrame.
    Garantiza que todas las columnas definidas en FIELDNAMES existan.
    """
    df = pd.DataFrame(records)
    for col in FIELDNAMES:
        if col not in df.columns:
            df[col] = ""
    return df[FIELDNAMES]


def export_results(
    records: list[dict],
    output_dir: Path = OUTPUT_DIR,
    fmt: str = "both",
) -> list[Path]:
    """
    Exporta los registros al directorio indicado.

    Args:
        records:    Lista de dicts (output de parse_all_profiles).
        output_dir: Directorio destino (se crea si no existe).
        fmt:        "csv", "excel" o "both".

    Returns:
        Lista de los Path de los archivos creados.
    """
    if not records:
        raise ValueError("No hay registros para exportar.")

    output_dir.mkdir(parents=True, exist_ok=True)
    df = to_dataframe(records)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    created: list[Path] = []

    if fmt in ("csv", "both"):
        csv_path = output_dir / f"results_{timestamp}.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8")
        created.append(csv_path)

    if fmt in ("excel", "both"):
        xlsx_path = output_dir / f"results_{timestamp}.xlsx"
        df.to_excel(xlsx_path, index=False, engine="openpyxl")
        created.append(xlsx_path)

    return created


def export_to_pdf(df: "pd.DataFrame", output_path: Path) -> None:
    """Exporta el DataFrame a un PDF con tabla legible."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=1.5 * cm, leftMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    elements = []

    # Título
    elements.append(Paragraph("Resultados LinkedIn Scraper", styles["Title"]))
    elements.append(Paragraph(f"Registros: {len(df)}", styles["Normal"]))

    # Convertir DataFrame a lista para la tabla (truncar textos largos)
    data = [df.columns.tolist()]
    for _, row in df.iterrows():
        data.append([str(v)[:50] + ("..." if len(str(v)) > 50 else "") for v in row])

    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0a66c2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(t)
    doc.build(elements)
