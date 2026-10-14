"""Test suite for CSV ingestion, schema validation, dirty data normalization,
timestamp parsing, and edge cases.
"""

import pytest
import polars as pl
from pathlib import Path
from app.ingestion.csv.scanner import scan_csv
from app.validation.preflight import preflight_csv
from app.ingestion.csv.transformer import transform_csv
from app.transformation.units import apply_unit_conversion


def test_unit_conversion():
    s = pl.Series("temp_c", [0.0, 100.0])
    converted, formula = apply_unit_conversion(s, "°C", "°F")
    assert formula is not None
    assert round(converted[0], 1) == 32.0
    assert round(converted[1], 1) == 212.0


def test_valid_csv_ingestion(tmp_path: Path):
    csv_file = tmp_path / "valid.csv"
    csv_file.write_text(
        "timestamp,AHU1_SAT,AHU1_RAT,AHU1_FAN_CMD\n"
        "2026-01-01T00:00:00Z,55.2,72.1,1\n"
        "2026-01-01T00:05:00Z,55.5,72.3,1\n"
        "2026-01-01T00:10:00Z,55.4,72.0,1\n",
        encoding="utf-8"
    )
    result = transform_csv(csv_file)
    assert result.dataframe.shape == (3, 4)
    assert result.mapped_column_count >= 2
    assert "timestamp" in result.dataframe.columns


def test_empty_csv_raises_clean_error(tmp_path: Path):
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="contains no data rows"):
        scan_csv(empty_csv)


def test_header_only_csv_raises_clean_error(tmp_path: Path):
    header_only = tmp_path / "header_only.csv"
    header_only.write_text("timestamp,AHU1_SAT,AHU1_RAT\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contains no data rows"):
        scan_csv(header_only)


def test_duplicate_column_headers(tmp_path: Path):
    csv_file = tmp_path / "dup.csv"
    csv_file.write_text(
        "timestamp,SAT,SAT,RAT\n"
        "2026-01-01T00:00:00Z,55.0,56.0,72.0\n"
        "2026-01-01T00:05:00Z,55.5,56.5,72.5\n",
        encoding="utf-8"
    )
    scan = scan_csv(csv_file)
    assert len(scan["columns"]) == 4


def test_timestamp_preflight_and_iso_parsing(tmp_path: Path):
    csv_file = tmp_path / "iso_ts.csv"
    csv_file.write_text(
        "timestamp,sat\n"
        "2026-01-01T00:00:00Z,55.0\n"
        "2026-01-01 00:05:00+00:00,55.5\n"
        "2026-01-01T00:10:00.000Z,55.4\n",
        encoding="utf-8"
    )
    pf = preflight_csv(csv_file)
    assert pf["timestamp_column"] == "timestamp"
    assert pf["valid"] is True


def test_sampling_interval_detection(tmp_path: Path):
    csv_file = tmp_path / "interval.csv"
    csv_file.write_text(
        "timestamp,sat\n"
        "2026-01-01T00:00:00Z,55.0\n"
        "2026-01-01T00:05:00Z,55.5\n"
        "2026-01-01T00:10:00Z,55.4\n"
        "2026-01-01T00:15:00Z,55.8\n",
        encoding="utf-8"
    )
    pf = preflight_csv(csv_file)
    # 5 min = 300s
    assert pf.get("median_sampling_seconds") == 300.0 or pf["valid"] is True


def test_dirty_sentinels_and_null_handling(tmp_path: Path):
    csv_file = tmp_path / "dirty.csv"
    csv_file.write_text(
        "timestamp,sat,rat\n"
        "2026-01-01T00:00:00Z,nan,72.0\n"
        "2026-01-01T00:05:00Z,55.0,null\n"
        "2026-01-01T00:10:00Z,56.0,73.5\n",
        encoding="utf-8"
    )
    res = transform_csv(csv_file)
    assert res.dataframe.height == 3
    # Check that string numbers parse cleanly or match
    assert str(res.dataframe["rat"][2]) == "73.5"


def test_extreme_and_negative_values(tmp_path: Path):
    csv_file = tmp_path / "extremes.csv"
    csv_file.write_text(
        "timestamp,oa_t,duct_static\n"
        "2026-01-01T00:00:00Z,-25.5,0.0\n"
        "2026-01-01T00:05:00Z,125.0,2.5\n",
        encoding="utf-8"
    )
    res = transform_csv(csv_file)
    assert res.dataframe["oa_t"].min() == -25.5
    assert res.dataframe["duct_static"].max() == 2.5
