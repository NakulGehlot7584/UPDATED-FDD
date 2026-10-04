"""
Historian reader engine: queries historical telemetry from Parquet partitions into Polars DataFrames and Arrow Tables.

Source of Truth:
- Storage layout: `app.historian.storage.HistorianStorage`
- Schema definitions: `app.historian.schema`
- Sidecar metadata: `app.historian.meta.HistorianSidecarMeta`

Design Principles:
1. Fast Column Projection: Supports reading subsets of telemetry roles for high performance.
2. Predicate Pushdown: Supports time-range filtering (`start_time`, `end_time`).
3. Zero-Copy Arrow Export: Exposes native PyArrow Tables for upcoming DataFusion queries.
4. Flexible Aggregation: Provides methods to read a single equipment or all equipment across a building.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from app.historian.meta import HistorianSidecarMeta
from app.historian.storage import HistorianStorage


def read_equipment_telemetry(
    building_id: str,
    equipment_id: str,
    *,
    storage: HistorianStorage | None = None,
    columns: list[str] | None = None,
    start_time: datetime | str | None = None,
    end_time: datetime | str | None = None,
) -> pl.DataFrame:
    """
    Read canonical historical telemetry for an equipment into a Polars DataFrame.

    Args:
        building_id: Building / facility identifier.
        equipment_id: Equipment identifier.
        storage: Optional HistorianStorage instance.
        columns: Optional list of canonical columns to project.
        start_time: Optional start timestamp filter (inclusive).
        end_time: Optional end timestamp filter (inclusive).

    Returns:
        Polars DataFrame containing the queried telemetry rows.
    """
    store = storage or HistorianStorage()
    pq_path = store.get_parquet_path(building_id, equipment_id)

    if not pq_path.is_file():
        return pl.DataFrame()

    df = pl.read_parquet(pq_path, columns=columns)

    # Apply time range filtering if requested
    if "timestamp_utc" in df.columns:
        if start_time is not None:
            if isinstance(start_time, str):
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00")).replace(tzinfo=None)
            else:
                start_dt = start_time.replace(tzinfo=None) if getattr(start_time, "tzinfo", None) else start_time
            df = df.filter(pl.col("timestamp_utc") >= start_dt)

        if end_time is not None:
            if isinstance(end_time, str):
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00")).replace(tzinfo=None)
            else:
                end_dt = end_time.replace(tzinfo=None) if getattr(end_time, "tzinfo", None) else end_time
            df = df.filter(pl.col("timestamp_utc") <= end_dt)

    return df


def read_equipment_arrow_table(
    building_id: str,
    equipment_id: str,
    *,
    storage: HistorianStorage | None = None,
    columns: list[str] | None = None,
) -> pa.Table | None:
    """
    Read canonical historical telemetry directly into an in-memory PyArrow Table.
    """
    store = storage or HistorianStorage()
    pq_path = store.get_parquet_path(building_id, equipment_id)

    if not pq_path.is_file():
        return None

    return pq.read_table(pq_path, columns=columns)


def read_all_telemetry(
    building_id: str | None = None,
    *,
    storage: HistorianStorage | None = None,
    columns: list[str] | None = None,
) -> pl.DataFrame:
    """
    Read and concatenate historical telemetry across all equipment in a building (or entire historian).
    """
    store = storage or HistorianStorage()
    partitions = store.list_equipment_partitions()

    if building_id is not None:
        partitions = [p for p in partitions if p[0] == building_id]

    if not partitions:
        return pl.DataFrame()

    frames: list[pl.DataFrame] = []
    for b_id, eq_id, pq_path in partitions:
        df = pl.read_parquet(pq_path, columns=columns)
        if not df.is_empty():
            frames.append(df)

    if not frames:
        return pl.DataFrame()

    return pl.concat(frames, how="diagonal_relaxed")


def get_equipment_meta(
    building_id: str,
    equipment_id: str,
    *,
    storage: HistorianStorage | None = None,
) -> HistorianSidecarMeta | None:
    """
    Retrieve sidecar metadata for an equipment partition.
    """
    store = storage or HistorianStorage()
    meta_path = store.get_meta_path(building_id, equipment_id)
    return HistorianSidecarMeta.read_from(meta_path)
