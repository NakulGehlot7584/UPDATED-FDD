"""Dynamic Graph Data Engine for Open-FDD.

Generates structured JSON payloads for multi-axis telemetry graphs, rule-specific
fault investigations with episode bands, and composite fault swimlane timelines.
Large traces are downsampled for visualization while preserving episode boundaries.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

import numpy as np
import pyarrow.parquet as pq

from app.fdd.episodes import extract_fault_episodes
from app.fdd.models import (
    AvailableGraphCategory,
    FaultEpisode,
    FaultTimelineLane,
    FaultTimelinePayload,
    GraphPayload,
    GraphSeries,
    RuleDefinition,
    RuleExecutionResult,
)

# Open-FDD Distinct rainbow palette
RAINBOW_PALETTE: List[str] = [
    "#2563eb",  # blue
    "#dc2626",  # red
    "#16a34a",  # green
    "#ea580c",  # orange
    "#7c3aed",  # violet
    "#0891b2",  # cyan
    "#ca8a04",  # gold
    "#0d9488",  # teal
    "#db2777",  # pink
    "#65a30d",  # lime
    "#9333ea",  # purple
    "#e11d48",  # rose
]

ROLE_METADATA: Dict[str, Dict[str, str]] = {
    # Temperatures (Axis Y1)
    "sat": {"name": "Supply Air Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "sat_sp": {"name": "Supply Air Temp SP", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "mat": {"name": "Mixed Air Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "rat": {"name": "Return Air Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "oa_t": {"name": "Outdoor Air Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "oat": {"name": "Outdoor Air Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "zone_t": {"name": "Zone Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "zone_t_sp": {"name": "Zone Temp SP", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "zone_temp": {"name": "Zone Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "zone_temp_sp": {"name": "Zone Temp SP", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "chw_supply_t": {"name": "CHW Supply Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "chw_return_t": {"name": "CHW Return Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "chw_supply_sp": {"name": "CHW Supply Temp SP", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "hw_supply_t": {"name": "HW Supply Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "hw_return_t": {"name": "HW Return Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "chw_temp": {"name": "Chilled Water Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "hw_temp": {"name": "Hot Water Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "chw_st": {"name": "CHW Supply Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "chw_rt": {"name": "CHW Return Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "hw_st": {"name": "HW Supply Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "hw_rt": {"name": "HW Return Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "cw_supply_t": {"name": "CW Supply Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "cw_return_t": {"name": "CW Return Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "web_oa_t": {"name": "Web Outdoor Air Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "web_oa_dp": {"name": "Web Outdoor Dewpoint", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "web_wb_t": {"name": "Web Wet Bulb Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "cooling_coil_entering_temp": {"name": "Cooling Coil Entering Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "cooling_coil_leaving_temp": {"name": "Cooling Coil Leaving Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "heating_coil_entering_temp": {"name": "Heating Coil Entering Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "heating_coil_leaving_temp": {"name": "Heating Coil Leaving Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "vav_discharge_t": {"name": "VAV Discharge Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "vav_inlet_t": {"name": "VAV Inlet Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "preheat_leave_t": {"name": "Preheat Leaving Temp", "unit": "°F", "y_axis": "y1", "chart_type": "line"},
    "ahu_sat": {"name": "AHU SAT", "unit": "°F", "y_axis": "y1", "chart_type": "line"},

    # Percentages & Modulations (Axis Y2)
    "clg_valve_pct": {"name": "Cooling Valve Cmd", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "clg_valve_fbk": {"name": "Cooling Valve Fbk", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "clg_vlv": {"name": "Cooling Valve Cmd", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "htg_valve_pct": {"name": "Heating Valve Cmd", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "htg_vlv": {"name": "Heating Valve Cmd", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "reheat_valve_pct": {"name": "Reheat Valve Cmd", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "reheat_valve": {"name": "Reheat Valve Cmd", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "oa_damper_pct": {"name": "OA Damper Pos", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "oa_damper": {"name": "OA Damper Pos", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "damper_pct": {"name": "Damper Position", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "fan_vfd_speed": {"name": "Fan VFD Speed", "unit": "%", "y_axis": "y2", "chart_type": "line"},
    "fan_vfd_pct": {"name": "Fan VFD Speed", "unit": "%", "y_axis": "y2", "chart_type": "line"},

    # Humidity (Axis Y2)
    "zone_h": {"name": "Zone Humidity", "unit": "%RH", "y_axis": "y2", "chart_type": "line"},
    "oa_h": {"name": "Outdoor Humidity", "unit": "%RH", "y_axis": "y2", "chart_type": "line"},
    "web_oa_h": {"name": "Web Outdoor Humidity", "unit": "%RH", "y_axis": "y2", "chart_type": "line"},
    "room_humidity": {"name": "Room Humidity", "unit": "%RH", "y_axis": "y2", "chart_type": "line"},

    # Pressures (Axis Y3)
    "duct_static": {"name": "Duct Static Press", "unit": "in. w.c.", "y_axis": "y3", "chart_type": "line"},
    "duct_static_sp": {"name": "Duct Static SP", "unit": "in. w.c.", "y_axis": "y3", "chart_type": "line"},
    "bldg_static": {"name": "Building Static Press", "unit": "in. w.c.", "y_axis": "y3", "chart_type": "line"},
    "filter_dp": {"name": "Filter Diff Press", "unit": "in. w.c.", "y_axis": "y3", "chart_type": "line"},
    "chw_dp": {"name": "CHW Diff Press", "unit": "in. w.c.", "y_axis": "y3", "chart_type": "line"},
    "chw_dp_sp": {"name": "CHW Diff Press SP", "unit": "in. w.c.", "y_axis": "y3", "chart_type": "line"},

    # Airflow & Velocity (Axis Y3)
    "zone_flow": {"name": "Zone Airflow", "unit": "CFM", "y_axis": "y3", "chart_type": "line"},
    "zone_flow_sp": {"name": "Zone Airflow SP", "unit": "CFM", "y_axis": "y3", "chart_type": "line"},
    "min_flow_sp": {"name": "Min Airflow SP", "unit": "CFM", "y_axis": "y3", "chart_type": "line"},
    "oa_flow": {"name": "Outdoor Airflow", "unit": "CFM", "y_axis": "y3", "chart_type": "line"},
    "vav_total_flow": {"name": "VAV Total Airflow", "unit": "CFM", "y_axis": "y3", "chart_type": "line"},
    "oa_velocity": {"name": "OA Velocity", "unit": "FPM", "y_axis": "y3", "chart_type": "line"},
    "chw_flow": {"name": "CHW Water Flow", "unit": "GPM", "y_axis": "y3", "chart_type": "line"},

    # Gas Concentration (Axis Y3)
    "co2": {"name": "CO2 Concentration", "unit": "ppm", "y_axis": "y3", "chart_type": "line"},
    "co2_sp": {"name": "CO2 Setpoint", "unit": "ppm", "y_axis": "y3", "chart_type": "line"},

    # Power & Current (Axis Y3)
    "chiller_power": {"name": "Chiller Power", "unit": "kW", "y_axis": "y3", "chart_type": "line"},
    "chiller_current": {"name": "Chiller Current", "unit": "A", "y_axis": "y3", "chart_type": "line"},
    "chiller_amps": {"name": "Chiller Current", "unit": "A", "y_axis": "y3", "chart_type": "line"},

    # Binary Commands & States (Axis Y4)
    "fan_cmd": {"name": "Supply Fan Cmd", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "fan_status": {"name": "Supply Fan Status", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "occ_mode": {"name": "Occupied Mode", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "return_fan": {"name": "Return Fan Status", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "exhaust_fan_cmd": {"name": "Exhaust Fan Cmd", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "exhaust_fan_status": {"name": "Exhaust Fan Status", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "tower_fan_cmd": {"name": "Tower Fan Cmd", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "pump_status": {"name": "Pump Status", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "chw_pump_cmd": {"name": "CHW Pump Cmd", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "chw_pump_status": {"name": "CHW Pump Status", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "cw_pump_cmd": {"name": "CW Pump Cmd", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "chiller_cmd": {"name": "Chiller Cmd", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "chiller_status": {"name": "Chiller Status", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "compressor_status": {"name": "Compressor Status", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "clg_available": {"name": "Cooling Available", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "loop_enabled": {"name": "Loop Enabled", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "building_ahu_load_satisfied": {"name": "AHU Load Satisfied", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "building_zone_load_satisfied": {"name": "Zone Load Satisfied", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
    "static_reset_request": {"name": "Static Reset Request", "unit": "0/1", "y_axis": "y4", "chart_type": "step"},
}


def select_plot_indices(
    n_samples: int,
    max_points: int = 5000,
    preserved_indices: Optional[Sequence[int]] = None,
) -> np.ndarray:
    """Select sample indices for rendering: always keeps endpoints, preserved indices, and even grid."""
    if n_samples <= 0:
        return np.array([], dtype=int)
    if n_samples <= max_points:
        return np.arange(n_samples, dtype=int)

    must_keep: Set[int] = {0, n_samples - 1}
    if preserved_indices:
        for idx in preserved_indices:
            if 0 <= idx < n_samples:
                must_keep.add(int(idx))

    if len(must_keep) >= max_points:
        return np.array(sorted(must_keep)[:max_points], dtype=int)

    # Fill remaining slots with even grid
    grid = np.linspace(0, n_samples - 1, num=max_points, dtype=float)
    for g in grid:
        must_keep.add(int(round(g)))
        if len(must_keep) >= max_points:
            break

    if len(must_keep) < max_points:
        extra_grid = np.linspace(0, n_samples - 1, num=max_points * 2, dtype=float)
        for g in extra_grid:
            must_keep.add(int(round(g)))
            if len(must_keep) >= max_points:
                break

    return np.array(sorted(must_keep)[:max_points], dtype=int)


def get_available_graph_categories(columns: Sequence[str]) -> List[AvailableGraphCategory]:
    """Inspect present columns and return available visualization categories."""
    col_set = {c.lower() for c in columns}

    temp_roles = [
        "sat", "sat_sp", "mat", "rat", "oa_t", "oat", "zone_t", "zone_temp", "zone_t_sp", "zone_temp_sp",
        "chw_supply_t", "chw_return_t", "hw_supply_t", "hw_return_t", "chw_temp", "hw_temp", "web_oa_t",
        "cooling_coil_entering_temp", "cooling_coil_leaving_temp", "heating_coil_entering_temp", "heating_coil_leaving_temp"
    ]
    airside_roles = [
        "duct_static", "duct_static_sp", "fan_cmd", "fan_status", "fan_vfd_speed",
        "oa_damper_pct", "oa_damper", "damper_pct", "oa_velocity", "oa_flow",
        "exhaust_fan_cmd", "exhaust_fan_status", "return_fan", "bldg_static", "filter_dp"
    ]
    hydronic_roles = [
        "clg_valve_pct", "clg_valve_fbk", "clg_vlv", "htg_valve_pct", "htg_vlv",
        "reheat_valve_pct", "reheat_valve", "chw_supply_t", "chw_return_t",
        "hw_supply_t", "hw_return_t", "chw_temp", "hw_temp", "chw_flow",
        "chw_dp", "chw_dp_sp", "chw_pump_cmd", "chw_pump_status", "cw_pump_cmd",
        "cw_supply_t", "cw_return_t"
    ]
    zone_roles = [
        "zone_t", "zone_t_sp", "zone_temp", "zone_temp_sp", "zone_h", "co2", "co2_sp",
        "zone_flow", "min_flow_sp", "reheat_valve_pct", "vav_discharge_t", "vav_total_flow"
    ]

    categories = [
        AvailableGraphCategory(
            category_id="all_telemetry",
            title="All Points Telemetry",
            description="Complete multi-axis telemetry of all sensor and actuator points.",
            available_roles=[c for c in columns if c.lower() not in {"timestamp_utc", "equipment_id", "building_id"}],
            is_available=any(c not in {"timestamp_utc", "equipment_id", "building_id"} for c in col_set),
        ),
        AvailableGraphCategory(
            category_id="temperature_dynamics",
            title="Temperature Dynamics",
            description="Supply, mixed, return, outdoor air temperatures and setpoints.",
            available_roles=[c for c in columns if c.lower() in temp_roles],
            is_available=any(c.lower() in temp_roles for c in columns),
        ),
        AvailableGraphCategory(
            category_id="airside",
            title="Airside & Fan Controls",
            description="Duct static pressure, fan commands, speeds, and damper modulation.",
            available_roles=[c for c in columns if c.lower() in airside_roles],
            is_available=any(c.lower() in airside_roles for c in columns),
        ),
        AvailableGraphCategory(
            category_id="hydronic",
            title="Hydronic Valves & Temperatures",
            description="Cooling valves, heating valves, and water temperature dynamics.",
            available_roles=[c for c in columns if c.lower() in hydronic_roles],
            is_available=any(c.lower() in hydronic_roles for c in columns),
        ),
        AvailableGraphCategory(
            category_id="zone_comfort",
            title="Zone Comfort & Terminal Controls",
            description="Zone temperature tracking, heating/cooling airflow, and comfort bounds.",
            available_roles=[c for c in columns if c.lower() in zone_roles],
            is_available=any(c.lower() in zone_roles for c in columns),
        ),
    ]

    return categories


def load_equipment_parquet_table(
    parquet_path: Path,
    columns: Optional[List[str]] = None,
    start_utc: Optional[str] = None,
    end_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Read Parquet file and return dictionary of column arrays."""
    table = pq.read_table(parquet_path, columns=columns)
    df_dict: Dict[str, Any] = {}

    for name in table.column_names:
        arr = table[name].to_numpy(zero_copy_only=False)
        df_dict[name] = arr

    if "timestamp_utc" not in df_dict:
        return df_dict

    ts_arr = df_dict["timestamp_utc"]
    n_total = len(ts_arr)

    # Convert timestamps to datetime list
    ts_dts: List[datetime] = []
    ts_strs: List[str] = []
    for t in ts_arr:
        if isinstance(t, np.datetime64):
            # Convert to ISO string
            ts_sec = t.astype("datetime64[s]").astype(int)
            dt = datetime.utcfromtimestamp(ts_sec)
        elif isinstance(t, (int, float)):
            dt = datetime.utcfromtimestamp(t / 1e9 if t > 1e11 else t)
        elif isinstance(t, datetime):
            dt = t
        else:
            dt = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        ts_dts.append(dt)
        ts_strs.append(dt.isoformat())

    df_dict["_ts_dts"] = ts_dts
    df_dict["_ts_strs"] = ts_strs

    return df_dict


def build_telemetry_graph(
    parquet_path: Path,
    equipment_id: str,
    building_id: Optional[str] = None,
    category: Optional[str] = None,
    max_points: int = 5000,
    start_utc: Optional[str] = None,
    end_utc: Optional[str] = None,
) -> GraphPayload:
    """Build multi-axis telemetry graph payload from equipment parquet."""
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file {parquet_path} does not exist")

    data = load_equipment_parquet_table(parquet_path, start_utc=start_utc, end_utc=end_utc)
    if not data or "_ts_strs" not in data:
        return GraphPayload(
            graph_id=f"telemetry_{equipment_id}",
            title=f"Telemetry on {equipment_id}",
            equipment_id=equipment_id,
            building_id=building_id,
            category=category or "all_telemetry",
            series=[],
            fault_episodes=[],
        )

    ts_strs = data["_ts_strs"]
    n_samples = len(ts_strs)

    # Determine columns to plot
    ignore_cols = {"timestamp_utc", "equipment_id", "building_id", "_ts_dts", "_ts_strs"}
    avail_cols = [c for c in data.keys() if c not in ignore_cols]

    filter_roles: Optional[Set[str]] = None
    if category and category != "all_telemetry":
        cats = get_available_graph_categories(avail_cols)
        matched_cat = next((c for c in cats if c.category_id == category), None)
        if matched_cat:
            filter_roles = set(matched_cat.available_roles)

    cols_to_plot = [c for c in avail_cols if filter_roles is None or c.lower() in filter_roles]

    # Downsample
    idx_selected = select_plot_indices(n_samples, max_points=max_points)
    plot_ts = [ts_strs[i] for i in idx_selected]

    series_list: List[GraphSeries] = []
    color_i = 0

    for col in cols_to_plot:
        arr = data[col]
        meta = ROLE_METADATA.get(col.lower(), {})
        name = meta.get("name", col.replace("_", " ").title())
        unit = meta.get("unit", "")
        y_axis = meta.get("y_axis", "y1")
        chart_type = meta.get("chart_type", "line")
        color = RAINBOW_PALETTE[color_i % len(RAINBOW_PALETTE)]
        color_i += 1

        values: List[Optional[float]] = []
        for i in idx_selected:
            v = arr[i]
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                values.append(None)
            else:
                try:
                    values.append(round(float(v), 3))
                except (ValueError, TypeError):
                    values.append(None)

        series_list.append(
            GraphSeries(
                role=col,
                name=name,
                unit=unit,
                timestamps=plot_ts,
                values=values,
                chart_type=chart_type,
                y_axis=y_axis,
                color=color,
            )
        )

    time_range = {
        "start": plot_ts[0] if plot_ts else None,
        "end": plot_ts[-1] if plot_ts else None,
    }

    return GraphPayload(
        graph_id=f"telemetry_{equipment_id}",
        title=f"Telemetry on {equipment_id}",
        equipment_id=equipment_id,
        building_id=building_id,
        category=category or "all_telemetry",
        series=series_list,
        fault_episodes=[],
        total_points=len(plot_ts),
        time_range=time_range,
    )


def build_rule_graph(
    parquet_path: Path,
    equipment_id: str,
    rule_id: str,
    rule_def: Optional[RuleDefinition] = None,
    episodes: Optional[List[FaultEpisode]] = None,
    building_id: Optional[str] = None,
    max_points: int = 5000,
) -> GraphPayload:
    """Build a focused rule investigation graph with relevant telemetry and fault episode bands."""
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet file {parquet_path} does not exist")

    data = load_equipment_parquet_table(parquet_path)
    if not data or "_ts_strs" not in data:
        return GraphPayload(
            graph_id=f"rule_{rule_id}_{equipment_id}",
            title=f"Rule Investigation: {rule_id}",
            equipment_id=equipment_id,
            building_id=building_id,
            category="rule_specific",
            series=[],
            fault_episodes=episodes or [],
        )

    ts_strs = data["_ts_strs"]
    ts_dts = data.get("_ts_dts", [])
    n_samples = len(ts_strs)
    fault_eps = episodes or []

    # Preserve episode boundary indices in downsampling
    preserved_indices: List[int] = []
    if fault_eps and ts_dts:
        for ep in fault_eps:
            start_dt = datetime.fromisoformat(ep.start)
            end_dt = datetime.fromisoformat(ep.end)
            # Find closest indices
            for i, dt in enumerate(ts_dts):
                if dt >= start_dt:
                    preserved_indices.append(i)
                    break
            for i in range(len(ts_dts) - 1, -1, -1):
                if ts_dts[i] <= end_dt:
                    preserved_indices.append(i)
                    break

    # Determine roles relevant to this rule
    relevant_roles: List[str] = []
    if rule_def:
        for r in rule_def.required_roles:
            if r.lower() in [k.lower() for k in data.keys()] and r.lower() not in relevant_roles:
                relevant_roles.append(r.lower())
        for r in rule_def.optional_roles:
            if r.lower() in [k.lower() for k in data.keys()] and r.lower() not in relevant_roles:
                relevant_roles.append(r.lower())

    # Include associated roles from grounded diagnostic metadata
    from app.fdd.diagnostics import get_diagnostic_meta, CANONICAL_ROLE_ALIASES
    diag_meta = get_diagnostic_meta(rule_id, rule_def)
    for r in diag_meta.get("roles", []):
        canon_r = CANONICAL_ROLE_ALIASES.get(r.lower(), r.lower())
        for cand in [r.lower(), canon_r]:
            if cand in [k.lower() for k in data.keys()] and cand not in relevant_roles:
                relevant_roles.append(cand)

    # Key contextual telemetry channels matching D:\csvopenfdd and canonical role schema
    context_roles = [
        "sat", "sat_sp", "rat", "mat", "oa_t", "oat",
        "duct_static", "duct_static_sp", "fan_cmd", "fan_status", "fan_vfd_speed",
        "clg_valve_pct", "clg_valve_fbk", "clg_vlv", "htg_valve_pct", "htg_vlv",
        "oa_damper_pct", "oa_damper", "damper_pct",
        "chw_supply_t", "chw_return_t", "zone_t", "zone_h", "co2", "co2_sp"
    ]
    for r in context_roles:
        if r in [k.lower() for k in data.keys()] and r not in relevant_roles:
            relevant_roles.append(r)

    # Downsample
    idx_selected = select_plot_indices(n_samples, max_points=max_points, preserved_indices=preserved_indices)
    plot_ts = [ts_strs[i] for i in idx_selected]

    series_list: List[GraphSeries] = []
    color_i = 0

    for col in relevant_roles:
        # Match case-insensitively to data column
        data_col = next((c for c in data.keys() if c.lower() == col), None)
        if not data_col:
            continue

        arr = data[data_col]
        meta = ROLE_METADATA.get(col, {})
        name = meta.get("name", data_col.replace("_", " ").title())
        unit = meta.get("unit", "")
        y_axis = meta.get("y_axis", "y1")
        chart_type = meta.get("chart_type", "line")
        color = RAINBOW_PALETTE[color_i % len(RAINBOW_PALETTE)]
        color_i += 1

        values: List[Optional[float]] = []
        for i in idx_selected:
            v = arr[i]
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                values.append(None)
            else:
                try:
                    values.append(round(float(v), 3))
                except (ValueError, TypeError):
                    values.append(None)

        series_list.append(
            GraphSeries(
                role=col,
                name=name,
                unit=unit,
                timestamps=plot_ts,
                values=values,
                chart_type=chart_type,
                y_axis=y_axis,
                color=color,
            )
        )

    time_range = {
        "start": plot_ts[0] if plot_ts else None,
        "end": plot_ts[-1] if plot_ts else None,
    }

    return GraphPayload(
        graph_id=f"rule_{rule_id}_{equipment_id}",
        title=f"Rule {rule_id} Investigation on {equipment_id}",
        equipment_id=equipment_id,
        building_id=building_id,
        category="rule_specific",
        series=series_list,
        fault_episodes=fault_eps,
        total_points=len(plot_ts),
        time_range=time_range,
    )


def build_fault_timeline(
    equipment_id: str,
    rule_results: Sequence[RuleExecutionResult],
    building_id: Optional[str] = None,
) -> FaultTimelinePayload:
    """Build composite fault swimlane timeline across all executed rules."""
    lanes: List[FaultTimelineLane] = []
    all_starts: List[str] = []
    all_ends: List[str] = []
    total_fault_hours = 0.0
    total_episodes = 0

    for res in rule_results:
        # Check findings
        for f in res.findings:
            if not f.fault_detected or not f.episodes:
                continue

            rule_name = f.detail.rule_name if f.detail else res.rule_id
            severity = f.detail.severity if f.detail else f.severity
            hours = f.fault_hours or sum(e.duration_hours for e in f.episodes)

            lanes.append(
                FaultTimelineLane(
                    rule_id=res.rule_id,
                    rule_name=rule_name,
                    severity=severity,
                    total_fault_hours=round(hours, 4),
                    episodes=f.episodes,
                )
            )

            total_fault_hours += hours
            total_episodes += len(f.episodes)
            for ep in f.episodes:
                all_starts.append(ep.start)
                all_ends.append(ep.end)

    # Sort lanes by severity then total fault hours
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    lanes.sort(key=lambda l: (sev_order.get(l.severity, 99), -l.total_fault_hours))

    time_range = {
        "start": min(all_starts) if all_starts else None,
        "end": max(all_ends) if all_ends else None,
    }

    return FaultTimelinePayload(
        equipment_id=equipment_id,
        building_id=building_id,
        time_range=time_range,
        lanes=lanes,
        total_fault_hours=round(total_fault_hours, 4),
        total_episodes=total_episodes,
    )
