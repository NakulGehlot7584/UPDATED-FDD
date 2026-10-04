"""Data models for Open-FDD Rule Engine and Apache DataFusion integration."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class RuleExecutionStatus(str, Enum):
    """Execution status of an FDD rule."""
    SUCCESS = "SUCCESS"
    FAULT_DETECTED = "FAULT_DETECTED"
    NO_FAULT = "NO_FAULT"
    SKIPPED_MISSING_ROLES = "SKIPPED_MISSING_ROLES"
    ERROR = "ERROR"


class RuleSeverity(str, Enum):
    """Severity classification for FDD rule findings."""
    P0 = "P0"  # Critical / Screened
    P1 = "P1"  # High
    P2 = "P2"  # Medium
    P3 = "P3"  # Low / Info


class RuleParameterDef(BaseModel):
    """Metadata definition for a configurable SQL rule parameter."""
    label: str
    default: float
    min: float
    max: float
    step: float
    unit: str
    frontend_control: str = "slider"
    sql_placeholder: str


class RuleDefinition(BaseModel):
    """Specification of an official Open-FDD rule."""
    rule_id: str
    aliases: List[str] = Field(default_factory=list)
    sql_file: str
    description: str
    required_roles: List[str] = Field(default_factory=list)
    optional_roles: List[str] = Field(default_factory=list)
    equipment_kinds: List[str] = Field(default_factory=list)
    output_columns: List[str] = Field(default_factory=list)
    priority: str = "P0"
    parity_status: str = "sql_screening"
    dashboard_wired: bool = False
    confirm_seconds: int = 300
    parameters: Dict[str, RuleParameterDef] = Field(default_factory=dict)
    sql_template: Optional[str] = None


class RuleFinding(BaseModel):
    """Individual fault detection finding for an equipment entity."""
    equipment_id: str
    building_id: Optional[str] = None
    rule_id: str
    severity: str = "P0"
    description: str
    fault_detected: bool = False
    fault_hours: Optional[float] = None
    fault_pct: Optional[float] = None
    total_hours: Optional[float] = None
    sample_count: Optional[int] = None
    raw_fault_count: Optional[int] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    episodes: List[FaultEpisode] = Field(default_factory=list)
    detail: Optional[FaultDetailRecord] = None


class RuleExecutionResult(BaseModel):
    """Comprehensive result of executing a single FDD rule."""
    rule_id: str
    status: RuleExecutionStatus
    elapsed_ms: float = 0.0
    row_count: int = 0
    findings: List[RuleFinding] = Field(default_factory=list)
    missing_roles: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    parameters_used: Dict[str, Any] = Field(default_factory=dict)
    executed_sql: Optional[str] = None


class ExecuteRuleRequest(BaseModel):
    """Request payload to execute rules on equipment."""
    building_id: Optional[str] = None
    equipment_id: Optional[str] = None
    equipment_kind: Optional[str] = None
    rule_ids: Optional[List[str]] = None
    parameter_overrides: Optional[Dict[str, Dict[str, float]]] = None
    poll_seconds: Optional[float] = None
    start_utc: Optional[str] = None
    end_utc: Optional[str] = None


class FDDExecutionSummary(BaseModel):
    """Aggregate summary report across an FDD execution run."""
    building_id: Optional[str] = None
    equipment_id: Optional[str] = None
    equipment_kind: Optional[str] = None
    total_catalog_rules: int = 66
    applicable_rules: int = 0
    non_applicable_rules: int = 0
    total_rules_evaluated: int = 0
    rules_succeeded: int = 0
    rules_faulted: int = 0
    rules_no_fault: int = 0
    rules_skipped: int = 0
    rules_failed: int = 0
    total_elapsed_ms: float = 0.0
    poll_seconds: float = 300.0
    results: List[RuleExecutionResult] = Field(default_factory=list)


class FaultEpisode(BaseModel):
    """Contiguous interval of active fault samples."""
    episode_id: str
    start: str  # ISO 8601 UTC
    end: str    # ISO 8601 UTC
    samples: int
    duration_hours: float
    summary: Optional[str] = None


class FaultEvidence(BaseModel):
    """Grounded telemetry evidence supporting a fault finding."""
    evidence_text: str
    confidence: str = "CONFIRMED"  # CONFIRMED | SUPPORTED | LIMITED
    observed_values: Dict[str, Any] = Field(default_factory=dict)
    missing_context_roles: List[str] = Field(default_factory=list)


class FaultDetailRecord(BaseModel):
    """Comprehensive diagnostic record for a detected fault."""
    rule_id: str
    rule_name: str
    equipment_id: str
    building_id: Optional[str] = None
    category: str = "General"
    severity: str = "HIGH"  # CRITICAL | HIGH | MEDIUM | LOW | INFO
    title: str
    description: str
    fault_detected: bool = False
    total_fault_hours: float = 0.0
    fault_pct: Optional[float] = None
    total_hours: Optional[float] = None
    sample_count: int = 0
    raw_sample_count: Optional[int] = None
    episode_count: int = 0
    episodes: List[FaultEpisode] = Field(default_factory=list)
    evidence: List[FaultEvidence] = Field(default_factory=list)
    possible_causes: List[str] = Field(default_factory=list)
    recommended_checks: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    associated_roles: List[str] = Field(default_factory=list)


class FaultSummaryItem(BaseModel):
    """Compact summary item for fault tables and lists."""
    rule_id: str
    rule_name: str
    equipment_id: str
    building_id: Optional[str] = None
    category: str = "General"
    severity: str = "HIGH"
    title: str
    total_fault_hours: float = 0.0
    fault_pct: Optional[float] = None
    sample_count: Optional[int] = None
    raw_fault_count: Optional[int] = None
    episode_count: int = 0
    active_now: bool = False
    first_fault_time: Optional[str] = None
    last_fault_time: Optional[str] = None


class GraphSeries(BaseModel):
    """Single numeric telemetry or status series for plotting."""
    role: str
    name: str
    unit: str = ""
    timestamps: List[str] = Field(default_factory=list)
    values: List[Optional[float]] = Field(default_factory=list)
    chart_type: str = "line"  # line | step | scatter
    y_axis: str = "y1"        # y1 | y2 | y3 | y4
    color: Optional[str] = None


class GraphPayload(BaseModel):
    """Multi-axis telemetry and fault visualization payload."""
    graph_id: str
    title: str
    equipment_id: str
    building_id: Optional[str] = None
    category: str = "telemetry"
    series: List[GraphSeries] = Field(default_factory=list)
    fault_episodes: List[FaultEpisode] = Field(default_factory=list)
    sampling_interval_seconds: float = 300.0
    total_points: int = 0
    time_range: Dict[str, Optional[str]] = Field(default_factory=dict)


class AvailableGraphCategory(BaseModel):
    """Specification of an available graph category based on uploaded points."""
    category_id: str
    title: str
    description: str
    available_roles: List[str] = Field(default_factory=list)
    is_available: bool = False


class FaultTimelineLane(BaseModel):
    """Horizontal swimlane representing a single rule's fault episodes."""
    rule_id: str
    rule_name: str
    severity: str
    total_fault_hours: float = 0.0
    episodes: List[FaultEpisode] = Field(default_factory=list)


class FaultTimelinePayload(BaseModel):
    """Composite fault timeline containing all faulted rule swimlanes."""
    equipment_id: str
    building_id: Optional[str] = None
    time_range: Dict[str, Optional[str]] = Field(default_factory=dict)
    lanes: List[FaultTimelineLane] = Field(default_factory=list)
    total_fault_hours: float = 0.0
    total_episodes: int = 0


class ResultValidationReport(BaseModel):
    """Execution result, evidence integrity, and finding reconciliation report."""
    overall_status: str = "VALID"  # VALID | WARNING | INVALID
    rules_validated_count: int = 0
    rules_valid_count: int = 0
    rules_issue_count: int = 0
    findings_validated_count: int = 0
    findings_valid_count: int = 0
    findings_with_evidence_issues: int = 0
    duplicate_findings_count: int = 0
    reconciliation_errors_count: int = 0
    issues_summary: List[str] = Field(default_factory=list)
    rules_table: List[Dict[str, Any]] = Field(default_factory=list)
    findings_table: List[Dict[str, Any]] = Field(default_factory=list)
    reconciliation_table: List[Dict[str, Any]] = Field(default_factory=list)


