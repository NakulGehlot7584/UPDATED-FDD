"""
Storage layout, partition resolution, and atomic filesystem operations for the Historian.

Source of Truth:
- Official Open-FDD partition hierarchy: `crates/fdd_store/src/historian.rs`
- Edge parquet layout: `edge/src/csv_ingest/parquet_bridge.rs`

Design Principles:
1. Standard Hive Partitioning:
   `building={building_id}/equipment={equipment_id}/history.parquet`
2. Safe Partition Token Sanitization: Prevents directory traversal attacks (`..`, `/`, `\\`).
3. Crash-Safe Atomic Publication: Writes parquet output to a hidden `.history.parquet.tmp-<pid>`
   file, flushes/syncs, then atomically renames to `history.parquet`.
4. Configurable Root: Defaults to `D:/fdd/data/historian` or `OPENFDD_PARQUET_ROOT` environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import tempfile


DEFAULT_HISTORIAN_DIR = Path(__file__).resolve().parents[3] / "data" / "historian"


def sanitize_partition_token(token: str, field_name: str = "partition") -> str:
    """
    Sanitize an identifier for safe use in directory names and Hive partition paths.
    """
    cleaned = token.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty")

    # Disallow path traversal characters
    if any(c in cleaned for c in ("/", "\\", "\0", "..", "=")):
        # Normalize disallowed characters into safe underscores
        cleaned = re.sub(r"[\/\\\0\=\.\s]+", "_", cleaned).strip("_")

    if not cleaned:
        cleaned = f"default_{field_name}"

    return cleaned


class HistorianStorage:
    """
    Manager for the physical Parquet historian storage layout on disk.
    """

    def __init__(self, root_dir: str | Path | None = None) -> None:
        if root_dir is not None:
            self.root_dir = Path(root_dir).resolve()
        else:
            env_root = os.getenv("OPENFDD_PARQUET_ROOT") or os.getenv("OPENFDD_STORAGE_DIR")
            if env_root:
                self.root_dir = Path(env_root).resolve()
            else:
                self.root_dir = DEFAULT_HISTORIAN_DIR.resolve()

        self.root_dir.mkdir(parents=True, exist_ok=True)

    def get_partition_dir(self, building_id: str, equipment_id: str) -> Path:
        """
        Return the directory path for a specific building and equipment partition.
        """
        safe_bldg = sanitize_partition_token(building_id, "building_id")
        safe_equip = sanitize_partition_token(equipment_id, "equipment_id")
        return self.root_dir / f"building={safe_bldg}" / f"equipment={safe_equip}"

    def get_parquet_path(self, building_id: str, equipment_id: str) -> Path:
        """
        Return the full path to the `history.parquet` file for an equipment partition.
        """
        return self.get_partition_dir(building_id, equipment_id) / "history.parquet"

    def get_meta_path(self, building_id: str, equipment_id: str) -> Path:
        """
        Return the full path to the sidecar metadata JSON file.
        """
        return self.get_partition_dir(building_id, equipment_id) / ".history.parquet.meta.json"

    def exists(self, building_id: str, equipment_id: str) -> bool:
        """
        Check if an equipment partition exists in the historian.
        """
        return self.get_parquet_path(building_id, equipment_id).is_file()

    def write_atomic(self, target_path: Path, data_bytes: bytes) -> None:
        """
        Write bytes to a temporary file and atomically rename to the target path.
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = target_path.parent / f".{target_path.name}.tmp-{os.getpid()}"

        try:
            with open(tmp_file, "wb") as f:
                f.write(data_bytes)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace
            os.replace(tmp_file, target_path)
        except Exception:
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            raise

    def list_equipment_partitions(self) -> list[tuple[str, str, Path]]:
        """
        Scan historian root and discover all existing `(building_id, equipment_id, parquet_path)` tuples.
        """
        partitions: list[tuple[str, str, Path]] = []
        if not self.root_dir.is_dir():
            return partitions

        # Look for building=* directories
        for bldg_entry in self.root_dir.iterdir():
            if not bldg_entry.is_dir() or not bldg_entry.name.startswith("building="):
                continue
            bldg_id = bldg_entry.name.removeprefix("building=")

            # Look for equipment=* directories
            for equip_entry in bldg_entry.iterdir():
                if not equip_entry.is_dir() or not equip_entry.name.startswith("equipment="):
                    continue
                equip_id = equip_entry.name.removeprefix("equipment=")
                pq_file = equip_entry / "history.parquet"

                if pq_file.is_file():
                    partitions.append((bldg_id, equip_id, pq_file))

        partitions.sort(key=lambda item: (item[0], item[1]))
        return partitions

    def delete_equipment(self, building_id: str, equipment_id: str) -> bool:
        """
        Remove an equipment partition and its directory from the historian.
        """
        p_dir = self.get_partition_dir(building_id, equipment_id)
        if p_dir.is_dir():
            shutil.rmtree(p_dir, ignore_errors=True)
            # Remove parent building directory if empty
            b_dir = p_dir.parent
            if b_dir.is_dir() and not any(b_dir.iterdir()):
                shutil.rmtree(b_dir, ignore_errors=True)
            return True
        return False

    def clear_all(self) -> None:
        """
        Clear all stored historian partitions.
        """
        if self.root_dir.is_dir():
            for item in self.root_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                elif item.is_file():
                    item.unlink(missing_ok=True)
