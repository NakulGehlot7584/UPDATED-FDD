"""
Preflight CSV validation module for verifying structural and timestamp integrity.

Source of Truth:
- Timestamp candidates: `TIMESTAMP_CANDIDATES`
- Candidate datetime formats: `CANDIDATE_DATETIME_FORMATS`

Design Principles:
1. Robust Timestamp Parsing: Generic support for ISO8601, 12-hour AM/PM, month names,
   and trailing timezone strings (e.g. IST, UTC) without filename-specific hacks.
2. Non-Destructive: Validates datasets read-only without modifying inputs on disk.
3. Preserves Output Contract: Retains valid, timestamp_column, timestamp_valid,
   missing_timestamps, duplicate_timestamps, non_monotonic_timestamps,
   median_sampling_seconds, warnings, and errors.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl


TIMESTAMP_CANDIDATES: tuple[str, ...] = (
    "timestamp",
    "timestamp_utc",
    "datetime",
    "date_time",
    "time",
)

CANDIDATE_DATETIME_FORMATS: tuple[str, ...] = (
    "%d-%b-%y %I:%M:%S %p",    # 01-Jul-26 12:00:00 AM
    "%d-%b-%Y %I:%M:%S %p",    # 01-Jul-2026 12:00:00 AM
    "%d-%b-%y %H:%M:%S",       # 01-Jul-26 14:00:00
    "%d-%b-%Y %H:%M:%S",       # 01-Jul-2026 14:00:00
    "%b-%d-%y %I:%M:%S %p",    # Jul-01-26 12:00:00 AM
    "%b-%d-%Y %I:%M:%S %p",    # Jul-01-2026 12:00:00 AM
    "%Y-%m-%d %H:%M:%S",       # 2026-07-01 14:00:00
    "%Y-%m-%d %I:%M:%S %p",    # 2026-07-01 02:00:00 PM
    "%m/%d/%Y %I:%M:%S %p",    # 07/01/2026 02:00:00 PM
    "%d/%m/%Y %I:%M:%S %p",    # 01/07/2026 02:00:00 PM
    "%m/%d/%Y %H:%M:%S",       # 07/01/2026 14:00:00
    "%d/%m/%Y %H:%M:%S",       # 01/07/2026 14:00:00
    "%m/%d/%y %I:%M:%S %p",    # 07/01/26 02:00:00 PM
    "%d/%m/%y %I:%M:%S %p",    # 01/07/26 02:00:00 PM
    "%m/%d/%y %H:%M:%S",       # 07/01/26 14:00:00
    "%d/%m/%y %H:%M:%S",       # 01/07/26 14:00:00
    "%Y/%m/%d %H:%M:%S",       # 2026/07/01 14:00:00
    "%d-%m-%Y %H:%M:%S",       # 01-07-2026 14:00:00
    "%Y-%m-%d",                # 2026-07-01
    "%d-%b-%Y",                # 01-Jul-2026
    "%d-%b-%y",                # 01-Jul-26
)


def find_timestamp_column(columns: list[str]) -> str | None:
    """
    Find a likely timestamp column using generic column-name candidates.
    """
    normalized = {column.lower().strip(): column for column in columns}

    for candidate in TIMESTAMP_CANDIDATES:
        if candidate in normalized:
            return normalized[candidate]

    return None


def parse_timestamp_series(raw_series: pl.Series) -> pl.Series:
    """
    Robustly parse timestamp values into a polars.Datetime series.

    Handles:
    - Native Datetime / Date series
    - ISO8601 formats with timezone offsets (+05:30, -04:00, Z) normalized to UTC
    - Standard timezone abbreviations (IST, UTC, GMT, EDT, EST, etc.) converted to UTC
    - 12-hour AM/PM formats with 2-digit / 4-digit years
    - 3-letter month abbreviations (e.g. 01-Jul-26 12:00:00 AM IST)
    - Naive timestamps preserved as wall-clock datetime
    """
    if raw_series.dtype in (pl.Datetime, pl.Date):
        return raw_series.cast(pl.Datetime)

    import re
    import pandas as pd

    tz_abbr_map = {
        "UTC": "+00:00",
        "GMT": "+00:00",
        "Z": "+00:00",
        "IST": "+05:30",
        "EDT": "-04:00",
        "EST": "-05:00",
        "CDT": "-05:00",
        "CST": "-06:00",
        "MDT": "-06:00",
        "MST": "-07:00",
        "PDT": "-07:00",
        "PST": "-08:00",
    }

    raw_list = raw_series.cast(pl.Utf8).str.strip_chars().to_list()
    has_explicit_offset = False
    converted_list: list[str | None] = []

    for val in raw_list:
        if val is None or val == "":
            converted_list.append(None)
            continue
        v = str(val).strip()
        matched = False
        for abbr, off in tz_abbr_map.items():
            if v.endswith(" " + abbr):
                idx = v.rfind(abbr)
                v = v[:idx].strip() + off
                matched = True
                has_explicit_offset = True
                break
            elif abbr == "Z" and v.endswith("Z"):
                has_explicit_offset = True
                matched = True
                break
        if not matched:
            if re.search(r"[\+\-]\d{2}:?\d{2}$", v):
                has_explicit_offset = True
        converted_list.append(v)

    try:
        # If any timestamps had explicit offsets/tz abbreviations, normalize them to true UTC
        dt_pd = pd.to_datetime(
            converted_list,
            format="mixed",
            utc=has_explicit_offset,
            errors="coerce",
        )
        if has_explicit_offset and hasattr(dt_pd, "tz_localize"):
            dt_pd = dt_pd.tz_localize(None)
        return pl.Series(raw_series.name, dt_pd.to_numpy())
    except Exception:
        pass

    # Fallback to Polars native string parsing
    s_str = raw_series.cast(pl.Utf8).str.strip_chars()
    for fmt in CANDIDATE_DATETIME_FORMATS:
        try:
            res = s_str.str.strptime(pl.Datetime, format=fmt, strict=False)
            if res.null_count() == 0 and res.len() > 0:
                return res
        except Exception:
            continue

    return s_str.str.strptime(pl.Datetime, format=None, strict=False)


def preflight_csv(file_path: str | Path) -> dict:
    """
    Validate the basic structural and timestamp health of a CSV.

    This function does not modify the input CSV.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    if path.suffix.lower() != ".csv":
        raise ValueError(f"Expected a CSV file, got: {path.suffix}")

    df = pl.read_csv(path)

    timestamp_column = find_timestamp_column(df.columns)

    report = {
        "file_name": path.name,
        "valid": True,
        "timestamp_column": timestamp_column,
        "timestamp_valid": False,
        "missing_timestamps": 0,
        "duplicate_timestamps": 0,
        "non_monotonic_timestamps": 0,
        "median_sampling_seconds": None,
        "warnings": [],
        "errors": [],
    }

    if timestamp_column is None:
        report["valid"] = False
        report["errors"].append("No timestamp column found.")
        return report

    raw_timestamp = df[timestamp_column]
    timestamps = parse_timestamp_series(raw_timestamp)

    report["missing_timestamps"] = timestamps.null_count()

    if report["missing_timestamps"] > 0:
        report["valid"] = False
        report["errors"].append(
            f"{report['missing_timestamps']} timestamp values could not be parsed."
        )

    valid_timestamps = timestamps.drop_nulls()

    if valid_timestamps.is_empty():
        report["valid"] = False
        report["errors"].append("No valid timestamps available.")
        return report

    report["timestamp_valid"] = True

    report["duplicate_timestamps"] = (
        valid_timestamps.len() - valid_timestamps.n_unique()
    )

    if report["duplicate_timestamps"] > 0:
        report["warnings"].append(
            f"{report['duplicate_timestamps']} duplicate timestamps found (deduplicated via last-write-wins)."
        )

    differences = valid_timestamps.diff().dt.total_seconds()

    negative_steps = differences.filter(differences < 0)

    report["non_monotonic_timestamps"] = negative_steps.len()

    if report["non_monotonic_timestamps"] > 0:
        report["warnings"].append(
            f"{report['non_monotonic_timestamps']} non-monotonic timestamp steps found (sorted chronologically during canonical ingestion)."
        )

    positive_steps = differences.filter(differences > 0)

    if not positive_steps.is_empty():
        report["median_sampling_seconds"] = positive_steps.median()

    return report
