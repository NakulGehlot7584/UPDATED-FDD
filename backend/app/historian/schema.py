"""
Canonical Arrow and Polars schema definitions for Open-FDD Historian storage.

Source of Truth:
- Official Open-FDD historian schema: `crates/fdd_store/src/ingest.rs`
- Open-FDD canonical role catalog: `app.mapping.roles.CANONICAL_ROLES`
- Canonical transformation schema: `app.transformation.schema.CanonicalSchema`

Design Principles:
1. Strong Arrow Types:
   - `timestamp_utc`: Timestamp(Microsecond or Nanosecond, UTC/None) / Datetime
   - `equipment_id`: Utf8 (String)
   - Continuous sensors, setpoints, commands: Float64
   - Categorical status / schedule modes: Utf8 (String) or Float64
2. DataFusion Ready: Output Arrow schemas are 100% compliant with standard Arrow IPC and DataFusion table providers.
3. Zero Loss: Retains all mapped canonical HVAC roles in standard lowercase snake_case naming.
"""

from __future__ import annotations

import pyarrow as pa
import polars as pl

# Roles that are treated as categorical text in Open-FDD (matches crates/fdd_store/src/ingest.rs:is_utf8_role)
UTF8_CANONICAL_ROLES: frozenset[str] = frozenset({
    "occ_mode",
    "occupancy",
    "schedule",
    "mode",
    "equip_mode",
})


def get_arrow_type_for_role(role_name: str) -> pa.DataType:
    """
    Return the official PyArrow DataType for a given canonical role or column name.
    """
    if role_name == "timestamp_utc":
        return pa.timestamp("us")
    if role_name in ("equipment_id", "building_id", "site_id", "timestamp_raw"):
        return pa.string()
    if role_name in UTF8_CANONICAL_ROLES:
        return pa.string()
    return pa.float64()


def get_polars_type_for_role(role_name: str) -> pl.DataType:
    """
    Return the official Polars DataType for a given canonical role or column name.
    """
    if role_name == "timestamp_utc":
        return pl.Datetime("us")
    if role_name in ("equipment_id", "building_id", "site_id", "timestamp_raw"):
        return pl.Utf8
    if role_name in UTF8_CANONICAL_ROLES:
        return pl.Utf8
    return pl.Float64


def build_arrow_schema_from_columns(column_names: list[str]) -> pa.Schema:
    """
    Construct a PyArrow Schema for a given list of canonical column names.
    """
    fields: list[pa.Field] = []

    # Ensure timestamp_utc is first if present
    ordered_names = ["timestamp_utc"] if "timestamp_utc" in column_names else []
    if "equipment_id" in column_names and "equipment_id" not in ordered_names:
        ordered_names.append("equipment_id")

    for col in column_names:
        if col not in ordered_names:
            ordered_names.append(col)

    for col in ordered_names:
        nullable = col not in ("timestamp_utc", "equipment_id")
        fields.append(pa.field(col, get_arrow_type_for_role(col), nullable=nullable))

    return pa.schema(fields)
