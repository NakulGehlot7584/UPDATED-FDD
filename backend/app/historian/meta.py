"""
Historian sidecar metadata models and provenance tracking.

Source of Truth:
- Official Open-FDD sidecar contract: `crates/fdd_store/src/meta.rs`
- Ingest reporting: `crates/fdd_store/src/ingest.rs`

Design Principles:
1. Complete Provenance: Every persisted partition file is paired with an audit sidecar
   recording the source CSV path, file size, modification timestamp, SHA256 checksum,
   row count, timestamp extent, and column inventory.
2. Crash-Safe Serialization: Sidecar metadata is stored as JSON alongside the Parquet file.
3. Fast Metadata Queries: Equipment and dataset summaries can be queried without
   scanning massive Parquet tables.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


def compute_file_fingerprint(path: str | Path) -> tuple[int, float, str]:
    """
    Compute (size_bytes, mtime_unix, sha256_hex) for a source file.
    """
    p = Path(path)
    if not p.exists():
        return 0, 0.0, ""

    stat = p.stat()
    size = stat.st_size
    mtime = stat.st_mtime

    hasher = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    sha256 = hasher.hexdigest()

    return size, mtime, sha256


@dataclass(frozen=True)
class HistorianSidecarMeta:
    """
    Provenance and structural metadata for a persisted Parquet equipment partition.
    """

    building_id: str
    equipment_id: str
    source_file: str
    source_size_bytes: int
    source_modified_unix: float
    source_sha256: str
    parquet_path: str
    row_count: int
    min_timestamp: str | None
    max_timestamp: str | None
    telemetry_roles: list[str]
    generated_at: str
    sampling_interval_seconds: float = 300.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistorianSidecarMeta:
        return cls(
            building_id=data.get("building_id", "DEFAULT_BUILDING"),
            equipment_id=data.get("equipment_id", "UNKNOWN_EQUIPMENT"),
            source_file=data.get("source_file", ""),
            source_size_bytes=data.get("source_size_bytes", 0),
            source_modified_unix=data.get("source_modified_unix", 0.0),
            source_sha256=data.get("source_sha256", ""),
            parquet_path=data.get("parquet_path", ""),
            row_count=data.get("row_count", 0),
            min_timestamp=data.get("min_timestamp"),
            max_timestamp=data.get("max_timestamp"),
            telemetry_roles=data.get("telemetry_roles", []),
            generated_at=data.get("generated_at", datetime.now(timezone.utc).isoformat()),
            sampling_interval_seconds=float(data.get("sampling_interval_seconds", 300.0)),
        )

    def write_to(self, path: Path) -> None:
        """Write sidecar metadata to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def read_from(cls, path: Path) -> HistorianSidecarMeta | None:
        """Read sidecar metadata from JSON file."""
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception:
            return None


@dataclass(frozen=True)
class EquipmentSummary:
    """
    Summary descriptor for an individual equipment stored in the historian.
    """

    equipment_id: str
    building_id: str
    row_count: int
    min_timestamp: str | None
    max_timestamp: str | None
    telemetry_roles: list[str]
    parquet_file: str
    file_size_bytes: int
    last_updated: str


@dataclass(frozen=True)
class HistorianSummary:
    """
    High-level metrics and inventory of all equipment currently stored in the historian.
    """

    total_equipment: int
    total_rows: int
    total_bytes: int
    buildings: list[str]
    global_min_timestamp: str | None
    global_max_timestamp: str | None
    equipment_list: list[EquipmentSummary] = field(default_factory=list)
