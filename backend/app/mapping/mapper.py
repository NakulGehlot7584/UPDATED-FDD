"""
Public mapping orchestration module for the FDD CSV role-mapping pipeline.

Source of Truth:
- Canonical role catalog in `backend.app.mapping.roles` (59 Open-FDD roles + co2, co2_sp)
- Pipeline orchestration flow:
  `normalizer` -> `inference` -> `scorer` -> `resolver` -> `mapper`

Design Principles:
1. Pure Orchestration: `mapper.py` does NOT implement new semantic mapping rules or
   duplicate scoring and conflict resolution logic.
2. Complete Diagnostics: Exposes the full resolution outcome alongside convenience
   lookup helpers through `MappingResult`.
3. Input Safety: Validates input iterables, handles duplicates, trims whitespace, and avoids
   mutating caller collections.
4. Independent: Operates strictly on standard library Python data structures (zero pandas/polars dependencies).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from app.mapping.resolver import (
    MappingConflict,
    ResolutionResult,
    ResolvedMapping,
    resolve_mappings,
)


@dataclass(frozen=True)
class MappingResult:
    """
    Public container presenting the final resolved canonical role mapping
    along with complete conflict and unmapped diagnostics.
    """

    mappings: dict[str, ResolvedMapping] = field(default_factory=dict)
    column_to_role: dict[str, str] = field(default_factory=dict)
    conflicts: list[MappingConflict] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)
    raw_columns: list[str] = field(default_factory=list)

    def get_column_for_role(self, role: str) -> str | None:
        """
        Return the source column mapped to the canonical role, or None if unmapped.
        """
        mapping = self.mappings.get(role)
        return mapping.source_column if mapping is not None else None

    def get_role_for_column(self, column: str) -> str | None:
        """
        Return the canonical role mapped to the source column, or None if unmapped.
        """
        return self.column_to_role.get(column)

    def has_role(self, role: str) -> bool:
        """
        Check whether a canonical role is present in the resolved mapping.
        """
        return role in self.mappings

    @property
    def mapped_role_count(self) -> int:
        """
        Number of canonical roles successfully mapped.
        """
        return len(self.mappings)

    @property
    def unmapped_column_count(self) -> int:
        """
        Number of source columns not mapped to any canonical role.
        """
        return len(self.unmapped_columns)

    @classmethod
    def from_resolution_result(
        cls,
        result: ResolutionResult,
        raw_columns: list[str],
    ) -> MappingResult:
        """
        Construct MappingResult from an underlying ResolutionResult.
        """
        return cls(
            mappings=result.mappings,
            column_to_role=result.column_to_role,
            conflicts=result.conflicts,
            unmapped_columns=result.unmapped_columns,
            raw_columns=raw_columns,
        )


def map_columns(
    columns: Sequence[str],
) -> MappingResult:
    """
    Orchestrate column-to-canonical-role mapping for a collection of source column names.

    Args:
        columns: Sequence of source column header strings from a CSV or telemetry stream.

    Returns:
        MappingResult containing resolved 1-to-1 mappings, conflicts, and unmapped columns.
    """
    # 1. Clean and deduplicate input columns safely without mutating input
    cleaned_columns: list[str] = []
    seen: set[str] = set()

    for col in columns:
        if not isinstance(col, str):
            col_str = str(col).strip()
        else:
            col_str = col.strip()

        if not col_str:
            continue

        if col_str not in seen:
            seen.add(col_str)
            cleaned_columns.append(col_str)

    if not cleaned_columns:
        return MappingResult(raw_columns=list(columns))

    # 2. Delegate to resolver engine
    resolution = resolve_mappings(cleaned_columns)

    # 3. Wrap in public MappingResult
    return MappingResult.from_resolution_result(
        result=resolution,
        raw_columns=list(columns),
    )


def build_mapping(
    columns: Sequence[str],
) -> MappingResult:
    """
    Alias for map_columns for flexible pipeline integration.
    """
    return map_columns(columns)
