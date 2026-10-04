"""Rule Executor orchestrating DataFusion SQL execution over Parquet historian."""

from __future__ import annotations

import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.fdd.catalog import RuleCatalog, get_rule_catalog
from app.fdd.engine import DataFusionEngine, create_engine
from app.fdd.models import (
    FDDExecutionSummary,
    RuleDefinition,
    RuleExecutionResult,
    RuleExecutionStatus,
    RuleFinding,
)
from app.fdd.diagnostics import build_grounded_diagnostic
from app.fdd.episodes import extract_fault_episodes
from app.historian.storage import HistorianStorage

# Official Open-FDD standard default parameters
DEFAULT_SQL_PARAMS: Dict[str, str] = {
    "FIXED_FLOW_HOURS": "1",
    "FIXED_FLOW_MAX_STD": "15",
    "FIXED_FLOW_MIN_MEAN": "200",
    "HIGH_MIN_FLOW_SP": "250",
    "FLOW_ON_MIN": "25",
    "FULL_OPEN_PCT": "0.975",
    "SUSTAIN_HOURS": "1.5",
    "HTG_FULL_MIN": "0.9",
    "SAT_ERR": "1",
    "SETBACK_HI": "68",
    "FREE_COOL_OAT": "65",
    "REHEAT_PCT": "0.25",
    "RESET_ERR_F": "3",
    "RESET_SAT_AT_65": "52",
    "RESET_SLOPE": "0.25",
    "RESET_OAT_REF": "65",
    "ECON1_DAMPER_MAX": "0.05",
    "ECON1_OAT_MIN": "55",
    "ECON2_OAT_HI": "63",
    "ECON2_DAMPER": "0.42",
    "DUCT_HIGH_MARGIN": "0.25",
    "PRESSURE_ON_MIN": "0.2",
    "ALWAYS_ON_PCT": "0.95",
}


def derive_window_params(params: Dict[str, str], poll_seconds: float) -> Dict[str, str]:
    """Derive rolling window parameters (*_ROWS, *_ROWS_PRECEDING) from hourly and minute definitions."""
    derived: Dict[str, str] = {}
    poll = max(1.0, poll_seconds)
    for key, val in list(params.items()):
        if not key.endswith("_HOURS"):
            continue
        prefix = key[:-6]
        try:
            hours = float(val)
            if math.isfinite(hours) and hours > 0:
                rows = max(1, math.ceil(hours * 3600.0 / poll))
                if prefix == "FIXED_FLOW":
                    rows = max(6, rows)
                rows_key = f"{prefix}_ROWS"
                prec_key = f"{prefix}_ROWS_PRECEDING"
                min_p_key = f"{prefix}_MIN_PERIODS"
                if rows_key not in params and rows_key not in derived:
                    derived[rows_key] = str(rows)
                if prec_key not in params and prec_key not in derived:
                    derived[prec_key] = str(max(0, rows - 1))
                if min_p_key not in params and min_p_key not in derived:
                    derived[min_p_key] = str(max(3, rows // 2))
        except (ValueError, TypeError):
            continue

    # Open-FDD parity: derive *_ROWS and *_ROWS_PRECEDING from *_MIN parameters (e.g. MODE_DELAY_MIN, STARTUP_DELAY_MIN)
    for key, val in list(params.items()):
        if not key.endswith("_MIN"):
            continue
        if key in ("CONFIRM_MIN", "FAULT_CONFIRM_MIN", "MIN", "SAT_MIN", "MAT_MIN", "RAT_MIN", "FAN_ON_MIN", "CLG_ON_MIN", "HTG_ON_MIN", "PRESSURE_ON_MIN", "FLOW_ON_MIN"):
            continue
        prefix = key[:-4]
        try:
            minutes = float(val)
            if math.isfinite(minutes) and minutes >= 0:
                rows = 1 if minutes <= 0 else max(1, math.ceil(minutes * 60.0 / poll))
                rows_key = f"{prefix}_ROWS"
                prec_key = f"{prefix}_ROWS_PRECEDING"
                if rows_key not in params and rows_key not in derived:
                    derived[rows_key] = str(rows)
                if prec_key not in params and prec_key not in derived:
                    derived[prec_key] = str(max(0, rows - 1))
        except (ValueError, TypeError):
            continue

    return derived


def inject_optional_roles_cte(
    sql: str,
    optional_roles: List[str],
    available_columns: Set[str],
    table_name: str = "history",
    rule_id: Optional[str] = None,
) -> str:
    """Inject CAST(NULL AS ...) columns for optional roles missing from history table."""
    # Open-FDD runner.rs parity: FCU-SENSOR-NULL with missing zone_t returns zero hours
    if rule_id == "FCU-SENSOR-NULL" and "zone_t" not in available_columns:
        return f"SELECT equipment_id, CAST(0.0 AS DOUBLE) AS fault_hours FROM {table_name} GROUP BY equipment_id"

    missing = [r for r in optional_roles if r.lower() not in available_columns]
    if not missing:
        return sql

    null_projections = []
    for r in missing:
        ty = "VARCHAR" if r.lower() == "occ_mode" else "DOUBLE"
        null_projections.append(f'CAST(NULL AS {ty}) AS "{r}"')
    
    null_cols_str = ", ".join(null_projections)
    cte = f"history_opt AS (SELECT {table_name}.*, {null_cols_str} FROM {table_name})"

    # Replace references to FROM history with FROM history_opt
    rewritten = re.sub(rf"\bFROM\s+{table_name}\b", "FROM history_opt", sql, flags=re.IGNORECASE)

    # Look for SQL WITH keyword on its own line / not inside a comment
    lines = rewritten.splitlines()
    with_idx = None
    for i, line in enumerate(lines):
        trimmed = line.strip()
        if trimmed.startswith("--") or trimmed.startswith("/*"):
            continue
        if re.match(r"^\bWITH\b\s+", trimmed, flags=re.IGNORECASE):
            with_idx = i
            break

    if with_idx is not None:
        target_line = lines[with_idx]
        new_line = re.sub(r"^\s*WITH\s+", f"WITH {cte}, ", target_line, flags=re.IGNORECASE)
        lines[with_idx] = new_line
        return "\n".join(lines)
    else:
        return f"WITH {cte}\n{rewritten}"


def resolve_equipment_kind(
    equipment_id: str,
    telemetry_roles: Optional[List[str]] = None,
    source_file: Optional[str] = None,
    explicit_kind: Optional[str] = None,
) -> str:
    """Resolve the canonical equipment kind ('ahu', 'vav', 'chiller', 'boiler', 'heatpump', 'cooling_tower').

    Hierarchy:
    1. Explicit override (if provided via API/payload).
    2. Equipment ID or source file string pattern match (e.g. 'ahu', 'vav', 'chiller', 'boiler').
    3. Dominant role signature from telemetry channels.
    4. Default fallback: 'ahu'.
    """
    if explicit_kind and explicit_kind.strip():
        return explicit_kind.strip().lower()

    src = source_file or ""
    text_to_check = f"{equipment_id} {src}".lower()

    # Match standard ASHRAE/BMS naming tokens
    if re.search(r"\bahu\b|ahu[_\-\d]|air_?handling|air_?handler", text_to_check):
        return "ahu"
    if re.search(r"\bvav\b|vav[_\-\d]|terminal_?unit|\bfcu\b", text_to_check):
        return "vav"
    if re.search(r"\bchiller\b|\bchw\b|ch[_\-\d]+", text_to_check):
        return "chiller"
    if re.search(r"\bboiler\b|\bhw\b|\bblr\b|blr[_\-\d]|bl[_\-\d]+", text_to_check):
        return "boiler"
    if re.search(r"\bheat_?pump\b|\bhp\b|hp[_\-\d]+", text_to_check):
        return "heatpump"
    if re.search(r"\btower\b|cooling_?tower|\bct\b", text_to_check):
        return "cooling_tower"

    # Infer from telemetry roles
    if telemetry_roles:
        roles_set = {r.lower().strip() for r in telemetry_roles}
        if {"sat", "duct_static", "oa_damper_pct", "mat", "rat", "fan_cmd"}.intersection(roles_set):
            return "ahu"
        if {"zone_flow", "damper_pct", "vav_discharge_t"}.intersection(roles_set):
            return "vav"
        if {"chiller_status", "chw_pump_cmd", "chw_diff_p"}.intersection(roles_set):
            return "chiller"
        if {"boiler_status", "hw_supply_t"}.intersection(roles_set):
            return "boiler"

    return "unknown"


class RuleExecutor:
    """Executes official Open-FDD SQL rules against DataFusion tables."""

    def __init__(
        self,
        catalog: Optional[RuleCatalog] = None,
        engine: Optional[DataFusionEngine] = None,
        storage: Optional[HistorianStorage] = None,
    ):
        self.catalog = catalog if catalog is not None else get_rule_catalog()
        self.engine = engine if engine is not None else create_engine()
        self.storage = storage if storage is not None else HistorianStorage()

    def substitute_sql_params(
        self,
        sql_template: str,
        rule_def: RuleDefinition,
        poll_seconds: float,
        overrides: Optional[Dict[str, float]] = None,
    ) -> tuple[str, Dict[str, str]]:
        """Substitute parameters into SQL template string."""
        params: Dict[str, str] = dict(DEFAULT_SQL_PARAMS)
        params["POLL_SECONDS"] = str(poll_seconds)

        # Determine confirmation duration and rows
        # Priority order:
        # 1. Direct row/record persistence overrides: persistence_records, persistence_min, minimum_persistence_records, confirm_rows, CONFIRM_ROWS
        # 2. Minute overrides: confirm_min
        # 3. Seconds overrides: confirm_seconds, CONFIRM_SECONDS
        # 4. Catalog rule_def.confirm_seconds
        confirm_rows = None
        confirm_sec = None

        if overrides:
            for k in ("confirm_rows", "CONFIRM_ROWS", "persistence_records", "persistence_min", "minimum_persistence_records"):
                if k in overrides and overrides[k] is not None:
                    try:
                        confirm_rows = max(1, int(round(float(overrides[k]))))
                        confirm_sec = int(round(confirm_rows * poll_seconds))
                        break
                    except (ValueError, TypeError):
                        pass

            if confirm_rows is None and "confirm_min" in overrides and overrides["confirm_min"] is not None:
                try:
                    confirm_sec = int(round(float(overrides["confirm_min"]) * 60.0))
                    confirm_rows = max(1, math.ceil(confirm_sec / max(1.0, poll_seconds)))
                except (ValueError, TypeError):
                    pass

            if confirm_rows is None:
                for k in ("confirm_seconds", "CONFIRM_SECONDS"):
                    if k in overrides and overrides[k] is not None:
                        try:
                            confirm_sec = int(round(float(overrides[k])))
                            confirm_rows = max(1, math.ceil(confirm_sec / max(1.0, poll_seconds)))
                            break
                        except (ValueError, TypeError):
                            pass

        if confirm_rows is None or confirm_sec is None:
            confirm_sec = rule_def.confirm_seconds
            confirm_rows = max(1, math.ceil(confirm_sec / max(1.0, poll_seconds)))

        params["CONFIRM_SECONDS"] = str(confirm_sec)
        params["CONFIRM_ROWS"] = str(confirm_rows)

        # Apply rule definition parameter defaults
        for p_name, p_def in rule_def.parameters.items():
            placeholder = p_def.sql_placeholder.strip()
            params[placeholder] = str(p_def.default)

        # Apply overrides
        if overrides:
            for k, v in overrides.items():
                # Check matching parameter by name or placeholder
                applied = False
                for p_name, p_def in rule_def.parameters.items():
                    if k.lower() == p_name.lower() or k.upper() == p_def.sql_placeholder.upper():
                        params[p_def.sql_placeholder] = str(v)
                        applied = True
                        break
                if not applied:
                    params[k.upper()] = str(v)

        # Derive rolling window parameters
        derived = derive_window_params(params, poll_seconds)
        params.update(derived)

        # Replace placeholders {{KEY}}
        subbed_sql = sql_template
        for k, v in params.items():
            subbed_sql = subbed_sql.replace(f"{{{{{k}}}}}", v)

        return subbed_sql, params

    def execute_rule(
        self,
        rule_identifier: str,
        table_name: str = "history",
        poll_seconds: float = 300.0,
        parameter_overrides: Optional[Dict[str, float]] = None,
        equipment_filter: Optional[str] = None,
        building_id: Optional[str] = None,
    ) -> RuleExecutionResult:
        """Execute a single rule against registered DataFusion table."""
        rule_def = self.catalog.get_rule(rule_identifier)
        if not rule_def:
            return RuleExecutionResult(
                rule_id=rule_identifier,
                status=RuleExecutionStatus.ERROR,
                error=f"Rule '{rule_identifier}' not found in catalog",
            )

        start_time = time.perf_counter()
        available_cols = self.engine.get_table_columns(table_name)
        if not available_cols:
            return RuleExecutionResult(
                rule_id=rule_def.rule_id,
                status=RuleExecutionStatus.ERROR,
                error=f"Table '{table_name}' has no columns or is not registered",
            )

        # Check required roles gating (both schema existence and data availability)
        # Match official Open-FDD runner.py semantics: df[role].notna().any()
        missing_required = [r for r in rule_def.required_roles if r.lower() not in available_cols]
        if not missing_required and rule_def.required_roles:
            # Check if any required role has 100% missing (null/nan) values
            count_cols = [f'COUNT("{r.lower()}") AS "c_{r.lower()}"' for r in rule_def.required_roles]
            filter_clause = f" WHERE equipment_id = '{equipment_filter}'" if equipment_filter else ""
            count_sql = f"SELECT {', '.join(count_cols)} FROM {table_name}{filter_clause}"
            try:
                count_res = self.engine.query_to_dicts(count_sql)
                if count_res:
                    row_counts = count_res[0]
                    for r in rule_def.required_roles:
                        key = f"c_{r.lower()}"
                        if row_counts.get(key, 0) == 0:
                            missing_required.append(r)
            except Exception:
                pass

        if missing_required:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return RuleExecutionResult(
                rule_id=rule_def.rule_id,
                status=RuleExecutionStatus.SKIPPED_MISSING_ROLES,
                elapsed_ms=elapsed,
                missing_roles=missing_required,
                findings=[],
            )

        try:
            sql_raw = self.catalog.get_rule_sql(rule_def.rule_id)
            sql_with_params, used_params = self.substitute_sql_params(
                sql_raw, rule_def, poll_seconds, parameter_overrides
            )
            # Inject NULL columns for missing optional roles
            prepared_sql = inject_optional_roles_cte(
                sql_with_params, rule_def.optional_roles, available_cols, table_name, rule_id=rule_def.rule_id
            )

            # Optional filter by equipment
            if equipment_filter:
                # Wrap in query or filter
                pass

            rows = self.engine.query_to_dicts(prepared_sql)
            elapsed = (time.perf_counter() - start_time) * 1000.0

            # Query raw fault count and confirmed timestamps from subquery (ranked or grp2)
            raw_count: Optional[int] = None
            timestamps: List[str] = []
            confirm_rows = used_params.get("CONFIRM_ROWS", "1")
            idx_final = prepared_sql.lower().rfind("final as (")
            if idx_final != -1:
                try:
                    if "ranked" in prepared_sql.lower():
                        raw_sql = (
                            prepared_sql[:idx_final]
                            + "raw_query AS (SELECT COUNT(*) AS raw_count FROM ranked WHERE raw_fault = 1) "
                            + "SELECT raw_count FROM raw_query"
                        )
                        raw_res = self.engine.query_to_dicts(raw_sql)
                        if raw_res and "raw_count" in raw_res[0]:
                            raw_count = int(raw_res[0]["raw_count"])

                        ts_sql = (
                            prepared_sql[:idx_final]
                            + f"ts_query AS (SELECT timestamp_utc FROM ranked WHERE raw_fault = 1 AND streak_len >= {confirm_rows}) "
                            + f"SELECT timestamp_utc FROM ts_query ORDER BY timestamp_utc"
                        )
                        ts_rows = self.engine.query_to_dicts(ts_sql)
                        timestamps = [r["timestamp_utc"] for r in ts_rows if "timestamp_utc" in r]
                    elif "grp2" in prepared_sql.lower():
                        raw_sql = (
                            prepared_sql[:idx_final]
                            + "raw_query AS (SELECT COUNT(*) AS raw_count FROM grp2 WHERE sustained_fault = 1) "
                            + "SELECT raw_count FROM raw_query"
                        )
                        raw_res = self.engine.query_to_dicts(raw_sql)
                        if raw_res and "raw_count" in raw_res[0]:
                            raw_count = int(raw_res[0]["raw_count"])

                        ts_sql = (
                            prepared_sql[:idx_final]
                            + f"ts_query AS (SELECT timestamp_utc FROM grp2 WHERE sustained_fault = 1 "
                            + f"AND ROW_NUMBER() OVER (PARTITION BY equipment_id, streak2 ORDER BY timestamp_utc) >= {confirm_rows}) "
                            + f"SELECT timestamp_utc FROM ts_query ORDER BY timestamp_utc"
                        )
                        ts_rows = self.engine.query_to_dicts(ts_sql)
                        timestamps = [r["timestamp_utc"] for r in ts_rows if "timestamp_utc" in r]
                except Exception:
                    pass

            findings = []
            status = RuleExecutionStatus.NO_FAULT

            for row in rows:
                eq_id = str(row.get("equipment_id", equipment_filter or "UNKNOWN"))
                fault_hours = float(row.get("fault_hours", 0.0) or 0.0) if "fault_hours" in row else None
                fault_pct = float(row.get("fault_pct", 0.0) or 0.0) if "fault_pct" in row else None
                total_hours = float(row.get("total_hours", 0.0) or 0.0) if "total_hours" in row else None

                # Determine if confirmed fault detected
                fault_detected = False
                if "fan_runtime_hours" in row or "avg_zone_temp" in row or "comfort_pct" in row or "fault_samples" in row or rule_def.rule_id == "FAULT-ELAPSED-HOURS":
                    # Screening / descriptive metric rule
                    fault_detected = False
                elif len(timestamps) > 0:
                    fault_detected = True
                elif fault_hours is not None and fault_hours > 0.001:
                    fault_detected = True
                elif fault_pct is not None and fault_pct > 0.001:
                    fault_detected = True
                elif "status" in row and str(row.get("status", "")).upper() == "FAULT":
                    fault_detected = True

                episodes = []
                detail = None

                if fault_detected:
                    status = RuleExecutionStatus.FAULT_DETECTED
                    if timestamps:
                        _, episodes = extract_fault_episodes(timestamps, poll_seconds, equipment_prefix=eq_id)
                    if fault_hours is None or fault_hours <= 0.0:
                        fault_hours = round(len(timestamps) * poll_seconds / 3600.0, 4)

                    # Gather telemetry summary conditioned on confirmed fault timestamps
                    telemetry_summary = {}
                    try:
                        stat_roles = [r for r in ["sat", "sat_sp", "duct_static", "duct_static_sp", "fan_cmd", "fan_status", "clg_valve_pct", "htg_valve_pct"] if r in available_cols]
                        if stat_roles:
                            stat_exprs = [f"AVG({r}) AS {r}_mean" for r in stat_roles]
                            if idx_final != -1 and "ranked" in prepared_sql.lower() and timestamps:
                                stat_sql = (
                                    prepared_sql[:idx_final]
                                    + f"conf_ts AS (SELECT timestamp_utc FROM ranked WHERE raw_fault = 1 AND streak_len >= {confirm_rows}) "
                                    + f"SELECT {', '.join(stat_exprs)} FROM history WHERE timestamp_utc IN (SELECT timestamp_utc FROM conf_ts)"
                                )
                            elif idx_final != -1 and "grp2" in prepared_sql.lower() and timestamps:
                                stat_sql = (
                                    prepared_sql[:idx_final]
                                    + f"conf_ts AS (SELECT timestamp_utc FROM grp2 WHERE sustained_fault = 1 "
                                    + f"AND ROW_NUMBER() OVER (PARTITION BY equipment_id, streak2 ORDER BY timestamp_utc) >= {confirm_rows}) "
                                    + f"SELECT {', '.join(stat_exprs)} FROM history WHERE timestamp_utc IN (SELECT timestamp_utc FROM conf_ts)"
                                )
                            else:
                                stat_sql = f"SELECT {', '.join(stat_exprs)} FROM history"
                            stat_res = self.engine.query_to_dicts(stat_sql)
                            if stat_res:
                                for r in stat_roles:
                                    mean_v = stat_res[0].get(f"{r}_mean")
                                    if mean_v is not None:
                                        telemetry_summary[r] = {"mean": float(mean_v)}

                        # For sensor validation rules, identify specific faulted sensor roles
                        if rule_def.rule_id in ("SV-FLATLINE", "SV-STALE") and "win" in prepared_sql.lower() and timestamps and idx_final != -1:
                            sens = ["oa_t", "mat", "zone_t", "rat", "sat", "chw_supply_t", "chw_return_t", "hw_supply_t", "hw_return_t", "oa_h"]
                            rows_req = used_params.get("FLATLINE_ROWS" if rule_def.rule_id == "SV-FLATLINE" else "STALE_ROWS", "4")
                            tol = used_params.get("FLATLINE_TOL" if rule_def.rule_id == "SV-FLATLINE" else "STALE_TOL", "0.01")
                            sens_exprs = [f"MAX(CASE WHEN n_{s} >= {rows_req} AND span_{s} <= {tol} THEN 1 ELSE 0 END) AS flat_{s}" for s in sens if s in available_cols]
                            if sens_exprs:
                                q_sens = (
                                    prepared_sql[:idx_final]
                                    + f"conf_ts AS (SELECT timestamp_utc FROM ranked WHERE raw_fault = 1 AND streak_len >= {confirm_rows}) "
                                    + f"SELECT {', '.join(sens_exprs)} FROM win WHERE timestamp_utc IN (SELECT timestamp_utc FROM conf_ts)"
                                )
                                res_s = self.engine.query_to_dicts(q_sens)
                                if res_s:
                                    faulted_s = [s for s in sens if s in available_cols and res_s[0].get(f"flat_{s}") == 1]
                                    if faulted_s:
                                        telemetry_summary["faulted_sensors"] = faulted_s
                    except Exception:
                        pass

                    detail = build_grounded_diagnostic(
                        rule_id=rule_def.rule_id,
                        equipment_id=eq_id,
                        building_id=building_id,
                        metrics=row,
                        episodes=episodes,
                        telemetry_summary=telemetry_summary,
                        available_roles=available_cols,
                        rule_def=rule_def,
                        raw_sample_count=raw_count,
                    )

                desc = rule_def.description
                if fault_detected and fault_hours is not None:
                    desc += f" (Fault duration: {fault_hours:.2f} hours)"

                finding = RuleFinding(
                    equipment_id=eq_id,
                    building_id=building_id,
                    rule_id=rule_def.rule_id,
                    severity=rule_def.priority,
                    description=desc,
                    fault_detected=fault_detected,
                    fault_hours=fault_hours,
                    fault_pct=fault_pct,
                    total_hours=total_hours,
                    sample_count=len(timestamps),
                    raw_fault_count=raw_count,
                    metrics=row,
                    episodes=episodes,
                    detail=detail,
                )
                findings.append(finding)

            return RuleExecutionResult(
                rule_id=rule_def.rule_id,
                status=status,
                elapsed_ms=elapsed,
                row_count=len(rows),
                findings=findings,
                parameters_used=used_params,
                executed_sql=prepared_sql,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            err_msg = str(e)
            err_lower = err_msg.lower()

            # Open-FDD parity: missing weather table or missing column schema is a skip
            if "weather" in err_lower and "not found" in err_lower:
                return RuleExecutionResult(
                    rule_id=rule_def.rule_id,
                    status=RuleExecutionStatus.SKIPPED_MISSING_ROLES,
                    elapsed_ms=elapsed,
                    missing_roles=["weather"],
                    findings=[],
                )
            if "no field named" in err_lower or ("column" in err_lower and "not found" in err_lower):
                return RuleExecutionResult(
                    rule_id=rule_def.rule_id,
                    status=RuleExecutionStatus.SKIPPED_MISSING_ROLES,
                    elapsed_ms=elapsed,
                    missing_roles=["schema_column_missing"],
                    findings=[],
                )

            return RuleExecutionResult(
                rule_id=rule_def.rule_id,
                status=RuleExecutionStatus.ERROR,
                elapsed_ms=elapsed,
                error=err_msg,
                executed_sql=prepared_sql if "prepared_sql" in locals() else None,
            )

    def execute_rules_for_equipment(
        self,
        equipment_id: str,
        building_id: Optional[str] = None,
        equipment_kind: Optional[str] = None,
        rule_ids: Optional[List[str]] = None,
        parameter_overrides: Optional[Dict[str, Dict[str, float]]] = None,
        poll_seconds: Optional[float] = None,
    ) -> FDDExecutionSummary:
        """Register equipment parquet and execute applicable or selected rules."""
        start_time = time.perf_counter()
        
        # Locate equipment file
        hist_meta = None
        parquet_path = None
        building = building_id

        if building:
            p = self.storage.get_parquet_path(building, equipment_id)
            if p.exists():
                parquet_path = p
        else:
            # Scan historian partitions for this equipment directly
            for b_dir in self.storage.root_dir.glob("building=*"):
                b_name = b_dir.name.split("=")[1]
                p = self.storage.get_parquet_path(b_name, equipment_id)
                if p.exists():
                    parquet_path = p
                    building = b_name
                    break

        # Fallback: check if equipment_id matches sidecar metadata (dataset_id, source file, or case-insensitive)
        if not parquet_path or not parquet_path.exists():
            import json
            for b_dir in self.storage.root_dir.glob("building=*"):
                b_name = b_dir.name.split("=")[1]
                for eq_dir in b_dir.glob("equipment=*"):
                    meta_path = eq_dir / "metadata.json"
                    if meta_path.exists():
                        try:
                            with open(meta_path, "r", encoding="utf-8") as mf:
                                m = json.load(mf)
                            src_file = str(m.get("source_file", ""))
                            eq_name = str(m.get("equipment_id", eq_dir.name.split("=")[1]))
                            p_file = eq_dir / "history.parquet"
                            if p_file.exists() and (
                                equipment_id.lower() == eq_name.lower()
                                or equipment_id.lower() in src_file.lower()
                                or Path(src_file).stem.lower() == equipment_id.lower()
                                or Path(src_file).name.lower() == equipment_id.lower()
                            ):
                                parquet_path = p_file
                                building = b_name
                                equipment_id = eq_name
                                break
                        except Exception:
                            pass
                if parquet_path and parquet_path.exists():
                    break

        if not parquet_path or not parquet_path.exists():
            raise FileNotFoundError(
                f"History Parquet not found for equipment '{equipment_id}' (building: {building})"
            )

        # Register table in DataFusion
        self.engine.register_parquet_file("history", parquet_path)

        # Register weather table for rules with weather sidecar joins (ECON-3, ECON-6, ECON-7, OAT-METEO)
        if not self.engine.table_exists("weather"):
            if building:
                wx_path = self.storage.root_dir / f"building={building}" / "equipment=WEATHER" / "history.parquet"
                if wx_path.exists():
                    try:
                        self.engine.register_parquet_file("weather", wx_path)
                    except Exception:
                        pass
            # Open-FDD runner.rs parity: if weather table is not present on disk, do NOT inject
            # a fake null table that causes silent false negatives. Allow DataFusion to raise
            # table 'weather' not found, which is classified as SKIPPED_MISSING_ROLES (Issue 32).

        # Extract metadata and telemetry roles for equipment scoping
        source_file = None
        meta_file = None
        meta_candidates = [
            parquet_path.parent / ".history.parquet.meta.json",
            parquet_path.parent / "metadata.json",
        ]
        if building:
            meta_candidates.append(self.storage.get_meta_path(building, equipment_id))

        for mc in meta_candidates:
            if mc and mc.exists():
                meta_file = mc
                break

        if meta_file and meta_file.exists():
            try:
                import json
                with open(meta_file, "r", encoding="utf-8") as mf:
                    m = json.load(mf)
                    source_file = m.get("source_file")
            except Exception:
                pass

        telemetry_roles = list(self.engine.get_table_columns("history"))
        target_kind = resolve_equipment_kind(
            equipment_id=equipment_id,
            telemetry_roles=telemetry_roles,
            source_file=source_file,
            explicit_kind=equipment_kind,
        )

        # Determine effective poll seconds
        effective_poll = poll_seconds
        if effective_poll is None and meta_file and meta_file.exists():
            try:
                import json
                with open(meta_file, "r", encoding="utf-8") as mf:
                    m = json.load(mf)
                    val = m.get("sampling_interval_seconds")
                    if val is not None and float(val) > 0:
                        effective_poll = float(val)
            except Exception:
                pass

        # If metadata did not contain it, calculate cadence directly from timestamp_utc in history table
        if effective_poll is None or effective_poll <= 0:
            try:
                res = self.engine.query_to_dicts(
                    "SELECT timestamp_utc FROM history ORDER BY timestamp_utc LIMIT 100"
                )
                if len(res) > 1:
                    import pandas as pd
                    ts = pd.to_datetime([r["timestamp_utc"] for r in res if r.get("timestamp_utc") is not None])
                    deltas = ts.to_series().diff().dropna().dt.total_seconds()
                    pos_deltas = deltas[deltas > 0]
                    if len(pos_deltas) > 0:
                        effective_poll = float(pos_deltas.median())
            except Exception:
                pass

        # Final fallback ONLY if cadence genuinely cannot be determined
        if effective_poll is None or effective_poll <= 0:
            effective_poll = 300.0

        # Determine rules to run based on equipment kind or explicit selection
        total_catalog = len(self.catalog)
        if rule_ids:
            rules_to_run = [self.catalog.get_rule(rid) for rid in rule_ids if self.catalog.get_rule(rid)]
            applicable_count = len(rules_to_run)
            non_applicable_count = total_catalog - applicable_count
        else:
            # Filter by resolved equipment kind (Open-FDD parity: run applicable rules for target equipment)
            rules_to_run = self.catalog.list_rules(equipment_kind=target_kind)
            applicable_count = len(rules_to_run)
            non_applicable_count = total_catalog - applicable_count

        results: List[RuleExecutionResult] = []
        rules_succeeded = 0
        rules_faulted = 0
        rules_no_fault = 0
        rules_skipped = 0
        rules_failed = 0

        global_overrides = (parameter_overrides or {}).get("GLOBAL", {})

        for r_def in rules_to_run:
            is_cmd = r_def.rule_id.upper().startswith("CMD-")
            overrides = dict(global_overrides)
            if is_cmd:
                for cmd_k in ("command_persistence", "command_persistence_records", "cmd_persistence"):
                    if cmd_k in overrides:
                        overrides["persistence_records"] = overrides[cmd_k]
                        break
            rule_overrides = (parameter_overrides or {}).get(r_def.rule_id)
            if rule_overrides:
                overrides.update(rule_overrides)

            res = self.execute_rule(
                rule_identifier=r_def.rule_id,
                table_name="history",
                poll_seconds=effective_poll,
                parameter_overrides=overrides if overrides else None,
                equipment_filter=equipment_id,
                building_id=building,
            )
            results.append(res)
            if res.status == RuleExecutionStatus.FAULT_DETECTED:
                rules_faulted += 1
                rules_succeeded += 1
            elif res.status == RuleExecutionStatus.NO_FAULT:
                rules_no_fault += 1
                rules_succeeded += 1
            elif res.status == RuleExecutionStatus.SKIPPED_MISSING_ROLES:
                rules_skipped += 1
            elif res.status == RuleExecutionStatus.ERROR:
                rules_failed += 1

        total_elapsed = (time.perf_counter() - start_time) * 1000.0

        return FDDExecutionSummary(
            building_id=building,
            equipment_id=equipment_id,
            equipment_kind=target_kind,
            total_catalog_rules=total_catalog,
            applicable_rules=applicable_count,
            non_applicable_rules=non_applicable_count,
            total_rules_evaluated=len(results),
            rules_succeeded=rules_succeeded,
            rules_faulted=rules_faulted,
            rules_no_fault=rules_no_fault,
            rules_skipped=rules_skipped,
            rules_failed=rules_failed,
            total_elapsed_ms=total_elapsed,
            poll_seconds=effective_poll,
            results=results,
        )


def get_executor(
    catalog: Optional[RuleCatalog] = None,
    engine: Optional[DataFusionEngine] = None,
    storage: Optional[HistorianStorage] = None,
    storage_layout: Optional[HistorianStorage] = None,
) -> RuleExecutor:
    """Convenience factory for RuleExecutor."""
    eff_storage = storage if storage is not None else storage_layout
    return RuleExecutor(catalog=catalog, engine=engine, storage=eff_storage)
