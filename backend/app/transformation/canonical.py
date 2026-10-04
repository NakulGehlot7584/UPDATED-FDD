"""
Canonical data transformation engine for the Open-FDD ingestion pipeline.

Source of Truth:
- Semantic mapping result: `app.mapping.mapper.MappingResult`
- Role catalog: `app.mapping.roles.CANONICAL_ROLES`
- Role units: `app.ingestion.csv.transformer.CANONICAL_ROLE_UNITS`
- Unit inference & classification: `app.ingestion.csv.transformer._infer_source_unit`, `_classify_column_category`
- Timestamp parser: `app.validation.preflight.parse_timestamp_series`, `find_timestamp_column`
- Unit conversions: `app.transformation.units.apply_unit_conversion`
- Canonical schema: `app.transformation.schema.CanonicalSchema`

Design Principles:
1. Reuses Mapping Result: Operates directly on the resolved canonical role mapping without
   re-inferring roles or creating redundant mapping logic.
2. Safe Numeric Handling: Casts sensor, setpoint, and command values to clean `Float64`,
   gracefully converting invalid non-numeric strings, sentinels (e.g. NaN, null, N/A),
   and boolean strings (true/false, on/off) into valid numeric or null representations without crashing.
3. Traceable & Non-Destructive: Retains the original raw DataFrame, provides an explicit
   canonical schema, and catalogs all unmapped source columns with classification rationale.
4. Isolated Metadata: Keeps temporal and topology metadata separate from HVAC telemetry signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from app.ingestion.csv.scanner import scan_csv
from app.mapping.mapper import MappingResult, map_columns
from app.mapping.normalizer import normalize_column_name
from app.transformation.schema import (
    CanonicalField,
    CanonicalSchema,
    ConversionRecord,
    UnmappedChannel,
)
from app.transformation.units import (
    CANONICAL_ROLE_UNITS,
    _classify_column_category,
    _infer_source_unit,
    apply_unit_conversion,
)
from app.validation.preflight import find_timestamp_column, parse_timestamp_series, preflight_csv


# ============================================================
# DATA VALUE SANITIZATION HELPERS
# ============================================================

def _sanitize_numeric_series(series: pl.Series) -> pl.Series:
    """
    Safely convert a Polars Series to Float64, handling dirty text, booleans, and null sentinels.

    - Booleans: True -> 1.0, False -> 0.0
    - Text booleans / status words: 'true'/'on'/'open'/'run' -> 1.0, 'false'/'off'/'closed'/'stop' -> 0.0
    - Sentinels: 'nan', 'null', 'none', 'n/a', '#n/a', 'err', '--' -> null
    - Native float NaN / Inf -> null (prevents IEEE 754 DataFusion total ordering false positives)
    - Non-numeric strings -> null (via strict=False)
    """
    if series.dtype in (pl.Float64, pl.Float32):
        s_float = series.cast(pl.Float64)
        s_clean = pl.when(s_float.is_nan() | s_float.is_infinite()).then(pl.lit(None)).otherwise(s_float)
        return pl.select(s_clean.alias(series.name)).to_series()

    if series.dtype in (pl.Int64, pl.Int32, pl.Int16, pl.Int8, pl.UInt64, pl.UInt32, pl.UInt16, pl.UInt8):
        return series.cast(pl.Float64)

    if series.dtype == pl.Boolean:
        return series.cast(pl.Float64)

    # Handle string / object types
    s_str = series.cast(pl.Utf8).str.strip_chars().str.to_lowercase()

    # Normalize known boolean / binary status strings
    s_normalized = (
        pl.when(s_str.is_in(["true", "t", "on", "open", "run", "active", "enabled", "1"]))
        .then(pl.lit("1.0"))
        .when(s_str.is_in(["false", "f", "off", "closed", "stop", "inactive", "disabled", "0"]))
        .then(pl.lit("0.0"))
        .when(s_str.is_in(["nan", "null", "none", "n/a", "#n/a", "err", "error", "--", ""]))
        .then(pl.lit(None))
        .otherwise(s_str)
    )

    # Cast to Float64 with strict=False to ensure invalid text never throws
    sanitized_expr = s_normalized.cast(pl.Float64, strict=False).alias(series.name)
    sanitized_s = pl.select(sanitized_expr).to_series()
    # Ensure any NaN/infinite resulting from string parse is also converted to null
    s_clean = pl.when(sanitized_s.is_nan() | sanitized_s.is_infinite()).then(pl.lit(None)).otherwise(sanitized_s)
    return pl.select(s_clean.alias(series.name)).to_series()


def _find_equipment_column(columns: list[str]) -> str | None:
    """
    Find a source column designated as equipment / asset identifier.
    """
    for col in columns:
        norm = normalize_column_name(col)
        if norm in (
            "equipment_id",
            "equipment",
            "device_id",
            "device",
            "asset_id",
            "ahu_id",
            "vav_id",
            "unit_id",
        ):
            return col
    return None


# ============================================================
# CANONICAL TRANSFORMATION RESULT
# ============================================================

@dataclass(frozen=True)
class CanonicalTransformResult:
    """
    Container presenting the clean in-memory canonical telemetry dataset,
    complete schema traceability, mapping audit, and original source data.
    """

    canonical_df: pl.DataFrame
    source_df: pl.DataFrame
    schema: CanonicalSchema
    mapping_result: MappingResult
    file_path: str | None = None
    file_name: str | None = None
    timestamp_column: str | None = None
    equipment_id_column: str | None = None
    sampling_interval_seconds: float | None = None
    rows_duped: int = 0
    conversions_applied: list[ConversionRecord] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        """Number of telemetry observations in the dataset."""
        return self.canonical_df.height

    @property
    def column_count(self) -> int:
        """Number of columns in the canonical telemetry dataset."""
        return self.canonical_df.width

    @property
    def telemetry_roles(self) -> list[str]:
        """List of canonical HVAC telemetry roles present in the dataset."""
        return [f.role for f in self.schema.telemetry_fields if f.role is not None]

    def get_telemetry_series(self, role: str) -> pl.Series | None:
        """Lookup canonical telemetry Series by role name."""
        if role in self.canonical_df.columns:
            return self.canonical_df[role]
        return None

    def get_unmapped_df(self) -> pl.DataFrame:
        """
        Return a DataFrame containing only the raw source columns that were NOT
        mapped into the canonical telemetry table.
        """
        unmapped_cols = [u.source_column for u in self.schema.unmapped_channels if u.source_column in self.source_df.columns]
        if not unmapped_cols:
            return pl.DataFrame()
        return self.source_df.select(unmapped_cols)

    def to_dict(self) -> dict[str, Any]:
        """
        Produce a JSON-serializable summary of the transformation result.
        """
        return {
            "file_name": self.file_name,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "timestamp_column": self.timestamp_column,
            "equipment_id_column": self.equipment_id_column,
            "sampling_interval_seconds": self.sampling_interval_seconds,
            "rows_duped": self.rows_duped,
            "telemetry_roles": self.telemetry_roles,
            "fields": [
                {
                    "name": f.name,
                    "role": f.role,
                    "dtype": f.dtype,
                    "unit": f.unit,
                    "source_column": f.source_column,
                    "source_dtype": f.source_dtype,
                    "source_unit": f.source_unit,
                    "conversion_applied": f.conversion_applied,
                    "is_metadata": f.is_metadata,
                }
                for f in self.schema.fields
            ],
            "unmapped_channels": [
                {
                    "source_column": u.source_column,
                    "source_dtype": u.source_dtype,
                    "unit": u.unit,
                    "column_category": u.column_category,
                    "reason": u.reason,
                }
                for u in self.schema.unmapped_channels
            ],
            "conversions": [
                {
                    "source_column": c.source_column,
                    "canonical_role": c.canonical_role,
                    "source_unit": c.source_unit,
                    "canonical_unit": c.canonical_unit,
                    "formula": c.formula,
                }
                for c in self.conversions_applied
            ],
        }


# ============================================================
# PRIMARY TRANSFORMATION LOGIC
# ============================================================

def transform_to_canonical(
    raw_df: pl.DataFrame,
    mapping_result: MappingResult,
    *,
    preflight_report: dict | None = None,
    file_name: str | None = None,
    file_path: str | None = None,
    default_equipment_id: str | None = None,
) -> CanonicalTransformResult:
    """
    Transform a raw HVAC CSV DataFrame and its resolved semantic mapping into
    a clean canonical telemetry dataset.

    Pipeline:
    1. Extracts and canonicalizes the temporal coordinate (`timestamp_utc`).
    2. Identifies or constructs the equipment identifier (`equipment_id`).
    3. Transforms each mapped canonical role:
       - Sanitizes numeric values safely.
       - Applies detected physical unit conversions (e.g. °C -> °F, Pa -> in_wc).
       - Casts to uniform Float64 telemetry columns.
    4. Catalogs all unmapped source columns as traceable `UnmappedChannel` records.
    5. Assembles a clean `canonical_df` and structured `CanonicalSchema`.

    Args:
        raw_df: Original unmodified Polars DataFrame from CSV.
        mapping_result: Final resolved MappingResult from the mapping engine.
        preflight_report: Optional preflight report (if pre-computed).
        file_name: Name of the CSV file.
        file_path: Path to the CSV file.
        default_equipment_id: Fallback equipment ID if no equipment column exists.

    Returns:
        CanonicalTransformResult with canonical DataFrame, schema, conversions, and traceability.
    """
    # 1. Identify Timestamp Column & Canonicalize
    timestamp_col = (
        preflight_report.get("timestamp_column")
        if preflight_report
        else find_timestamp_column(raw_df.columns)
    )

    canonical_series_list: list[pl.Series] = []
    canonical_fields: list[CanonicalField] = []
    applied_conversions: list[ConversionRecord] = []
    used_source_columns: set[str] = set()

    if timestamp_col is not None and timestamp_col in raw_df.columns:
        raw_ts = raw_df[timestamp_col]
        parsed_ts = parse_timestamp_series(raw_ts).alias("timestamp_utc")
        canonical_series_list.append(parsed_ts)
        # Preserve original raw timestamp string as auxiliary metadata column (Issue 06)
        raw_ts_str = raw_ts.cast(pl.Utf8).alias("timestamp_raw")
        canonical_series_list.append(raw_ts_str)
        used_source_columns.add(timestamp_col)

        canonical_fields.append(
            CanonicalField(
                name="timestamp_utc",
                role=None,
                dtype=str(parsed_ts.dtype),
                unit=None,
                source_column=timestamp_col,
                source_dtype=str(raw_ts.dtype),
                source_unit=None,
                conversion_applied="datetime_parsed",
                is_metadata=True,
            )
        )
        canonical_fields.append(
            CanonicalField(
                name="timestamp_raw",
                role=None,
                dtype=str(raw_ts_str.dtype),
                unit=None,
                source_column=timestamp_col,
                source_dtype=str(raw_ts.dtype),
                source_unit=None,
                conversion_applied="raw_preserved",
                is_metadata=True,
            )
        )

    # 2. Identify Equipment ID & Canonicalize
    equipment_col = _find_equipment_column(raw_df.columns)
    eq_id_value = default_equipment_id or (Path(file_name).stem if file_name else "UNKNOWN_EQUIPMENT")

    if equipment_col is not None and equipment_col in raw_df.columns:
        eq_series = raw_df[equipment_col].cast(pl.Utf8).alias("equipment_id")
        canonical_series_list.append(eq_series)
        used_source_columns.add(equipment_col)

        canonical_fields.append(
            CanonicalField(
                name="equipment_id",
                role=None,
                dtype=str(eq_series.dtype),
                unit=None,
                source_column=equipment_col,
                source_dtype=str(raw_df[equipment_col].dtype),
                source_unit=None,
                conversion_applied=None,
                is_metadata=True,
            )
        )
    else:
        # Construct equipment_id column from default or file context
        eq_series = pl.Series(
            name="equipment_id",
            values=[eq_id_value] * raw_df.height,
            dtype=pl.Utf8,
        )
        canonical_series_list.append(eq_series)
        canonical_fields.append(
            CanonicalField(
                name="equipment_id",
                role=None,
                dtype=str(eq_series.dtype),
                unit=None,
                source_column="[SYNTHESIZED_OR_INFERRED]",
                source_dtype="String",
                source_unit=None,
                conversion_applied=None,
                is_metadata=True,
            )
        )

    # 3. Transform Mapped Canonical HVAC Roles
    # Sort roles for deterministic canonical output schema ordering
    sorted_roles = sorted(mapping_result.mappings.keys())

    for role in sorted_roles:
        resolved = mapping_result.mappings[role]
        src_col = resolved.source_column

        if src_col not in raw_df.columns:
            continue

        raw_series = raw_df[src_col]
        used_source_columns.add(src_col)

        # Check if role is categorical text (e.g. occ_mode, schedule) with non-numeric source
        is_categorical = role in ("occ_mode", "occupancy", "schedule", "mode", "equip_mode")
        if is_categorical and raw_series.dtype in (pl.Utf8, pl.String, pl.Categorical):
            final_series = raw_series.cast(pl.Utf8).str.strip_chars().alias(role)
            conversion_formula = None
            source_unit = None
            canonical_unit = None
        else:
            # Sanitize values to clean Float64
            clean_numeric = _sanitize_numeric_series(raw_series)

            # Detect physical units
            source_unit = _infer_source_unit(src_col)
            canonical_unit = CANONICAL_ROLE_UNITS.get(role)

            # Apply unit conversion if detected
            converted_series, conversion_formula = apply_unit_conversion(
                clean_numeric,
                source_unit=source_unit,
                canonical_unit=canonical_unit,
            )

            final_series = converted_series.alias(role)

        canonical_series_list.append(final_series)

        if conversion_formula and source_unit and canonical_unit:
            applied_conversions.append(
                ConversionRecord(
                    source_column=src_col,
                    canonical_role=role,
                    source_unit=source_unit,
                    canonical_unit=canonical_unit,
                    formula=conversion_formula,
                )
            )

        canonical_fields.append(
            CanonicalField(
                name=role,
                role=role,
                dtype=str(final_series.dtype),
                unit=canonical_unit,
                source_column=src_col,
                source_dtype=str(raw_series.dtype),
                source_unit=source_unit,
                conversion_applied=conversion_formula,
                is_metadata=False,
            )
        )

    # 4. Catalog Unmapped Channels for Full Traceability
    conflict_losers = {c.loser_column for c in mapping_result.conflicts}
    unmapped_channels: list[UnmappedChannel] = []

    for col_name in raw_df.columns:
        if col_name in used_source_columns:
            continue

        src_series = raw_df[col_name]
        source_unit = _infer_source_unit(col_name)
        col_cat = _classify_column_category(
            col_name,
            mapped=False,
            is_conflict=col_name in conflict_losers,
        )

        if col_name in conflict_losers:
            reason = "Demoted / rejected due to lower confidence score."
        elif col_cat == "TEMPORAL_METADATA":
            reason = "Secondary temporal metadata channel."
        elif col_cat == "TOPOLOGY_METADATA":
            reason = "Secondary topology / device identifier metadata channel."
        elif col_cat == "BENCHMARK_METADATA":
            reason = "Diagnostic ground-truth benchmark evaluation label."
        elif col_cat == "AUXILIARY_BMS":
            reason = "Supervisory / auxiliary BMS operational signal."
        else:
            reason = "No matching canonical HVAC rule in Open-FDD catalog."

        unmapped_channels.append(
            UnmappedChannel(
                source_column=col_name,
                source_dtype=str(src_series.dtype),
                unit=source_unit,
                column_category=col_cat,
                reason=reason,
            )
        )

    # 5. Assemble Final Canonical DataFrame & Schema
    canonical_df = pl.DataFrame(canonical_series_list)

    # 5a. Deduplicate by timestamp_utc (Keep Last row per Open-FDD semantics)
    rows_duped = 0
    if "timestamp_utc" in canonical_df.columns and canonical_df.height > 0:
        initial_count = canonical_df.height
        if "equipment_id" in canonical_df.columns:
            canonical_df = canonical_df.unique(subset=["equipment_id", "timestamp_utc"], keep="last").sort("timestamp_utc")
        else:
            canonical_df = canonical_df.unique(subset=["timestamp_utc"], keep="last").sort("timestamp_utc")
        rows_duped = initial_count - canonical_df.height

    schema = CanonicalSchema(
        fields=canonical_fields,
        unmapped_channels=unmapped_channels,
        conversions=applied_conversions,
    )

    # 6. Resolve sampling interval from preflight report or timestamp differences
    sampling_interval = None
    if preflight_report:
        sampling_interval = (
            preflight_report.get("median_sampling_seconds")
            or preflight_report.get("sampling_interval_seconds")
            or preflight_report.get("median_sampling_interval_seconds")
        )
    if sampling_interval is None and "timestamp_utc" in canonical_df.columns and canonical_df.height > 1:
        try:
            diffs = canonical_df["timestamp_utc"].diff().dt.total_seconds()
            pos = diffs.filter(diffs > 0)
            if not pos.is_empty():
                sampling_interval = float(pos.median())
        except Exception:
            sampling_interval = None

    return CanonicalTransformResult(
        canonical_df=canonical_df,
        source_df=raw_df,
        schema=schema,
        mapping_result=mapping_result,
        file_path=file_path,
        file_name=file_name,
        timestamp_column=timestamp_col,
        equipment_id_column=equipment_col,
        sampling_interval_seconds=float(sampling_interval) if sampling_interval is not None and sampling_interval > 0 else None,
        rows_duped=rows_duped,
        conversions_applied=applied_conversions,
    )


def transform_csv_canonical(
    file_path: str | Path,
    *,
    default_equipment_id: str | None = None,
) -> CanonicalTransformResult:
    """
    Convenience function to inspect, preflight, map, and transform a CSV file
    directly into a canonical telemetry dataset.

    Args:
        file_path: Path to the target CSV file.
        default_equipment_id: Optional fallback equipment ID.

    Returns:
        CanonicalTransformResult with canonical DataFrame and schema.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    if path.suffix.lower() != ".csv":
        raise ValueError(f"Expected a CSV file, got: {path.suffix}")

    # 1. Preflight validation & Read raw CSV
    preflight_report = preflight_csv(path)
    raw_df = pl.read_csv(path)

    # 2. Semantic role mapping
    mapping_result = map_columns(raw_df.columns)

    # 3. Canonical data transformation
    return transform_to_canonical(
        raw_df=raw_df,
        mapping_result=mapping_result,
        preflight_report=preflight_report,
        file_name=path.name,
        file_path=str(path),
        default_equipment_id=default_equipment_id,
    )
