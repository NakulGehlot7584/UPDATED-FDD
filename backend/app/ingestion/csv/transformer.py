"""
Generic CSV transformation and canonicalization layer for the FDD pipeline.

Source of Truth:
- Ingestion inspection: `app.ingestion.csv.scanner.scan_csv`
- Validation preflight: `app.validation.preflight.preflight_csv`
- Semantic role mapping: `app.mapping.mapper.map_columns`
- Canonical role catalog: `app.mapping.roles.CANONICAL_ROLES`

Design Principles:
1. Pure Orchestration: Connects scanner, preflight, and mapping without embedding
   dataset-specific heuristics, fault calculations, or vendor assumptions.
2. Complete Inspection Metadata: Produces a structured `ColumnInspection` for every
   source column detailing canonical role, data type, physical units, conversion needs,
   and evidence rationale.
3. Safe Canonicalization: Renames mapped columns to canonical role names ONLY when
   explicitly requested (`canonicalize_names=True`), while preserving all unmapped
   metadata channels and detecting naming collisions.
4. Non-Destructive: Never modifies original CSV files on disk or mutates inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import polars as pl

from app.ingestion.csv.scanner import scan_csv
from app.mapping.mapper import MappingResult, map_columns
from app.mapping.normalizer import normalize_column_name
from app.mapping.roles import CANONICAL_ROLES
from app.validation.preflight import preflight_csv
from app.transformation.units import (
    CANONICAL_ROLE_UNITS,
    _classify_column_category,
    _infer_source_unit,
    _is_conversion_required,
)


# ============================================================
# INSPECTION & RESULT DATACLASSES
# ============================================================

@dataclass(frozen=True)
class ColumnInspection:
    """
    Diagnostic and canonicalization metadata for a single source column.
    """

    source_column: str
    canonical_role: str | None
    source_dtype: str | None
    unit: str | None
    canonical_unit: str | None
    conversion_required: bool
    mapping_score: int | None
    matched_pattern: str | None
    mapping_reason: str | None
    mapped: bool
    column_category: str = "CANONICAL_SIGNAL"


@dataclass(frozen=True)
class DatasetTransformResult:
    """
    Container presenting the complete CSV inspection, preflight health,
    semantic role mapping, and transformed Polars DataFrame.
    """

    file_path: str
    file_name: str
    dataframe: pl.DataFrame
    scan_report: dict
    preflight_report: dict
    mapping_result: MappingResult
    columns: list[ColumnInspection] = field(default_factory=list)

    @property
    def mapped_column_count(self) -> int:
        """Number of source columns successfully mapped to canonical roles."""
        return self.mapping_result.mapped_role_count

    @property
    def unmapped_column_count(self) -> int:
        """Number of source columns not mapped to any canonical role."""
        return self.mapping_result.unmapped_column_count

    @property
    def mapping_coverage(self) -> float:
        """Ratio of mapped columns to total source columns."""
        total = len(self.columns)
        if total == 0:
            return 0.0
        return self.mapped_column_count / total

    def get_mapping(self, source_column: str) -> ColumnInspection | None:
        """Lookup inspection record for a specific source column."""
        for col in self.columns:
            if col.source_column == source_column:
                return col
        return None

    def get_role_column(self, role: str) -> str | None:
        """Lookup source column assigned to a canonical role."""
        return self.mapping_result.get_column_for_role(role)

    def to_canonical(
        self,
        default_equipment_id: str | None = None,
    ):
        """
        Produce a clean in-memory canonical telemetry dataset from this transform result.
        """
        from app.transformation.canonical import transform_to_canonical

        return transform_to_canonical(
            raw_df=self.dataframe,
            mapping_result=self.mapping_result,
            preflight_report=self.preflight_report,
            file_name=self.file_name,
            file_path=self.file_path,
            default_equipment_id=default_equipment_id,
        )


# ============================================================
# PRIMARY TRANSFORMATION FUNCTION
# ============================================================

def transform_csv(
    file_path: str | Path,
    *,
    canonicalize_names: bool = False,
) -> DatasetTransformResult:
    """
    Inspect, validate, and optionally canonicalize a CSV dataset.

    Pipeline steps:
    1. Reads CSV using Polars without mutating the original file.
    2. Runs structural scan (`scan_csv`) and preflight timestamp checks (`preflight_csv`).
    3. Executes generic role mapping (`map_columns`).
    4. Builds detailed `ColumnInspection` metadata for every source column.
    5. When `canonicalize_names=True` and preflight passes, renames mapped columns to
       their canonical role names while preserving all unmapped metadata columns.

    Args:
        file_path: Path to the target CSV file.
        canonicalize_names: If True, mapped columns in the returned DataFrame are renamed
                           to canonical role IDs. Defaults to False.

    Returns:
        DatasetTransformResult containing the DataFrame, scan report, preflight report,
        mapping result, and column inspections.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    if path.suffix.lower() != ".csv":
        raise ValueError(f"Expected a CSV file, got: {path.suffix}")

    # 1. Structural inspection & Preflight validation
    scan_report = scan_csv(path)
    preflight_report = preflight_csv(path)

    # 2. Read raw DataFrame
    df = pl.read_csv(path)
    if df.height == 0:
        raise ValueError(f"CSV file '{path.name}' contains no data rows (empty or header-only).")

    # 3. Execute semantic role mapping
    mapping_result = map_columns(df.columns)

    # Reject files with no timestamp AND no mapped telemetry roles
    if preflight_report.get("timestamp_column") is None and mapping_result.mapped_role_count == 0:
        raise ValueError(
            f"CSV file '{path.name}' contains no recognized timestamp or HVAC telemetry columns."
        )

    # 4. Build ColumnInspection for EVERY source column
    dtypes_map = {col["name"]: col["dtype"] for col in scan_report.get("columns", [])}
    conflict_losers = {c.loser_column for c in mapping_result.conflicts}
    inspections: list[ColumnInspection] = []

    for col_name in df.columns:
        role = mapping_result.get_role_for_column(col_name)
        source_dtype = dtypes_map.get(col_name, str(df[col_name].dtype))
        source_unit = _infer_source_unit(col_name)
        col_cat = _classify_column_category(
            col_name,
            mapped=role is not None,
            is_conflict=col_name in conflict_losers,
        )

        if role is not None:
            canonical_unit = CANONICAL_ROLE_UNITS.get(role)
            conversion_req = _is_conversion_required(source_unit, canonical_unit)
            res_mapping = mapping_result.mappings.get(role)

            inspections.append(
                ColumnInspection(
                    source_column=col_name,
                    canonical_role=role,
                    source_dtype=source_dtype,
                    unit=source_unit,
                    canonical_unit=canonical_unit,
                    conversion_required=conversion_req,
                    mapping_score=res_mapping.score if res_mapping else None,
                    matched_pattern=res_mapping.matched_pattern if res_mapping else None,
                    mapping_reason=res_mapping.reason if res_mapping else None,
                    mapped=True,
                    column_category=col_cat,
                )
            )
        else:
            if col_cat == "TEMPORAL_METADATA":
                default_reason = "Time-series index / temporal coordinate; intentionally excluded from HVAC telemetry roles."
            elif col_cat == "TOPOLOGY_METADATA":
                default_reason = "Equipment / topology identifier; handled as asset context."
            elif col_cat == "BENCHMARK_METADATA":
                default_reason = "Diagnostic ground-truth benchmark evaluation label."
            elif col_cat == "AUXILIARY_BMS":
                default_reason = "Supervisory / auxiliary BMS operational signal."
            elif col_name in conflict_losers:
                default_reason = "Demoted / rejected due to lower confidence score."
            else:
                default_reason = "No matching canonical HVAC rule in Open-FDD catalog."

            inspections.append(
                ColumnInspection(
                    source_column=col_name,
                    canonical_role=None,
                    source_dtype=source_dtype,
                    unit=source_unit,
                    canonical_unit=None,
                    conversion_required=False,
                    mapping_score=None,
                    matched_pattern=None,
                    mapping_reason=default_reason,
                    mapped=False,
                    column_category=col_cat,
                )
            )

    # 5. Handle optional canonical renaming
    output_df = df

    if canonicalize_names and preflight_report.get("valid", False):
        rename_dict: dict[str, str] = {}
        existing_cols = set(df.columns)

        for role, resolved in mapping_result.mappings.items():
            src_col = resolved.source_column
            if src_col != role:
                # Collision guard: check if target role name exists as another unmapped column
                if role in existing_cols and role not in [
                    r.source_column for r in mapping_result.mappings.values()
                ]:
                    raise ValueError(
                        f"Canonicalization collision: cannot rename source column '{src_col}' to '{role}' "
                        f"because column '{role}' already exists in source dataset."
                    )
                rename_dict[src_col] = role

        if rename_dict:
            output_df = df.rename(rename_dict)

    return DatasetTransformResult(
        file_path=str(path),
        file_name=path.name,
        dataframe=output_df,
        scan_report=scan_report,
        preflight_report=preflight_report,
        mapping_result=mapping_result,
        columns=inspections,
    )
