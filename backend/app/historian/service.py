"""
High-level service interface for Open-FDD Historian operations.

Source of Truth:
- Writer: `app.historian.writer.write_canonical_telemetry_to_historian`
- Reader: `app.historian.reader`
- Storage: `app.historian.storage.HistorianStorage`
- Metadata: `app.historian.meta`

Design Principles:
1. Single Entrypoint: Provides clean operational methods for ingestion, querying, and auditing.
2. Fast Summaries: Aggregates equipment counts, row totals, byte sizes, and timestamp extents.
3. Thread-Safe: Stateless delegation to crash-safe storage operations.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow as pa

from app.historian.meta import (
    EquipmentSummary,
    HistorianSidecarMeta,
    HistorianSummary,
)
from app.historian.reader import (
    get_equipment_meta,
    read_all_telemetry,
    read_equipment_arrow_table,
    read_equipment_telemetry,
)
from app.historian.storage import HistorianStorage
from app.historian.writer import write_canonical_telemetry_to_historian
from app.transformation.canonical import CanonicalTransformResult


class HistorianService:
    """
    Central operational service for the Open-FDD Parquet/Arrow Historian.
    """

    def __init__(self, storage: HistorianStorage | None = None) -> None:
        self.storage = storage or HistorianStorage()

    def ingest_canonical_result(
        self,
        canonical_result: CanonicalTransformResult,
        *,
        building_id: str = "DEFAULT_BUILDING",
        default_equipment_id: str | None = None,
    ) -> list[HistorianSidecarMeta]:
        """
        Ingest a CanonicalTransformResult into partitioned Parquet storage.
        """
        return write_canonical_telemetry_to_historian(
            canonical_result=canonical_result,
            storage=self.storage,
            building_id=building_id,
            default_equipment_id=default_equipment_id,
        )

    def list_equipment(self) -> list[EquipmentSummary]:
        """
        Return summary descriptors for all equipment partitions stored in the historian.
        """
        partitions = self.storage.list_equipment_partitions()
        summaries: list[EquipmentSummary] = []

        for bldg_id, equip_id, pq_path in partitions:
            meta = get_equipment_meta(bldg_id, equip_id, storage=self.storage)
            stat = pq_path.stat() if pq_path.exists() else None
            file_size = stat.st_size if stat else 0
            last_updated = meta.generated_at if meta else (datetime.fromtimestamp(stat.st_mtime).isoformat() if stat else "")

            if meta is not None:
                row_count = meta.row_count
                min_ts = meta.min_timestamp
                max_ts = meta.max_timestamp
                roles = meta.telemetry_roles
            else:
                # Fast fallback read if metadata sidecar is missing
                try:
                    df = pl.read_parquet(pq_path)
                    row_count = df.height
                    min_ts = str(df["timestamp_utc"].min()) if "timestamp_utc" in df.columns else None
                    max_ts = str(df["timestamp_utc"].max()) if "timestamp_utc" in df.columns else None
                    roles = [c for c in df.columns if c not in ("timestamp_utc", "equipment_id")]
                except Exception:
                    row_count = 0
                    min_ts = None
                    max_ts = None
                    roles = []

            summaries.append(
                EquipmentSummary(
                    equipment_id=equip_id,
                    building_id=bldg_id,
                    row_count=row_count,
                    min_timestamp=min_ts,
                    max_timestamp=max_ts,
                    telemetry_roles=roles,
                    parquet_file=str(pq_path),
                    file_size_bytes=file_size,
                    last_updated=last_updated,
                )
            )

        return summaries

    def get_summary(self) -> HistorianSummary:
        """
        Produce a high-level summary of all data currently stored in the historian.
        """
        equip_list = self.list_equipment()
        total_rows = sum(e.row_count for e in equip_list)
        total_bytes = sum(e.file_size_bytes for e in equip_list)
        buildings = sorted(list({e.building_id for e in equip_list}))

        all_min_ts = [e.min_timestamp for e in equip_list if e.min_timestamp]
        all_max_ts = [e.max_timestamp for e in equip_list if e.max_timestamp]

        global_min = min(all_min_ts) if all_min_ts else None
        global_max = max(all_max_ts) if all_max_ts else None

        return HistorianSummary(
            total_equipment=len(equip_list),
            total_rows=total_rows,
            total_bytes=total_bytes,
            buildings=buildings,
            global_min_timestamp=global_min,
            global_max_timestamp=global_max,
            equipment_list=equip_list,
        )

    def get_telemetry(
        self,
        building_id: str,
        equipment_id: str,
        *,
        columns: list[str] | None = None,
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
    ) -> pl.DataFrame:
        """
        Read historical telemetry for a given equipment.
        """
        return read_equipment_telemetry(
            building_id=building_id,
            equipment_id=equipment_id,
            storage=self.storage,
            columns=columns,
            start_time=start_time,
            end_time=end_time,
        )

    def get_arrow_table(
        self,
        building_id: str,
        equipment_id: str,
        *,
        columns: list[str] | None = None,
    ) -> pa.Table | None:
        """
        Read historical telemetry directly as a PyArrow Table.
        """
        return read_equipment_arrow_table(
            building_id=building_id,
            equipment_id=equipment_id,
            storage=self.storage,
            columns=columns,
        )

    def delete_equipment(self, building_id: str, equipment_id: str) -> bool:
        """
        Delete an equipment partition.
        """
        return self.storage.delete_equipment(building_id, equipment_id)

    def clear(self) -> None:
        """
        Clear all historian partitions.
        """
        self.storage.clear_all()
