"""
Canonical Data Transformation layer for the Open-FDD ingestion pipeline.
"""

from __future__ import annotations

from app.transformation.canonical import (
    CanonicalTransformResult,
    transform_csv_canonical,
    transform_to_canonical,
)
from app.transformation.schema import (
    CanonicalField,
    CanonicalSchema,
    ConversionRecord,
    UnmappedChannel,
)
from app.transformation.units import (
    UNIT_CONVERSION_REGISTRY,
    apply_unit_conversion,
)

__all__ = [
    "CanonicalField",
    "CanonicalSchema",
    "CanonicalTransformResult",
    "ConversionRecord",
    "UNIT_CONVERSION_REGISTRY",
    "UnmappedChannel",
    "apply_unit_conversion",
    "transform_csv_canonical",
    "transform_to_canonical",
]
