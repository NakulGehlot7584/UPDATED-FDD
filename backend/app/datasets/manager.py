"""
Operational dataset manager for registering, querying, and managing datasets.

Source of Truth:
- Transformation pipeline: `app.ingestion.csv.transformer.transform_csv`
- Metadata models: `app.datasets.models.DatasetInfo`, `app.datasets.models.DatasetSession`

Design Principles:
1. Operational Layer: Bridges transformation results into registered dataset records.
2. Safe Unique Identification: Generates UUIDs to distinguish distinct files even if filenames match.
3. Duplicate Path Protection: Prevents duplicate registration of the same physical path.
4. Non-Destructive: Registers datasets with `canonicalize_names=False` to preserve raw source schemas.
5. Thread-Safe: Uses an internal RLock for concurrent safe access.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import uuid

from app.datasets.models import DatasetInfo, DatasetSession
from app.historian.service import HistorianService
from app.ingestion.csv.transformer import DatasetTransformResult, transform_csv


@dataclass
class _DatasetRecord:
    """
    Internal storage record pairing public metadata with full transformation diagnostics.
    """

    info: DatasetInfo
    transform_result: DatasetTransformResult


class DatasetManager:
    """
    Thread-safe in-memory manager for registering, inspecting, and managing multiple CSV datasets.
    """

    def __init__(self, historian: HistorianService | None = None) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, _DatasetRecord] = {}
        self._path_to_id: dict[str, str] = {}
        self._historian = historian or HistorianService()

    @property
    def historian(self) -> HistorianService:
        """Access the underlying HistorianService."""
        return self._historian

    def add_csv(
        self,
        file_path: str | Path,
    ) -> DatasetInfo:
        """
        Inspect and register a CSV dataset.

        If the same physical file path was already registered, returns the existing
        DatasetInfo record deterministically without duplicating data.

        Args:
            file_path: Path to the target CSV file.

        Returns:
            DatasetInfo summary metadata.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is not a valid CSV.
        """
        path = Path(file_path).resolve()

        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        if path.suffix.lower() != ".csv":
            raise ValueError(f"Expected a CSV file, got: {path.suffix}")

        norm_path_str = str(path)

        with self._lock:
            # Check if this exact physical path was already registered
            if norm_path_str in self._path_to_id:
                existing_id = self._path_to_id[norm_path_str]
                return self._records[existing_id].info

            # Execute transformation pipeline (preserving source schema)
            result = transform_csv(path, canonicalize_names=False)

            eq_id = None
            eq_ids: tuple[str, ...] = ()
            try:
                can_res = result.to_canonical()
                if "equipment_id" in can_res.canonical_df.columns:
                    distinct_eqs = [
                        str(x)
                        for x in can_res.canonical_df["equipment_id"].unique().drop_nulls().to_list()
                        if x is not None and str(x).strip()
                    ]
                    if distinct_eqs:
                        eq_ids = tuple(distinct_eqs)
                        eq_id = distinct_eqs[0]
            except Exception:
                pass

            dataset_id = str(uuid.uuid4())
            info = DatasetInfo.from_transform_result(
                dataset_id,
                result,
                equipment_id=eq_id,
                equipment_ids=eq_ids,
            )

            record = _DatasetRecord(
                info=info,
                transform_result=result,
            )

            self._records[dataset_id] = record
            self._path_to_id[norm_path_str] = dataset_id

            return info

    def list_datasets(self) -> list[DatasetInfo]:
        """
        Return summary metadata for all currently registered datasets.
        """
        with self._lock:
            return [record.info for record in self._records.values()]

    def get_dataset(
        self,
        dataset_id: str,
    ) -> DatasetInfo | None:
        """
        Retrieve summary metadata for a dataset by its unique ID.
        """
        with self._lock:
            record = self._records.get(dataset_id)
            return record.info if record is not None else None

    def get_dataset_result(
        self,
        dataset_id: str,
    ) -> DatasetTransformResult | None:
        """
        Retrieve the complete DatasetTransformResult (DataFrame, scan, preflight, mappings)
        for a dataset by its unique ID.
        """
        with self._lock:
            record = self._records.get(dataset_id)
            return record.transform_result if record is not None else None

    def get_equipment_id_for_dataset(
        self,
        dataset_id: str,
    ) -> str | None:
        """
        Get the canonical equipment ID associated with a dataset ID.
        """
        with self._lock:
            record = self._records.get(dataset_id)
            return record.info.equipment_id if record is not None else None

    def get_canonical_telemetry(
        self,
        dataset_id: str,
        default_equipment_id: str | None = None,
    ):
        """
        Produce or retrieve the CanonicalTransformResult for a registered dataset.
        """
        with self._lock:
            record = self._records.get(dataset_id)
            if record is None:
                return None
            return record.transform_result.to_canonical(
                default_equipment_id=default_equipment_id,
            )

    def ingest_to_historian(
        self,
        dataset_id: str,
        building_id: str = "DEFAULT_BUILDING",
        default_equipment_id: str | None = None,
    ):
        """
        Ingest a registered dataset into the partitioned Parquet historian.
        """
        can_res = self.get_canonical_telemetry(
            dataset_id,
            default_equipment_id=default_equipment_id,
        )
        if can_res is None:
            return []
        return self._historian.ingest_canonical_result(
            can_res,
            building_id=building_id,
            default_equipment_id=default_equipment_id,
        )

    def has_dataset(
        self,
        dataset_id: str,
    ) -> bool:
        """
        Check if a dataset with the given ID is registered.
        """
        with self._lock:
            return dataset_id in self._records

    def remove_dataset(
        self,
        dataset_id: str,
    ) -> bool:
        """
        Unregister and remove a dataset by its unique ID.

        Returns True if the dataset was found and removed, False otherwise.
        """
        with self._lock:
            record = self._records.pop(dataset_id, None)
            if record is not None:
                norm_path_str = str(Path(record.info.file_path).resolve())
                self._path_to_id.pop(norm_path_str, None)
                return True
            return False

    def clear(self) -> None:
        """
        Unregister all datasets and reset the manager state.
        """
        with self._lock:
            self._records.clear()
            self._path_to_id.clear()

    def get_session(self) -> DatasetSession:
        """
        Produce a DatasetSession snapshot of all active datasets.
        """
        with self._lock:
            return DatasetSession(
                datasets={d_id: rec.info for d_id, rec in self._records.items()}
            )
