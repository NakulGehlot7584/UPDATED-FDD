"""
Data structures and metadata models for dataset tracking.

Source of Truth:
- `app.ingestion.csv.transformer.ColumnInspection`
- `app.ingestion.csv.transformer.DatasetTransformResult`
- `app.mapping.mapper.MappingResult`

Design Principles:
1. Pure Data Models: Contains only dataclasses representing dataset metadata and session states.
2. Zero Logic Duplication: Reuses existing ingestion, preflight, and mapping models.
3. Framework-Independent: Zero dependencies on web frameworks, databases, or cloud storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ingestion.csv.transformer import ColumnInspection, DatasetTransformResult


@dataclass(frozen=True)
class DatasetInfo:
    """
    Summary metadata for an inspected and registered CSV dataset.
    """

    dataset_id: str
    file_name: str
    file_path: str

    row_count: int
    column_count: int

    preflight_valid: bool
    timestamp_column: str | None
    median_sampling_seconds: float | None

    mapped_column_count: int
    unmapped_column_count: int
    mapping_coverage: float

    conflict_count: int

    columns: tuple[ColumnInspection, ...]
    equipment_id: str | None = None
    equipment_ids: tuple[str, ...] = ()

    @classmethod
    def from_transform_result(
        cls,
        dataset_id: str,
        result: DatasetTransformResult,
        equipment_id: str | None = None,
        equipment_ids: tuple[str, ...] = (),
    ) -> DatasetInfo:
        """
        Construct a DatasetInfo summary from an underlying DatasetTransformResult.
        """
        scan = result.scan_report
        preflight = result.preflight_report
        return cls(
            dataset_id=dataset_id,
            file_name=result.file_name,
            file_path=result.file_path,
            row_count=scan.get("row_count", result.dataframe.height),
            column_count=scan.get("column_count", result.dataframe.width),
            preflight_valid=preflight.get("valid", False),
            timestamp_column=preflight.get("timestamp_column"),
            median_sampling_seconds=preflight.get("median_sampling_seconds"),
            mapped_column_count=result.mapped_column_count,
            unmapped_column_count=result.unmapped_column_count,
            mapping_coverage=result.mapping_coverage,
            conflict_count=len(result.mapping_result.conflicts),
            columns=tuple(result.columns),
            equipment_id=equipment_id,
            equipment_ids=equipment_ids,
        )


@dataclass
class DatasetSession:
    """
    In-memory session container tracking multiple registered datasets.
    """

    datasets: dict[str, DatasetInfo] = field(default_factory=dict)
