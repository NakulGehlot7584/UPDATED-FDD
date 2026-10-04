"""FDD Rule Engine powered by Apache DataFusion and official Open-FDD SQL rules."""

from app.fdd.catalog import RuleCatalog, get_rule_catalog
from app.fdd.engine import DataFusionEngine, create_engine
from app.fdd.executor import RuleExecutor, get_executor
from app.fdd.diagnostics import build_grounded_diagnostic, get_diagnostic_meta
from app.fdd.episodes import extract_fault_episodes
from app.fdd.graphs import (
    build_fault_timeline,
    build_rule_graph,
    build_telemetry_graph,
    get_available_graph_categories,
    select_plot_indices,
)
from app.fdd.models import (
    AvailableGraphCategory,
    ExecuteRuleRequest,
    FDDExecutionSummary,
    FaultDetailRecord,
    FaultEpisode,
    FaultEvidence,
    FaultSummaryItem,
    FaultTimelineLane,
    FaultTimelinePayload,
    GraphPayload,
    GraphSeries,
    RuleDefinition,
    RuleExecutionResult,
    RuleExecutionStatus,
    RuleFinding,
    RuleParameterDef,
    RuleSeverity,
)

__all__ = [
    "RuleCatalog",
    "get_rule_catalog",
    "DataFusionEngine",
    "create_engine",
    "RuleExecutor",
    "get_executor",
    "RuleDefinition",
    "RuleParameterDef",
    "RuleFinding",
    "RuleExecutionResult",
    "RuleExecutionStatus",
    "RuleSeverity",
    "ExecuteRuleRequest",
    "FDDExecutionSummary",
    "FaultEpisode",
    "FaultEvidence",
    "FaultDetailRecord",
    "FaultSummaryItem",
    "GraphSeries",
    "GraphPayload",
    "AvailableGraphCategory",
    "FaultTimelineLane",
    "FaultTimelinePayload",
    "extract_fault_episodes",
    "build_grounded_diagnostic",
    "get_diagnostic_meta",
    "build_telemetry_graph",
    "build_rule_graph",
    "build_fault_timeline",
    "get_available_graph_categories",
    "select_plot_indices",
]
