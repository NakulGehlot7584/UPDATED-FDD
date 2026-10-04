"""
Canonical schema and field metadata structures for transformed HVAC telemetry datasets.

Source of Truth:
- Canonical role catalog in `app.mapping.roles.CANONICAL_ROLES`
- Column inspection model in `app.ingestion.csv.transformer.ColumnInspection`

Design Principles:
1. Complete Provenance & Traceability: Every canonical telemetry field preserves its
   originating source column, source dtype, detected unit, and any applied mathematical conversion.
2. Zero Data Loss: Unmapped source columns are captured as structured `UnmappedChannel`
   records with reasons and semantic classification.
3. Framework-Independent: Uses standard Python dataclasses for serialization into JSON/Arrow/Parquet.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CanonicalField:
    """
    Metadata describing a single column in the canonical telemetry dataset.
    """

    name: str
    role: str | None
    dtype: str
    unit: str | None
    source_column: str
    source_dtype: str
    source_unit: str | None = None
    conversion_applied: str | None = None
    is_metadata: bool = False


@dataclass(frozen=True)
class UnmappedChannel:
    """
    Diagnostic record for a raw source column not included in canonical telemetry roles.
    """

    source_column: str
    source_dtype: str
    unit: str | None = None
    column_category: str = "UNSUPPORTED"
    reason: str = "Not mapped to canonical role"


@dataclass(frozen=True)
class ConversionRecord:
    """
    Audit record of a physical unit transformation applied during ingestion.
    """

    source_column: str
    canonical_role: str
    source_unit: str
    canonical_unit: str
    formula: str


@dataclass(frozen=True)
class CanonicalSchema:
    """
    Complete schema definition of the canonical dataset including mapped telemetry,
    metadata channels, unmapped column traceability, and applied unit conversions.
    """

    fields: list[CanonicalField] = field(default_factory=list)
    unmapped_channels: list[UnmappedChannel] = field(default_factory=list)
    conversions: list[ConversionRecord] = field(default_factory=list)

    @property
    def field_names(self) -> list[str]:
        """List of all canonical column names in the output dataset."""
        return [f.name for f in self.fields]

    @property
    def telemetry_fields(self) -> list[CanonicalField]:
        """List of canonical HVAC telemetry fields (excluding metadata)."""
        return [f for f in self.fields if not f.is_metadata]

    @property
    def metadata_fields(self) -> list[CanonicalField]:
        """List of metadata fields (e.g. timestamp_utc, equipment_id)."""
        return [f for f in self.fields if f.is_metadata]

    def get_field(self, name: str) -> CanonicalField | None:
        """Lookup canonical field by output column name."""
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def get_field_by_role(self, role: str) -> CanonicalField | None:
        """Lookup canonical field by canonical HVAC role."""
        for f in self.fields:
            if f.role == role:
                return f
        return None

    def get_field_by_source_column(self, source_col: str) -> CanonicalField | None:
        """Lookup canonical field by original raw CSV source column name."""
        for f in self.fields:
            if f.source_column == source_col:
                return f
        return None
