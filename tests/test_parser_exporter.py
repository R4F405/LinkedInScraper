"""
tests/test_parser_exporter.py

Tests para parser/profile_parser.py y exporter/export.py.
No requieren red ni navegador — trabajan con HTML de ejemplo local.

Ejecutar:
    python -m pytest tests/ -v
"""

import sys
from pathlib import Path

import pytest
import pandas as pd

# ---------------------------------------------------------------------------
# Asegurar que la raíz del proyecto esté en el path cuando se ejecuta pytest
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.profile_parser import parse_profile_html, parse_profile_file, parse_all_profiles
from exporter.export import to_dataframe, export_results

FIXTURE_HTML = Path(__file__).parent / "fixtures" / "sample_profile.html"


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def sample_html() -> str:
    return FIXTURE_HTML.read_text(encoding="utf-8")


@pytest.fixture
def sample_records() -> list[dict]:
    return [
        {
            "name": "Maria García López",
            "email": "maria.garcia@example.com",
            "headline": "Senior Software Engineer at Acme Corp",
            "location": "Barcelona, Cataluña, España",
            "company": "Acme Corp",
            "education": "Universitat Politècnica de Catalunya",
            "source_file": "sample_profile.html",
        }
    ]


# ===========================================================================
# Tests — parser
# ===========================================================================

class TestParseProfileHtml:

    def test_name_extracted(self, sample_html):
        data = parse_profile_html(sample_html)
        assert data["name"] == "Maria García López"

    def test_headline_extracted(self, sample_html):
        data = parse_profile_html(sample_html)
        assert data["headline"] == "Senior Software Engineer at Acme Corp"

    def test_location_extracted(self, sample_html):
        data = parse_profile_html(sample_html)
        assert data["location"] == "Barcelona, Cataluña, España"

    def test_email_extracted(self, sample_html):
        data = parse_profile_html(sample_html)
        assert data["email"] == "maria.garcia@example.com"

    def test_company_extracted(self, sample_html):
        data = parse_profile_html(sample_html)
        assert data["company"] == "Acme Corp"

    def test_education_extracted(self, sample_html):
        data = parse_profile_html(sample_html)
        assert data["education"] == "Universitat Politècnica de Catalunya"

    def test_returns_dict_with_expected_keys(self, sample_html):
        data = parse_profile_html(sample_html)
        assert set(data.keys()) == {"name", "email", "headline", "location", "company", "education"}

    def test_empty_html_returns_empty_strings(self):
        data = parse_profile_html("<html></html>")
        assert data == {"name": "", "email": "", "headline": "", "location": "", "company": "", "education": ""}


class TestParseProfileFile:

    def test_reads_file_and_includes_source_file_key(self):
        data = parse_profile_file(FIXTURE_HTML)
        assert data["source_file"] == FIXTURE_HTML.name
        assert data["name"] == "Maria García López"


class TestParseAllProfiles:

    def test_returns_list_from_directory(self, tmp_path):
        # Copiar el fixture al tmp_path para aislar el test
        import shutil
        shutil.copy(FIXTURE_HTML, tmp_path / "profile_1.html")
        results = parse_all_profiles(tmp_path)
        assert len(results) == 1
        assert results[0]["name"] == "Maria García López"

    def test_empty_directory_returns_empty_list(self, tmp_path):
        results = parse_all_profiles(tmp_path)
        assert results == []


# ===========================================================================
# Tests — exporter
# ===========================================================================

class TestToDataframe:

    def test_returns_dataframe(self, sample_records):
        df = to_dataframe(sample_records)
        assert isinstance(df, pd.DataFrame)

    def test_has_expected_columns(self, sample_records):
        df = to_dataframe(sample_records)
        assert list(df.columns) == ["name", "email", "headline", "location", "company", "education", "source_file"]

    def test_row_values_match_input(self, sample_records):
        df = to_dataframe(sample_records)
        row = df.iloc[0]
        assert row["name"] == "Maria García López"
        assert row["email"] == "maria.garcia@example.com"

    def test_missing_columns_filled_with_empty_string(self):
        df = to_dataframe([{"name": "Test User"}])
        assert df["email"].iloc[0] == ""
        assert df["location"].iloc[0] == ""
        assert df["company"].iloc[0] == ""
        assert df["education"].iloc[0] == ""


class TestExportResults:

    def test_exports_csv(self, sample_records, tmp_path):
        paths = export_results(sample_records, output_dir=tmp_path, fmt="csv")
        assert len(paths) == 1
        assert paths[0].suffix == ".csv"
        assert paths[0].exists()

    def test_exports_excel(self, sample_records, tmp_path):
        paths = export_results(sample_records, output_dir=tmp_path, fmt="excel")
        assert len(paths) == 1
        assert paths[0].suffix == ".xlsx"
        assert paths[0].exists()

    def test_exports_both_by_default(self, sample_records, tmp_path):
        paths = export_results(sample_records, output_dir=tmp_path, fmt="both")
        assert len(paths) == 2
        extensions = {p.suffix for p in paths}
        assert extensions == {".csv", ".xlsx"}

    def test_csv_content_matches_input(self, sample_records, tmp_path):
        paths = export_results(sample_records, output_dir=tmp_path, fmt="csv")
        df = pd.read_csv(paths[0])
        assert df.iloc[0]["name"] == "Maria García López"

    def test_raises_on_empty_records(self, tmp_path):
        with pytest.raises(ValueError, match="No hay registros"):
            export_results([], output_dir=tmp_path)
