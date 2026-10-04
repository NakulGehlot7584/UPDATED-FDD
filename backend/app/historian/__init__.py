"""
Canonical Arrow/Parquet Historian storage layer for Open-FDD.
"""

from __future__ import annotations

from app.historian.meta import (
    EquipmentSummary,
    HistorianSidecarMeta,
    HistorianSummary,
    compute_file_fingerprint,
)
from app.historian.reader import (
    get_equipment_meta,
    read_all_telemetry,
    read_equipment_arrow_table,
    read_equipment_telemetry,
)
from app.historian.schema import (
    UTF8_CANONICAL_ROLES,
    build_arrow_schema_from_columns,
    get_arrow_type_for_role,
    get_polars_type_for_role,
)
from app.historian.service import HistorianService
from app.historian.storage import (
    DEFAULT_HISTORIAN_DIR,
    HistorianStorage,
    sanitize_partition_token,
)
from app.historian.writer import write_canonical_telemetry_to_historian

__all__ = [
    "DEFAULT_HISTORIAN_DIR",
    "EquipmentSummary",
    "HistorianService",
    "HistorianSidecarMeta",
    "HistorianStorage",
    "HistorianSummary",
    "UTF8_CANONICAL_ROLES",
    "build_arrow_schema_from_columns",
    "compute_file_fingerprint",
    "get_arrow_type_for_role",
    "get_equipment_meta",
    "get_polars_type_for_role",
    "read_all_telemetry",
    "read_equipment_arrow_table",
    "read_equipment_telemetry",
    "sanitize_partition_token",
    "write_canonical_telemetry_to_historian",
]
