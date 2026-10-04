"""
Pydantic API request and response schemas.

Design Principles:
1. Serialization Safety: Ensures all responses are strictly JSON-serializable.
2. Polars Isolation: DataFrames are never directly exposed through schemas.
3. Complete Visibility: Preserves all mapping, conflict, preflight, and inspection metadata.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class DatasetSummary(BaseModel):
    dataset_id: str
    file_name: str
    row_count: int
    column_count: int
    mapped_column_count: int
    unmapped_column_count: int
    mapping_coverage: float
    conflict_count: int
    preflight_valid: bool
    equipment_id: str | None = None
    equipment_ids: list[str] = Field(default_factory=list)


class DatasetListResponse(BaseModel):
    datasets: list[DatasetSummary]


class ColumnInspectionSchema(BaseModel):
    source_column: str
    canonical_role: str | None = None
    source_dtype: str | None = None
    unit: str | None = None
    canonical_unit: str | None = None
    conversion_required: bool = False
    mapping_score: int | None = None
    matched_pattern: str | None = None
    mapping_reason: str | None = None
    mapped: bool = False
    column_category: str = "CANONICAL_SIGNAL"


class MappingConflictSchema(BaseModel):
    role: str
    winner_column: str
    winner_score: int
    loser_column: str
    loser_score: int
    reason: str


class PreflightDetailsSchema(BaseModel):
    valid: bool
    timestamp_column: str | None = None
    timestamp_valid: bool = False
    missing_timestamps: int = 0
    duplicate_timestamps: int = 0
    non_monotonic_timestamps: int = 0
    median_sampling_seconds: float | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DatasetDetailResponse(BaseModel):
    dataset_id: str
    file_name: str
    row_count: int
    column_count: int
    preflight: PreflightDetailsSchema
    mapped_column_count: int
    unmapped_column_count: int
    mapping_coverage: float
    conflict_count: int
    columns: list[ColumnInspectionSchema]
    conflicts: list[MappingConflictSchema]
    unmapped_columns: list[str]
    equipment_id: str | None = None
    equipment_ids: list[str] = Field(default_factory=list)


class DatasetColumnsResponse(BaseModel):
    dataset_id: str
    columns: list[ColumnInspectionSchema]


class DatasetDeleteResponse(BaseModel):
    dataset_id: str
    removed: bool


class CanonicalFieldSchema(BaseModel):
    name: str
    role: str | None = None
    dtype: str
    unit: str | None = None
    source_column: str
    source_dtype: str
    source_unit: str | None = None
    conversion_applied: str | None = None
    is_metadata: bool = False


class UnmappedChannelSchema(BaseModel):
    source_column: str
    source_dtype: str
    unit: str | None = None
    column_category: str = "UNSUPPORTED"
    reason: str


class ConversionRecordSchema(BaseModel):
    source_column: str
    canonical_role: str
    source_unit: str
    canonical_unit: str
    formula: str


class CanonicalTelemetryResponse(BaseModel):
    dataset_id: str
    file_name: str
    row_count: int
    column_count: int
    timestamp_column: str | None = None
    equipment_id_column: str | None = None
    telemetry_roles: list[str]
    fields: list[CanonicalFieldSchema]
    unmapped_channels: list[UnmappedChannelSchema]
    conversions: list[ConversionRecordSchema]
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)


class EquipmentSummarySchema(BaseModel):
    equipment_id: str
    building_id: str
    row_count: int
    min_timestamp: str | None = None
    max_timestamp: str | None = None
    telemetry_roles: list[str] = Field(default_factory=list)
    parquet_file: str
    file_size_bytes: int
    last_updated: str


class HistorianSummarySchema(BaseModel):
    total_equipment: int
    total_rows: int
    total_bytes: int
    buildings: list[str]
    global_min_timestamp: str | None = None
    global_max_timestamp: str | None = None
    equipment_list: list[EquipmentSummarySchema] = Field(default_factory=list)


class HistorianIngestResponse(BaseModel):
    dataset_id: str
    equipment_written: int
    total_rows: int
    partitions: list[dict[str, Any]] = Field(default_factory=list)


class HistorianTelemetryResponse(BaseModel):
    building_id: str
    equipment_id: str
    row_count: int
    column_count: int
    columns: list[str]
    min_timestamp: str | None = None
    max_timestamp: str | None = None
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)
