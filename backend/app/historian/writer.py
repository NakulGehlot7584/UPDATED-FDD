"""
Historian writer engine: transforms in-memory canonical telemetry into durable Parquet partitions.

Source of Truth:
- Official Open-FDD ingest: `crates/fdd_store/src/ingest.rs`
- Edge parquet bridge: `edge/src/csv_ingest/parquet_bridge.rs`
- Canonical schema: `app.historian.schema`
- Storage layout: `app.historian.storage.HistorianStorage`

Design Principles:
1. Multi-Equipment Support: If a canonical dataset contains multiple distinct `equipment_id`s,
   it automatically partitions and writes each equipment into its respective Hive directory.
2. Idempotent & Re-Import Safe: Overwrites / updates partition files atomically with zero risk
   of corruption or uncontrolled duplicated file sprawl.
3. Provenance Audited: Automatically computes file fingerprints and writes sidecar metadata.
4. Clean Arrow Data Types: `timestamp_utc` is preserved as TimestampMicrosecond, `equipment_id` as Utf8,
   and telemetry signals as Float64.
"""

from __future__ import annotations

from datetime import datetime, timezone
import io
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from app.historian.meta import HistorianSidecarMeta, compute_file_fingerprint
from app.historian.schema import build_arrow_schema_from_columns, get_arrow_type_for_role
from app.historian.storage import HistorianStorage
from app.transformation.canonical import CanonicalTransformResult


def write_canonical_telemetry_to_historian(
    canonical_result: CanonicalTransformResult,
    *,
    storage: HistorianStorage | None = None,
    building_id: str = "DEFAULT_BUILDING",
    default_equipment_id: str | None = None,
) -> list[HistorianSidecarMeta]:
    """
    Persist a CanonicalTransformResult into partitioned Parquet storage.

    Args:
        canonical_result: Clean in-memory CanonicalTransformResult from the transformation stage.
        storage: Optional HistorianStorage instance (uses default if None).
        building_id: Building / facility identifier for Hive partitioning.
        default_equipment_id: Fallback equipment ID if not present in DataFrame.

    Returns:
        List of HistorianSidecarMeta records for all equipment partitions written.
    """
    store = storage or HistorianStorage()
    df = canonical_result.canonical_df

    if df.is_empty():
        return []

    # 1. Identify equipment column and partition groups
    if "equipment_id" in df.columns:
        # Cast to string and drop nulls/empty
        unique_equip_ids = (
            df["equipment_id"]
            .drop_nulls()
            .cast(pl.Utf8)
            .unique()
            .to_list()
        )
    else:
        unique_equip_ids = []

    if not unique_equip_ids:
        unique_equip_ids = [default_equipment_id or canonical_result.equipment_id_column or "UNKNOWN_EQUIPMENT"]

    # 2. Compute source file fingerprints for provenance
    src_file = canonical_result.file_path or canonical_result.file_name or ""
    src_size, src_mtime, src_hash = compute_file_fingerprint(src_file) if src_file and Path(src_file).exists() else (0, 0.0, "")

    written_meta: list[HistorianSidecarMeta] = []

    # 3. Write each equipment partition
    for equip_id in unique_equip_ids:
        if "equipment_id" in df.columns:
            equip_df = df.filter(pl.col("equipment_id") == equip_id)
        else:
            equip_df = df.with_columns(pl.lit(equip_id).alias("equipment_id"))

        if equip_df.is_empty():
            continue

        # Sort chronologically by timestamp_utc
        if "timestamp_utc" in equip_df.columns:
            equip_df = equip_df.sort("timestamp_utc")
            min_ts_val = equip_df["timestamp_utc"].min()
            max_ts_val = equip_df["timestamp_utc"].max()
            min_ts = str(min_ts_val) if min_ts_val is not None else None
            max_ts = str(max_ts_val) if max_ts_val is not None else None
        else:
            min_ts = None
            max_ts = None

        # Build PyArrow schema
        column_names = equip_df.columns
        arrow_schema = build_arrow_schema_from_columns(column_names)

        # Convert Polars DataFrame to PyArrow Table with explicit casting
        pa_arrays = []
        for field in arrow_schema:
            col_name = field.name
            target_type = field.type
            s = equip_df[col_name]

            if target_type == pa.timestamp("us"):
                # Ensure Datetime
                if s.dtype != pl.Datetime:
                    s = s.cast(pl.Datetime)
                arr = s.to_arrow()
                # Cast to timestamp[us] if necessary
                if arr.type != target_type:
                    arr = arr.cast(target_type)
            elif target_type == pa.string():
                arr = s.cast(pl.Utf8).to_arrow()
            elif target_type == pa.float64():
                arr = s.cast(pl.Float64).to_arrow()
            else:
                arr = s.to_arrow().cast(target_type)

            pa_arrays.append(arr)

        pa_table = pa.Table.from_arrays(pa_arrays, schema=arrow_schema)

        # Write Parquet to in-memory buffer, then atomic publish
        buf = io.BytesIO()
        pq.write_table(
            pa_table,
            buf,
            compression="snappy",
            use_dictionary=True,
            version="2.6",
        )
        parquet_bytes = buf.getvalue()

        # Destination paths
        parquet_path = store.get_parquet_path(building_id, equip_id)
        meta_path = store.get_meta_path(building_id, equip_id)

        # Atomically write Parquet file
        store.write_atomic(parquet_path, parquet_bytes)

        # Extract telemetry roles (excluding timestamp_utc and equipment_id)
        telemetry_roles = [c for c in column_names if c not in ("timestamp_utc", "equipment_id", "building_id")]

        # Determine sampling interval from canonical result or timestamp diffs
        sampling_interval = canonical_result.sampling_interval_seconds
        if (sampling_interval is None or sampling_interval <= 0) and "timestamp_utc" in equip_df.columns and equip_df.height > 1:
            try:
                diffs = equip_df["timestamp_utc"].diff().dt.total_seconds()
                pos = diffs.filter(diffs > 0)
                if not pos.is_empty():
                    sampling_interval = float(pos.median())
            except Exception:
                pass
        if sampling_interval is None or sampling_interval <= 0:
            sampling_interval = 300.0

        # Write sidecar metadata
        meta = HistorianSidecarMeta(
            building_id=building_id,
            equipment_id=equip_id,
            source_file=str(src_file),
            source_size_bytes=src_size,
            source_modified_unix=src_mtime,
            source_sha256=src_hash,
            parquet_path=str(parquet_path),
            row_count=equip_df.height,
            min_timestamp=min_ts,
            max_timestamp=max_ts,
            telemetry_roles=telemetry_roles,
            generated_at=datetime.now(timezone.utc).isoformat(),
            sampling_interval_seconds=float(sampling_interval),
        )
        meta.write_to(meta_path)
        written_meta.append(meta)

    return written_meta
