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

FIELDNAMES = ["name", "email", "headline", "location", "source_file"]


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
