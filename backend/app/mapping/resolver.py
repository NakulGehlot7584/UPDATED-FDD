"""
Global role resolution engine for the FDD CSV role-mapping pipeline.

Source of Truth:
- Canonical role catalog in `backend.app.mapping.roles` (59 Open-FDD roles + co2, co2_sp)
- Scored candidate evaluations from `scorer.py`

Design Principles:
1. Global Resolution: Performs global 1-to-1 matching across all columns and roles.
   - Highest-scoring column wins each canonical role.
   - Conflict records capture any lower-scoring competing columns.
   - Non-winning columns can gracefully fall back to alternative valid roles.
2. Deterministic Tie-Breaking:
   - Primary: Evidence score (descending)
   - Secondary: Matched semantic pattern length (descending, favoring specific phrases)
   - Tertiary: Alphabetical role name
   - Quaternary: Alphabetical source column name
3. Explanatory & Auditable: Every resolution decision preserves winning score, reason,
   matched pattern, conflicts, and unmapped column lists.
4. Independent: Uses only standard library and project data structures (no pandas/polars).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.mapping.inference import RoleCandidate, infer_role_candidates
from app.mapping.scorer import ScoredCandidate, score_candidates


@dataclass(frozen=True)
class ResolvedMapping:
    """
    Final resolved assignment of a canonical role to a source column.
    """

    role: str
    source_column: str
    score: int
    reason: str
    matched_pattern: str


@dataclass(frozen=True)
class MappingConflict:
    """
    Diagnostic record of a column that competed for a role but was rejected
    in favor of a higher-scoring or higher-priority candidate.
    """

    role: str
    winner_column: str
    winner_score: int
    loser_column: str
    loser_score: int
    reason: str


@dataclass(frozen=True)
class ResolutionResult:
    """
    Container holding the complete outcome of global role resolution.
    """

    mappings: dict[str, ResolvedMapping] = field(default_factory=dict)
    column_to_role: dict[str, str] = field(default_factory=dict)
    conflicts: list[MappingConflict] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)


def resolve_scored_candidates(
    column_candidates: dict[str, list[ScoredCandidate]],
) -> ResolutionResult:
    """
    Resolve global 1-to-1 mappings across columns and roles from precomputed scored candidates.

    Args:
        column_candidates: Mapping of source_column -> list of ScoredCandidate objects.

    Returns:
        ResolutionResult containing winning mappings, column-to-role lookup, conflicts, and unmapped columns.
    """
    # 1. Flatten all eligible (score > 0) candidate proposals across all columns
    flat_candidates: list[tuple[int, int, str, str, ScoredCandidate]] = []

    for col, cands in column_candidates.items():
        for cand in cands:
            if cand.score > 0:
                flat_candidates.append((
                    cand.score,
                    len(cand.matched_pattern),
                    cand.role,
                    col,
                    cand,
                ))

    # 2. Deterministic sort:
    #    - Score descending (-score)
    #    - Pattern length descending (-pat_len: favors specific multi-word tokens over abbreviations)
    #    - Role name alphabetical (deterministic secondary tie-breaker)
    #    - Column name alphabetical (deterministic tertiary tie-breaker)
    flat_candidates.sort(
        key=lambda item: (-item[0], -item[1], item[2], item[3]),
    )

    assigned_roles: dict[str, tuple[str, int]] = {}  # role -> (winner_column, winner_score)
    assigned_columns: dict[str, str] = {}            # column -> role
    resolved_mappings: dict[str, ResolvedMapping] = {}
    conflicts: list[MappingConflict] = []

    # 3. Greedy resolution with conflict tracking
    for score, pat_len, role, col, cand in flat_candidates:
        if role not in assigned_roles and col not in assigned_columns:
            # Clean primary assignment
            assigned_roles[role] = (col, score)
            assigned_columns[col] = role
            resolved_mappings[role] = ResolvedMapping(
                role=role,
                source_column=col,
                score=score,
                reason=cand.reason,
                matched_pattern=cand.matched_pattern,
            )
        elif role in assigned_roles and col not in assigned_columns:
            # Role already claimed by a higher-scoring or earlier-ranked column
            winner_col, winner_score = assigned_roles[role]
            conflicts.append(
                MappingConflict(
                    role=role,
                    winner_column=winner_col,
                    winner_score=winner_score,
                    loser_column=col,
                    loser_score=score,
                    reason=(
                        f"Role '{role}' already assigned to '{winner_col}' (score {winner_score}) "
                        f"over '{col}' (score {score})."
                    ),
                )
            )
        elif col in assigned_columns and role not in assigned_roles:
            # Column was already assigned to a higher-scoring role
            pass

    # 4. Identify all columns in input that remain unmapped
    all_input_cols = list(column_candidates.keys())
    unmapped = [c for c in all_input_cols if c not in assigned_columns]

    return ResolutionResult(
        mappings=resolved_mappings,
        column_to_role=assigned_columns,
        conflicts=conflicts,
        unmapped_columns=unmapped,
    )


def resolve_mappings(columns: list[str]) -> ResolutionResult:
    """
    Execute end-to-end resolution pipeline for a list of column names:
    inference -> scoring -> global resolution.

    Args:
        columns: List of source column name strings from CSV / telemetry stream.

    Returns:
        ResolutionResult containing resolved mappings, conflicts, and unmapped columns.
    """
    column_candidates: dict[str, list[ScoredCandidate]] = {}

    for col in columns:
        inferred = infer_role_candidates(col)
        scored = score_candidates(col, inferred)
        column_candidates[col] = scored

    return resolve_scored_candidates(column_candidates)
