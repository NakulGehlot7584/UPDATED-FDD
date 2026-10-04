export interface DatasetSummary {
  dataset_id: string;
  file_name: string;
  row_count: number;
  column_count: number;
  mapped_column_count: number;
  unmapped_column_count: number;
  mapping_coverage: number;
  conflict_count: number;
  preflight_valid: boolean;
  equipment_id?: string | null;
  equipment_ids?: string[];
}

export interface DatasetListResponse {
  datasets: DatasetSummary[];
}

export interface ColumnInspection {
  source_column: string;
  canonical_role: string | null;
  column_category?: string;
  source_dtype: string | null;
  unit: string | null;
  canonical_unit: string | null;
  conversion_required: boolean;
  mapping_score: number | null;
  matched_pattern: string | null;
  mapping_reason: string | null;
  mapped: boolean;
}

export interface MappingConflict {
  role: string;
  winner_column: string;
  winner_score: number;
  loser_column: string;
  loser_score: number;
  reason: string;
}

export interface PreflightDetails {
  valid: boolean;
  timestamp_column: string | null;
  timestamp_valid: boolean;
  missing_timestamps: number;
  duplicate_timestamps: number;
  non_monotonic_timestamps: number;
  median_sampling_seconds: number | null;
  warnings: string[];
  errors: string[];
}

export interface DatasetDetailResponse {
  dataset_id: string;
  file_name: string;
  row_count: number;
  column_count: number;
  preflight: PreflightDetails;
  mapped_column_count: number;
  unmapped_column_count: number;
  mapping_coverage: number;
  conflict_count: number;
  columns: ColumnInspection[];
  conflicts: MappingConflict[];
  unmapped_columns: string[];
  equipment_id?: string | null;
  equipment_ids?: string[];
  building_id?: string | null;
}

export interface DatasetColumnsResponse {
  dataset_id: string;
  columns: ColumnInspection[];
}

export interface DatasetDeleteResponse {
  dataset_id: string;
  removed: boolean;
}

// ==========================================
// FDD & Open-FDD Rule Engine Types
// ==========================================

export type RuleExecutionStatus =
  | 'SUCCESS'
  | 'FAULT_DETECTED'
  | 'NO_FAULT'
  | 'SKIPPED_MISSING_ROLES'
  | 'ERROR';

export type RuleSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO' | 'P0' | 'P1' | 'P2' | 'P3';

export interface RuleParameterDef {
  label: string;
  default: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  frontend_control?: string;
  sql_placeholder: string;
}

export interface RuleDefinition {
  rule_id: string;
  aliases: string[];
  sql_file: string;
  description: string;
  required_roles: string[];
  optional_roles: string[];
  equipment_kinds: string[];
  output_columns: string[];
  priority: string;
  parity_status: string;
  dashboard_wired: boolean;
  confirm_seconds: number;
  parameters: Record<string, RuleParameterDef>;
  sql_template?: string | null;
}

export interface FaultEpisode {
  episode_id: string;
  start: string;
  end: string;
  samples: number;
  duration_hours: number;
  summary?: string | null;
}

export interface FaultEvidence {
  evidence_text: string;
  confidence: string;
  observed_values: Record<string, any>;
  missing_context_roles: string[];
}

export interface FaultDetailRecord {
  rule_id: string;
  rule_name: string;
  equipment_id: string;
  building_id?: string | null;
  category: string;
  severity: string;
  title: string;
  description: string;
  fault_detected: boolean;
  total_fault_hours: number;
  fault_pct?: number | null;
  total_hours?: number | null;
  sample_count: number;
  episode_count: number;
  episodes: FaultEpisode[];
  evidence: FaultEvidence[];
  possible_causes: string[];
  recommended_checks: string[];
  metrics: Record<string, any>;
  associated_roles: string[];
}

export interface RuleFinding {
  equipment_id: string;
  building_id?: string | null;
  rule_id: string;
  severity: string;
  description: string;
  fault_detected: boolean;
  fault_hours?: number | null;
  fault_pct?: number | null;
  total_hours?: number | null;
  sample_count?: number | null;
  raw_fault_count?: number | null;
  metrics: Record<string, any>;
  episodes: FaultEpisode[];
  detail?: FaultDetailRecord | null;
}

export interface RuleExecutionResult {
  rule_id: string;
  status: RuleExecutionStatus;
  elapsed_ms: number;
  row_count: number;
  findings: RuleFinding[];
  missing_roles: string[];
  error?: string | null;
  parameters_used: Record<string, any>;
  executed_sql?: string | null;
}

export interface FDDExecutionSummary {
  building_id?: string | null;
  equipment_id?: string | null;
  equipment_kind?: string | null;
  total_catalog_rules?: number;
  applicable_rules?: number;
  non_applicable_rules?: number;
  total_rules_evaluated: number;
  rules_succeeded: number;
  rules_faulted: number;
  rules_no_fault: number;
  rules_skipped: number;
  rules_failed: number;
  total_elapsed_ms: number;
  poll_seconds: number;
  results: RuleExecutionResult[];
}

export interface ExecuteRuleRequest {
  building_id?: string | null;
  equipment_id?: string | null;
  rule_ids?: string[] | null;
  parameter_overrides?: Record<string, Record<string, number>> | null;
  poll_seconds?: number | null;
  start_utc?: string | null;
  end_utc?: string | null;
}

// ==========================================
// Telemetry & Graph Visualization Types
// ==========================================

export interface GraphSeries {
  role: string;
  name: string;
  unit: string;
  timestamps: string[];
  values: (number | null)[];
  chart_type: string;
  y_axis: string;
  color?: string | null;
}

export interface GraphPayload {
  graph_id: string;
  title: string;
  equipment_id: string;
  building_id?: string | null;
  category: string;
  series: GraphSeries[];
  fault_episodes: FaultEpisode[];
  sampling_interval_seconds: number;
  total_points: number;
  time_range: Record<string, string | null>;
}

export interface FaultTimelineLane {
  rule_id: string;
  rule_name: string;
  severity: string;
  total_fault_hours: number;
  episodes: FaultEpisode[];
}

export interface FaultTimelinePayload {
  equipment_id: string;
  building_id?: string | null;
  time_range: Record<string, string | null>;
  lanes: FaultTimelineLane[];
  total_fault_hours: number;
  total_episodes: number;
}

// ==========================================
// Dynamic Threshold Metadata Types
// ==========================================

export interface ThresholdItem {
  placeholder: string;
  param_name: string;
  label: string;
  category: string;
  tier: 'TIER_A' | 'TIER_B' | 'TIER_C';
  default_value: number;
  min_value: number;
  max_value: number;
  step: number;
  unit: string;
  description: string;
  applicable_rules: string[];
  equipment_kinds: string[];
}

export interface ThresholdCategory {
  name: string;
  display_order: number;
  description: string;
  tier: string;
}

export interface ThresholdCatalogResponse {
  categories: ThresholdCategory[];
  parameters: ThresholdItem[];
  presets: Record<string, Record<string, number>>;
  total_parameters: number;
  tier_a_count: number;
  tier_b_count: number;
}

// ==========================================
// Result Validation & Telemetry Tables
// ==========================================

export interface ResultValidationReport {
  overall_status: 'VALID' | 'WARNING' | 'INVALID' | string;
  rules_validated_count: number;
  rules_valid_count: number;
  rules_issue_count: number;
  findings_validated_count: number;
  findings_valid_count: number;
  findings_with_evidence_issues: number;
  duplicate_findings_count: number;
  reconciliation_errors_count: number;
  issues_summary: string[];
  rules_table: Array<Record<string, any>>;
  findings_table: Array<Record<string, any>>;
  reconciliation_table: Array<Record<string, any>>;
}

export interface HistorianTelemetryResponse {
  equipment_id: string;
  building_id: string;
  total_rows: number;
  min_timestamp?: string | null;
  max_timestamp?: string | null;
  columns: string[];
  records: Record<string, any>[];
}