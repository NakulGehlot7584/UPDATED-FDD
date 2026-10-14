"""Sensor-Level Fault Attribution Engine for Open-FDD.

Maps rule-level fault findings to granular sensor associations, preserving
canonical roles, original CSV column names, human display labels, physical units,
observed measurements, specific detected conditions, and verified intervals.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set
from app.fdd.models import (
    FaultEpisode,
    RuleDefinition,
    SensorFaultDetail,
)
from app.transformation.units import CANONICAL_ROLE_UNITS


# Standard engineering display names for canonical HVAC roles
ROLE_DISPLAY_NAMES: Dict[str, str] = {
    "sat": "Supply Air Temperature",
    "sat_sp": "Supply Air Temp Setpoint",
    "mat": "Mixed Air Temperature",
    "rat": "Return Air Temperature",
    "oa_t": "Outdoor Air Temperature",
    "oa_h": "Outdoor Air Relative Humidity",
    "duct_static": "Duct Static Pressure",
    "duct_static_sp": "Duct Static Setpoint",
    "oa_damper_pct": "Outdoor Air Damper Position",
    "damper_pct": "Damper Position Feedback",
    "damper_cmd": "Damper Control Command",
    "clg_valve_pct": "Cooling Coil Valve Position",
    "htg_valve_pct": "Heating Coil Valve Position",
    "reheat_valve_pct": "Reheat Coil Valve Position",
    "fan_cmd": "Supply Fan Command",
    "fan_status": "Supply Fan Status Feedback",
    "return_fan": "Return Fan Command",
    "zone_t": "Zone Temperature",
    "zone_air_temp_sp": "Zone Temperature Setpoint",
    "zone_flow": "Zone Airflow Measurement",
    "vav_total_flow": "Total VAV Airflow",
    "min_flow_sp": "Minimum Airflow Setpoint",
    "occ_mode": "Occupancy Mode",
    "chiller_status": "Chiller Operating Status",
    "chiller_cmd": "Chiller Run Command",
    "chw_pump_cmd": "Chilled Water Pump Command",
    "chw_pump_status": "Chilled Water Pump Status",
    "chw_supply_t": "Chilled Water Supply Temperature",
    "chw_return_t": "Chilled Water Return Temperature",
    "chw_supply_sp": "Chilled Water Supply Setpoint",
    "chw_dp": "Chilled Water Differential Pressure",
    "chw_dp_sp": "Chilled Water DP Setpoint",
    "chw_flow": "Chilled Water Flow Rate",
    "hw_supply_t": "Hot Water Supply Temperature",
    "hw_return_t": "Hot Water Return Temperature",
    "cw_supply_t": "Condenser Water Supply Temperature",
    "cw_return_t": "Condenser Water Return Temperature",
    "tower_fan_cmd": "Cooling Tower Fan Command",
    "web_oa_t": "Meteorological Outdoor Air Temp",
    "web_wb_t": "Outdoor Wet-Bulb Temperature",
    "web_oa_dp": "Outdoor Dewpoint Temperature",
    "preheat_leave_t": "Preheat Coil Leaving Temp",
    "cooling_coil_entering_temp": "Cooling Coil Entering Water Temp",
    "cooling_coil_leaving_temp": "Cooling Coil Leaving Water Temp",
    "heating_coil_entering_temp": "Heating Coil Entering Water Temp",
    "heating_coil_leaving_temp": "Heating Coil Leaving Water Temp",
    "vav_discharge_t": "VAV Discharge Air Temp",
    "vav_inlet_t": "VAV Inlet Air Temp",
    "ahu_sat": "AHU Supply Air Temp (Upstream)",
    "zone_co2": "Zone Carbon Dioxide (CO2)",
    "co2": "Zone Carbon Dioxide (CO2)",
    "co2_sp": "CO2 Ventilation Setpoint",
    "cooling_sp": "Cooling Temp Setpoint",
    "heating_sp": "Heating Temp Setpoint",
}

# Physical boundary catalog for sensor validation range checks
SENSOR_RANGE_LIMITS: Dict[str, tuple[float, float, str]] = {
    "oa_t": (-60.0, 130.0, "°F"),
    "mat": (-20.0, 110.0, "°F"),
    "zone_t": (40.0, 100.0, "°F"),
    "rat": (40.0, 100.0, "°F"),
    "sat": (30.0, 150.0, "°F"),
    "chw_supply_t": (30.0, 80.0, "°F"),
    "chw_return_t": (30.0, 90.0, "°F"),
    "hw_supply_t": (40.0, 220.0, "°F"),
    "hw_return_t": (40.0, 220.0, "°F"),
    "oa_h": (0.0, 100.0, "%"),
    "duct_static": (-1.0, 8.0, "in_wc"),
}

# Rule specific conditions / explanations for multi-sensor and pair rules
ROLE_CONDITION_EXPLANATIONS: Dict[str, Dict[str, tuple[str, str]]] = {
    # rule_id -> {role -> (error_type, sensor_role_type)}
    "CMD-1": {
        "fan_status": ("Fan run status feedback indicates OFF (0) while command is ON", "primary"),
        "fan_cmd": ("Supply fan commanded to run (ON / 100%)", "control_command"),
    },
    "AHU-SATDEV": {
        "sat": ("Supply air temp deviating from setpoint by > threshold", "primary"),
        "sat_sp": ("Active supply air temperature setpoint", "reference_setpoint"),
    },
    "AHU-DUCTHI": {
        "duct_static": ("Duct static pressure exceeding setpoint + margin", "primary"),
        "duct_static_sp": ("Target duct static pressure setpoint", "reference_setpoint"),
        "fan_cmd": ("Supply fan operating at elevated speed", "control_command"),
    },
    "AHU-SIMUL": {
        "clg_valve_pct": ("Cooling coil valve commanded open (> 5%) simultaneously with heating", "primary"),
        "htg_valve_pct": ("Heating coil valve commanded open (> 5%) simultaneously with cooling", "primary"),
    },
    "RESET-1": {
        "sat_sp": ("Supply air temp setpoint not resetting with outdoor temperature", "primary"),
        "oa_t": ("Outdoor air temperature reference for reset schedule", "reference_setpoint"),
    },
    "CHW-1": {
        "chw_supply_t": ("Chilled water supply temperature measurement (low delta-T)", "primary"),
        "chw_return_t": ("Chilled water return temperature measurement (low delta-T)", "primary"),
    },
    "CHW-2": {
        "chw_dp": ("Chilled water differential pressure below setpoint", "primary"),
        "chw_dp_sp": ("Target chilled water differential pressure setpoint", "reference_setpoint"),
        "chw_pump_cmd": ("Chilled water pump at maximum capacity", "control_command"),
    },
    "CHW-3": {
        "chw_supply_t": ("Chilled water supply temp above acceptable band", "primary"),
        "chw_supply_sp": ("Target chilled water supply temperature setpoint", "reference_setpoint"),
        "chw_pump_cmd": ("Chilled water pump running", "control_command"),
    },
    "CHW-4": {
        "chw_flow": ("Chilled water flow rate below minimum threshold", "primary"),
        "chw_pump_cmd": ("Chilled water pump commanded ON", "control_command"),
    },
    "VAV-2": {
        "zone_t": ("Zone temperature violated unoccupied night setback limit", "primary"),
        "occ_mode": ("Occupancy schedule mode indicating unoccupied period", "control_command"),
    },
    "VAV-3": {
        "reheat_valve_pct": ("Reheat coil valve open (> 25%) when outdoor air is warm", "primary"),
        "oa_t": ("Outdoor air temperature above free cooling threshold", "context"),
        "zone_flow": ("Zone airflow measurement", "context"),
    },
    "VAV-4": {
        "damper_pct": ("VAV damper fully open (>= 97.5%)", "primary"),
        "zone_flow": ("Zone airflow starved below active setpoint", "primary"),
    },
    "VAV-5": {
        "zone_flow": ("Airflow sensor reading biased or out of calibration", "primary"),
        "damper_pct": ("VAV damper position reference feedback", "reference_setpoint"),
    },
    "VAV-6": {
        "reheat_valve_pct": ("Reheat valve active during economizer / free cooling weather", "primary"),
        "oa_t": ("Outdoor air temperature reference", "context"),
    },
    "FCU-DAMPER-POS": {
        "damper_pct": ("Damper position feedback differs from commanded position", "primary"),
        "damper_cmd": ("Damper control command", "control_command"),
    },
    "FCU-CO2-DAMPER": {
        "zone_co2": ("Zone CO2 exceeds threshold with ventilation damper closed", "primary"),
        "damper_cmd": ("Outdoor air damper command restricted", "control_command"),
    },
    "FCU-DEADBAND": {
        "cooling_sp": ("Cooling setpoint too close to heating setpoint (deadband < threshold)", "reference_setpoint"),
        "heating_sp": ("Heating setpoint too close to cooling setpoint (deadband < threshold)", "reference_setpoint"),
    },
    "FCU-MODE-CYCLE": {
        "htg_valve_pct": ("Heating valve cycling rapidly between open and closed", "primary"),
        "clg_valve_pct": ("Cooling valve cycling rapidly between open and closed", "primary"),
    },
    # Multi-sensor Airside & Economizer rules (Equipment-Level)
    "FC1": {
        "duct_static": ("Airside discharge static pressure measured below setpoint", "equipment_component"),
        "duct_static_sp": ("Target duct static pressure setpoint", "equipment_component"),
        "fan_cmd": ("Supply fan command at 100% capacity", "equipment_component"),
    },
    "FC2": {
        "mat": ("Mixed air temperature outside outdoor and return boundaries", "equipment_component"),
        "oa_t": ("Outdoor air temperature boundary for mixing energy balance", "equipment_component"),
        "rat": ("Return air temperature boundary for mixing energy balance", "equipment_component"),
        "fan_cmd": ("Supply fan operating gate proving airside flow", "equipment_component"),
    },
    "FC3": {
        "mat": ("Mixed air temp equals return air temp while OA damper open", "equipment_component"),
        "rat": ("Return air temp benchmark for airside mixing", "equipment_component"),
        "oa_t": ("Outdoor air temperature benchmark", "equipment_component"),
        "oa_damper_pct": ("Outdoor air damper command open (> minimum)", "equipment_component"),
    },
    "FC4": {
        "oa_damper_pct": ("Outdoor air damper open in heating mode", "equipment_component"),
        "clg_valve_pct": ("Cooling valve open in heating mode", "equipment_component"),
        "htg_valve_pct": ("Heating coil active in heating mode", "equipment_component"),
        "fan_cmd": ("Supply fan proved running", "equipment_component"),
    },
    "FC5": {
        "sat": ("Supply air temp colder than mixed air temp in heating", "equipment_component"),
        "mat": ("Mixed air temp reference entering heating coil", "equipment_component"),
        "htg_valve_pct": ("Heating coil valve open (> minimum threshold)", "equipment_component"),
        "fan_cmd": ("Supply fan proved running", "equipment_component"),
    },
    "FC6": {
        "mat": ("Mixed air temp measured in airside mixing plenum", "equipment_component"),
        "rat": ("Return air temp measured entering mixing plenum", "equipment_component"),
        "oa_t": ("Outdoor air temp measured entering economizer", "equipment_component"),
        "vav_total_flow": ("Total airside volumetric flow rate", "equipment_component"),
        "fan_cmd": ("Supply fan operating status", "equipment_component"),
    },
    "FC7": {
        "sat": ("Supply air temp below setpoint during full heating", "equipment_component"),
        "sat_sp": ("Target supply air temperature setpoint", "equipment_component"),
        "htg_valve_pct": ("Heating coil valve at maximum position (100%)", "equipment_component"),
    },
    "FC8": {
        "sat": ("Supply air temp warmer than mixed air temp while economizing", "equipment_component"),
        "mat": ("Mixed air temp reference entering cooling coil", "equipment_component"),
        "oa_damper_pct": ("Outdoor air damper position modulating for economizing", "equipment_component"),
        "clg_valve_pct": ("Cooling coil valve closed", "equipment_component"),
    },
    "FC9": {
        "oa_t": ("Outdoor air temp higher than supply setpoint during economizer", "equipment_component"),
        "sat_sp": ("Target supply air temp setpoint", "equipment_component"),
        "oa_damper_pct": ("Outdoor air damper open (> minimum)", "equipment_component"),
        "clg_valve_pct": ("Cooling coil valve inactive", "equipment_component"),
    },
    "FC10": {
        "mat": ("Mixed air temp significantly warmer than outdoor air during 100% OA economizing", "equipment_component"),
        "oa_t": ("Outdoor air temp reference", "equipment_component"),
        "oa_damper_pct": ("Outdoor air damper at full open position (100%)", "equipment_component"),
        "clg_valve_pct": ("Cooling coil valve active", "equipment_component"),
    },
    "FC11": {
        "oa_t": ("Outdoor air temp significantly lower than supply setpoint in mechanical cooling", "equipment_component"),
        "sat_sp": ("Target supply air temperature setpoint", "equipment_component"),
        "oa_damper_pct": ("Outdoor air damper position", "equipment_component"),
        "clg_valve_pct": ("Cooling coil valve active", "equipment_component"),
    },
    "FC12": {
        "sat": ("Supply air temp warmer than mixed air temp during mechanical cooling", "equipment_component"),
        "mat": ("Mixed air temp entering cooling coil", "equipment_component"),
        "oa_damper_pct": ("Outdoor air damper position", "equipment_component"),
        "clg_valve_pct": ("Cooling coil valve commanded open (100%)", "equipment_component"),
    },
    "FC13-SAT-HIGH": {
        "sat": ("Supply air temp above setpoint in full cooling mode", "equipment_component"),
        "sat_sp": ("Target supply air temperature setpoint", "equipment_component"),
        "clg_valve_pct": ("Cooling coil valve at 100% position", "equipment_component"),
        "oa_damper_pct": ("Outdoor air damper position", "equipment_component"),
    },
    "ECON-1": {
        "fan_cmd": ("Supply fan proved running", "equipment_component"),
        "oa_damper_pct": ("Outdoor air damper stuck closed during favorable economizer conditions", "equipment_component"),
        "oa_t": ("Outdoor air temperature favorable for free cooling", "equipment_component"),
    },
    "ECON-2": {
        "oa_t": ("Outdoor air temperature above economizer high limit", "equipment_component"),
        "oa_damper_pct": ("Outdoor air damper open (> minimum) when economizer should be disabled", "equipment_component"),
    },
}


def resolve_sensor_attributions(
    rule_def: RuleDefinition,
    equipment_id: str,
    episodes: List[FaultEpisode],
    telemetry_summary: Dict[str, Any],
    column_mappings: Dict[str, str],
    available_roles: Set[str],
    engine: Optional[Any] = None,
    poll_seconds: float = 300.0,
) -> List[SensorFaultDetail]:
    """Resolve and build granular SensorFaultDetail records for a detected fault finding."""
    rule_id = rule_def.rule_id
    clean_id = rule_id.upper()
    sensors: List[SensorFaultDetail] = []

    first_start = episodes[0].start if episodes else None
    last_end = episodes[-1].end if episodes else None
    tot_hours = round(sum(e.duration_hours for e in episodes), 2) if episodes else None

    # Helper to resolve display name, source column, unit, and observed value
    def _make_sensor(
        role: str,
        error_type: str,
        role_type: str = "primary",
        interval_avail: bool = True,
        s_start: Optional[str] = None,
        s_end: Optional[str] = None,
        s_hours: Optional[float] = None,
        s_obs: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> SensorFaultDetail:
        disp_name = ROLE_DISPLAY_NAMES.get(role, role.replace("_", " ").title())
        src_col = column_mappings.get(role, role)
        unit = CANONICAL_ROLE_UNITS.get(role, "")

        obs_val = s_obs
        if obs_val is None and role in telemetry_summary and "mean" in telemetry_summary[role]:
            try:
                obs_val = round(float(telemetry_summary[role]["mean"]), 2)
            except Exception:
                pass

        return SensorFaultDetail(
            sensor_name=disp_name,
            canonical_role=role,
            source_column=src_col,
            error_type=error_type,
            fault_start=s_start if interval_avail else None,
            fault_end=s_end if interval_avail else None,
            duration_hours=s_hours if interval_avail else None,
            observed_value=obs_val,
            unit=unit if unit else None,
            sensor_role_type=role_type,
            interval_available=interval_avail,
            notes=notes,
        )

    # -------------------------------------------------------------
    # 1. SENSOR VALIDATION RULES (SV-RANGE, SV-FLATLINE, SV-STALE, SV-SPIKE, SV-RATE)
    # -------------------------------------------------------------
    if clean_id == "SV-RANGE":
        # Check specific sensors that violated range limits
        range_candidates = [
            "oa_t", "mat", "zone_t", "rat", "sat",
            "chw_supply_t", "chw_return_t", "hw_supply_t", "hw_return_t",
            "oa_h", "duct_static"
        ]
        faulted_roles = []
        if engine and engine.table_exists("history"):
            for cand in range_candidates:
                if cand not in available_roles:
                    continue
                min_lim, max_lim, u = SENSOR_RANGE_LIMITS[cand]
                try:
                    q = (
                        f"SELECT MIN({cand}) AS min_v, MAX({cand}) AS max_v, AVG({cand}) AS avg_v, "
                        f"COUNT(*) AS out_cnt, MIN(timestamp_utc) AS s_start, MAX(timestamp_utc) AS s_end "
                        f"FROM history WHERE {cand} IS NOT NULL AND ({cand} < {min_lim} OR {cand} > {max_lim})"
                    )
                    res = engine.query_to_dicts(q)
                    if res and res[0].get("out_cnt") and int(res[0]["out_cnt"]) > 0:
                        row = res[0]
                        cnt = int(row["out_cnt"])
                        dur = round(cnt * poll_seconds / 3600.0, 2)
                        st = str(row["s_start"]) if row.get("s_start") else first_start
                        en = str(row["s_end"]) if row.get("s_end") else last_end
                        mean_v = round(float(row["avg_v"]), 2) if row.get("avg_v") is not None else None
                        err_desc = f"Sensor value outside physical range [{min_lim}..{max_lim} {u}]"
                        sensors.append(
                            _make_sensor(
                                role=cand,
                                error_type=err_desc,
                                role_type="primary",
                                interval_avail=True,
                                s_start=st,
                                s_end=en,
                                s_hours=dur,
                                s_obs=mean_v,
                            )
                        )
                        faulted_roles.append(cand)
                except Exception:
                    pass

        # Fallback if no specific candidate query succeeded
        if not sensors:
            for cand in ["oa_t", "sat", "mat", "rat", "zone_t"]:
                if cand in available_roles:
                    min_lim, max_lim, u = SENSOR_RANGE_LIMITS.get(cand, (-50.0, 150.0, ""))
                    sensors.append(
                        _make_sensor(
                            role=cand,
                            error_type=f"Sensor evaluated for physical range violation [{min_lim}..{max_lim} {u}]",
                            role_type="primary",
                            interval_avail=True,
                            s_start=first_start,
                            s_end=last_end,
                            s_hours=tot_hours,
                        )
                    )
        return sensors

    elif clean_id in ("SV-FLATLINE", "SV-STALE"):
        faulted = telemetry_summary.get("faulted_sensors", [])
        is_flat = clean_id == "SV-FLATLINE"
        cond_text = "Sensor telemetry flatlined (zero variance over fixed window)" if is_flat else "Sensor telemetry unchanging / stale across consecutive intervals"
        
        target_roles = faulted if faulted else [r for r in ["mat", "sat", "oa_t", "rat", "zone_t"] if r in available_roles]
        for r in target_roles:
            sensors.append(
                _make_sensor(
                    role=r,
                    error_type=cond_text,
                    role_type="primary",
                    interval_avail=True,
                    s_start=first_start,
                    s_end=last_end,
                    s_hours=tot_hours,
                )
            )
        return sensors

    elif clean_id == "SV-SPIKE":
        for r in [r for r in ["sat", "oa_t", "mat", "duct_static", "zone_t"] if r in available_roles]:
            sensors.append(
                _make_sensor(
                    role=r,
                    error_type="Instantaneous delta spike exceeding physical rate of change limits",
                    role_type="primary",
                    interval_avail=True,
                    s_start=first_start,
                    s_end=last_end,
                    s_hours=tot_hours,
                )
            )
        return sensors

    elif clean_id == "SV-RATE":
        for r in [r for r in ["sat", "mat", "oa_t", "zone_t", "duct_static"] if r in available_roles]:
            sensors.append(
                _make_sensor(
                    role=r,
                    error_type="Sensor rate of change exceeds physical process limit",
                    role_type="primary",
                    interval_avail=True,
                    s_start=first_start,
                    s_end=last_end,
                    s_hours=tot_hours,
                )
            )
        return sensors

    elif clean_id == "PID-HUNT-1":
        for r in [r for r in ["sat", "duct_static", "clg_valve_pct"] if r in available_roles]:
            sensors.append(
                _make_sensor(
                    role=r,
                    error_type="Persistent sinusoidal hunting / oscillation around setpoint",
                    role_type="primary",
                    interval_avail=True,
                    s_start=first_start,
                    s_end=last_end,
                    s_hours=tot_hours,
                )
            )
        return sensors

    # -------------------------------------------------------------
    # 2. KNOWN PAIR RULES AND MULTI-SENSOR RULES WITH MAPPED EXPLANATIONS
    # -------------------------------------------------------------
    if clean_id in ROLE_CONDITION_EXPLANATIONS:
        rule_map = ROLE_CONDITION_EXPLANATIONS[clean_id]
        is_equipment_rule = clean_id.startswith("FC") or clean_id.startswith("ECON-") or clean_id in ("OA-1", "DMP-1", "VLV-1", "VAV-REHEAT")
        
        for role, (err_type, r_type) in rule_map.items():
            if role in available_roles or role in rule_def.required_roles:
                interval_avail = not is_equipment_rule
                note_str = "Individual sensor interval unavailable — equipment-level fault involving multiple interconnected sensors." if is_equipment_rule else None
                sensors.append(
                    _make_sensor(
                        role=role,
                        error_type=err_type,
                        role_type=r_type,
                        interval_avail=interval_avail,
                        s_start=first_start if interval_avail else None,
                        s_end=last_end if interval_avail else None,
                        s_hours=tot_hours if interval_avail else None,
                        notes=note_str,
                    )
                )
        return sensors

    # -------------------------------------------------------------
    # 3. DEDICATED SINGLE-SENSOR OR SIMPLE ROLES
    # -------------------------------------------------------------
    if len(rule_def.required_roles) == 1:
        req_role = rule_def.required_roles[0]
        desc = rule_def.description
        sensors.append(
            _make_sensor(
                role=req_role,
                error_type=desc,
                role_type="primary",
                interval_avail=True,
                s_start=first_start,
                s_end=last_end,
                s_hours=tot_hours,
            )
        )
        return sensors

    # -------------------------------------------------------------
    # 4. GENERAL FALLBACK FOR MULTI-SENSOR RULES
    # -------------------------------------------------------------
    for r in rule_def.required_roles:
        if r in available_roles or not available_roles:
            sensors.append(
                _make_sensor(
                    role=r,
                    error_type=f"Required telemetry component for rule {rule_id}: {rule_def.description}",
                    role_type="equipment_component",
                    interval_avail=False,
                    notes="Individual sensor interval unavailable — equipment-level fault evaluated across multiple sensors.",
                )
            )

    return sensors
