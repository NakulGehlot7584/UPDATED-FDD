"""
Candidate role inference engine for the FDD CSV role-mapping pipeline.

Source of Truth:
- Canonical role catalog in `backend.app.mapping.roles` (59 Open-FDD roles + co2, co2_sp)
- Generic semantic column naming patterns and vendor synonyms

Design Principles:
1. Candidate Generation Only: This module produces candidate roles matching semantic
   patterns in normalized column names. It does NOT make final winner decisions (which
   is the responsibility of `scorer.py`).
2. Semantic Isolation:
   - CO2 channels (co2, co2_sp) are strictly isolated from temperature channels (zone_t, sat, etc.).
   - Setpoint channels (sat_sp, duct_static_sp, co2_sp) are explicitly distinguished from measurements.
   - Outdoor air dampers (oa_damper_pct) are separated from generic VAV dampers (damper_pct).
   - Return fans (return_fan) are separated from supply fans (fan_cmd).
3. Generic & Source-Driven: No hardcoded assumptions or dataset-specific rules.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.mapping.normalizer import normalize_column_name


@dataclass(frozen=True)
class RoleCandidate:
    role: str
    reason: str
    matched_pattern: str


# ============================================================
# CANONICAL ROLE PATTERN CATALOG
# ============================================================

ROLE_PATTERNS: tuple[tuple[tuple[str, ...], str], ...] = (
    # --------------------------------------------------------
    # Project CO2 Extensions (Evaluated first to enforce isolation)
    # --------------------------------------------------------
    (
        (
            "co2_setpoint",
            "co2_sp",
            "co2_target",
            "co2_threshold",
            "co2_stpt",
            "zone_co2_setpoint",
            "room_co2_setpoint",
            "space_co2_setpoint",
            "carbon_dioxide_setpoint",
            "carbon_dioxide_sp",
            "carbon_dioxide_target",
            "carbon_dioxide_stpt",
        ),
        "co2_sp",
    ),
    (
        (
            "co2_ppm",
            "co2_sensor",
            "zone_co2",
            "room_co2",
            "space_co2",
            "outdoor_co2",
            "outside_co2",
            "return_co2",
            "ra_co2",
            "carbon_dioxide_ppm",
            "carbon_dioxide",
            "co2",
        ),
        "co2",
    ),
    # Space / Zone Relative Humidity
    (
        (
            "room_humidity",
            "zone_humidity",
            "space_humidity",
            "room_rh",
            "zone_rh",
            "space_rh",
            "indoor_humidity",
            "indoor_rh",
            "humidity_value",
            "humidity",
            "relative_humidity",
            "zone_h",
        ),
        "zone_h",
    ),
    # Cooling Valve Feedback / Position Monitoring
    (
        (
            "chw_valve_feedback",
            "chw_valve_position",
            "chw_valve_pos",
            "cooling_valve_feedback",
            "cooling_valve_position",
            "cooling_valve_pos",
            "clg_valve_feedback",
            "clg_valve_position",
            "clg_valve_pos",
            "valve_position_feedback",
            "valve_pos_feedback",
            "valve_position_actual",
            "valve_feedback",
            "valve_actual",
            "valve_position",
            "valve_pos",
            "chw_monitoring",
            "room_chw_monitoring",
            "cooling_monitoring",
            "clg_monitoring",
            "chw_feedback",
            "clg_feedback",
        ),
        "clg_valve_fbk",
    ),

    # --------------------------------------------------------
    # Supply / Discharge Air Temperature & Setpoint
    # --------------------------------------------------------
    (
        (
            "supply_air_temp_setpoint",
            "supply_air_temperature_setpoint",
            "room_supply_air_temp_setpoint",
            "discharge_air_temp_setpoint",
            "discharge_air_temperature_setpoint",
            "discharge_temp_setpoint",
            "discharge_temp_sp",
            "sat_setpoint",
            "sat_sp",
            "dat_sp",
            "dat_setpoint",
            "sa_tempspt",
            "sa_temp_sp",
            "sa_temp_setpoint",
            "dat_reset",
            "cooling_setpoint",
            "effective_setpoint",
            "clg_stpt",
            "discharge_air_temp_sp",
            "discharge_air_sp",
            "supply_air_setpoint",
            "discharge_air_setpoint",
            "supply_temp_setpoint",
            "supply_temperature_setpoint",
            "sat_sp_f",
            "sat_setpoint_f",
        ),
        "sat_sp",
    ),
    (
        (
            "supply_air_temp",
            "supply_air_temperature",
            "discharge_air_temp",
            "discharge_air_temperature",
            "discharge_temp",
            "discharge_temperature",
            "sat",
            "dat",
            "da_t",
            "sa_temp",
            "sa_t",
            "discharge_air",
            "supply_air",
        ),
        "sat",
    ),

    # --------------------------------------------------------
    # Return Air Temperature
    # --------------------------------------------------------
    (
        (
            "return_air_temp",
            "return_air_temperature",
            "return_temp",
            "return_temperature",
            "rat",
            "ra_t",
            "ra_temp",
            "return_air",
        ),
        "rat",
    ),

    # --------------------------------------------------------
    # Mixed Air Temperature
    # --------------------------------------------------------
    (
        (
            "mixed_air_temp",
            "mixed_air_temperature",
            "mat",
            "ma_t",
            "ma_temp",
            "mixed_air",
        ),
        "mat",
    ),

    # --------------------------------------------------------
    # Outdoor Air Temperature (BAS Local)
    # --------------------------------------------------------
    (
        (
            "outside_air_temp",
            "outside_air_temperature",
            "outdoor_air_temp",
            "outdoor_air_temperature",
            "oat",
            "oa_temp",
            "oa_t",
            "dry_bulb",
            "drybulb",
            "ambient_temp",
            "ambient_temperature",
            "ambient_air_temp",
            "ambient_air_temperature",
        ),
        "oa_t",
    ),

    # --------------------------------------------------------
    # Web Weather Service Telemetry
    # --------------------------------------------------------
    (
        (
            "web_oa_t",
            "web_oat",
            "wx_oa_t",
            "web_outside_air_temp",
        ),
        "web_oa_t",
    ),
    (
        (
            "web_oa_dp",
            "web_dew_point",
            "web_dewpoint",
            "dew_point",
            "dewpoint",
            "web_outside_air_dewpoint",
        ),
        "web_oa_dp",
    ),
    (
        (
            "web_wb_t",
            "web_wet_bulb",
            "web_wetbulb",
            "wet_bulb",
            "wetbulb",
            "web_outside_air_wetbulb",
        ),
        "web_wb_t",
    ),
    (
        (
            "web_oa_h",
            "web_humidity",
            "web_relative_humidity",
            "web_outside_air_humidity",
        ),
        "web_oa_h",
    ),

    # --------------------------------------------------------
    # Duct Static Pressure & Setpoint
    # --------------------------------------------------------
    (
        (
            "duct_static_pressure_setpoint",
            "duct_static_sp",
            "da_p_setpoint",
            "static_pressure_setpoint",
            "static_sp",
            "duct_sp",
            "dsp_sp",
            "dsp_setpoint",
            "da_p_sp",
        ),
        "duct_static_sp",
    ),
    (
        (
            "duct_static_pressure",
            "duct_static",
            "da_p_inwc",
            "da_p",
            "static_pressure",
            "supply_air_duct_static",
            "duct_pressure",
            "dsp",
        ),
        "duct_static",
    ),

    # --------------------------------------------------------
    # Fan Telemetry (Return Fan vs Supply Fan Cmd vs Status)
    # --------------------------------------------------------
    (
        (
            "return_fan_speed",
            "return_fan_cmd",
            "return_fan_command",
            "return_fan_speed_command",
            "return_fan_status",
            "return_fan_sts",
            "rf_speed",
            "rf_cmd",
            "rf_spd",
            "rf_spd_dm",
            "rf_speed_command",
            "return_fan",
            "rf_c",
        ),
        "return_fan",
    ),
    (
        (
            "supply_fan_run_status",
            "supply_fan_run_sts",
            "supply_fan_status",
            "supply_fan_sts",
            "supply_fan_stat",
            "supply_fan_proof",
            "supply_fan_run",
            "fan_run_status",
            "fan_run_sts",
            "fan_runsts",
            "fan_status",
            "fan_sts",
            "fan_stat",
            "fan_proof",
            "ahu_run_status",
            "ahu_run_sts",
            "ahu_status",
            "sf_run_sts",
            "sf_status",
            "sf_sts",
            "sf_proof",
            "sf_s",
        ),
        "fan_status",
    ),
    (
        (
            "supply_fan_speed",
            "fan_speed",
            "fan_spd",
            "fan_cmd",
            "fan_command",
            "fan_control",
            "supply_fan_control",
            "fan_on_command",
            "supply_fan_cmd",
            "supply_fan_command",
            "sf_c",
            "sf_spd",
            "sf_spd_dm",
            "sf_speed",
            "sf_speed_command",
            "supply_fan",
            "ec_fan_speed_command",
            "ec_fan_speed",
            "fan_speed_command",
            "fan_pct",
            "fan_percent",
            "ahu_on_command",
            "blower_speed",
            "blower_cmd",
        ),
        "fan_cmd",
    ),

    # --------------------------------------------------------
    # Damper Commands (OA Damper vs VAV Damper)
    # --------------------------------------------------------
    (
        (
            "outside_air_damper",
            "outdoor_air_damper",
            "fresh_air_damper_command",
            "fresh_air_damper",
            "oa_damper_pct",
            "oa_damper_cmd",
            "oa_damper",
            "oa_dmp_dm",
            "oa_dmp",
            "oad_pos",
            "mad_c",
            "ex_dmpr",
            "economizer_damper",
            "oa_dpr",
            "fresh_air_dpr",
            "mixed_air_damper",
        ),
        "oa_damper_pct",
    ),
    (
        (
            "vav_damper",
            "zone_damper",
            "damper_pct",
            "damper_pos",
            "damper_command",
            "damper_cmd",
            "vavactuator",
            "vav_actuator",
            "damper",
        ),
        "damper_pct",
    ),

    # --------------------------------------------------------
    # Valve Commands (Cooling, Heating, Reheat)
    # --------------------------------------------------------
    (
        (
            "cooling_valve_command",
            "cooling_valve_control",
            "cooling_valve_cmd",
            "cooling_valve_pct",
            "cooling_valve",
            "cooling_command_pct",
            "cooling_command",
            "cooling_cmd_pct",
            "cooling_cmd",
            "chwc_vlv_dm",
            "chwc_vlv",
            "valve_position_command",
            "valve_command",
            "valve_position_cmd",
            "valve_pos_cmd",
            "clg_valve_command",
            "clg_valve_control",
            "clg_valve_cmd",
            "clg_valve_pct",
            "clg_valve",
            "chw_valve_command",
            "chw_valve_control",
            "chw_valve_cmd",
            "chw_valve_pct",
            "chw_valve",
            "chw_control",
            "cooling_control",
            "clg_control",
            "room_chw_control",
            "cooling_coil_valve",
            "chilled_water_valve",
            "chw_monitoring",
            "cooling_monitoring",
            "clg_monitoring",
            "room_chw_monitoring",
            "chw_valve_feedback",
            "clg_valve_feedback",
        ),
        "clg_valve_pct",
    ),
    (
        (
            "heating_valve_command",
            "heating_valve_pct",
            "heating_valve",
            "htg_valve_pct",
            "htg_valve",
            "hw_valve_pct",
            "hw_valve",
            "heating_coil_valve",
            "hot_water_valve",
            "hhw_valve",
        ),
        "htg_valve_pct",
    ),
    (
        (
            "reheat_valve_command",
            "reheat_valve_pct",
            "reheat_valve",
            "rht_valve",
            "vav_reheat_valve",
        ),
        "reheat_valve_pct",
    ),

    # --------------------------------------------------------
    # Zone & Space Telemetry
    # --------------------------------------------------------
    (
        (
            "zone_temp",
            "zone_temperature",
            "space_temp",
            "space_temperature",
            "room_temp",
            "room_temperature",
            "zone_temp_sensor",
            "room_temp_sensor",
            "space_temp_sensor",
            "temp_sensor",
            "temperature_sensor",
            "temp_sens",
            "zone_t",
            "zn_t",
            "room_t",
            "space_t",
        ),
        "zone_t",
    ),
    (
        (
            "zone_airflow",
            "zone_flow",
            "actflow",
            "flow_input",
            "vav_airflow",
            "box_airflow",
            "actual_flow",
            "zone_air_flow",
            "airflow",
            "air_flow",
        ),
        "zone_flow",
    ),
    (
        (
            "vav_total_airflow",
            "vav_total_flow",
            "total_airflow",
            "ahu_total_airflow",
            "total_air_flow",
            "ahu_airflow",
        ),
        "vav_total_flow",
    ),
    (
        (
            "min_flow_sp",
            "minflowsp",
            "min_airflow",
            "min_airflow_setpoint",
            "min_flow_setpoint",
            "minimum_airflow_setpoint",
            "min_flow",
        ),
        "min_flow_sp",
    ),

    # --------------------------------------------------------
    # Chilled Water & Plant Telemetry
    # --------------------------------------------------------
    (
        (
            "chw_supply_temp_setpoint",
            "chw_supply_sp",
            "chws_sp",
            "chilled_water_supply_setpoint",
            "chws_setpoint",
        ),
        "chw_supply_sp",
    ),
    (
        (
            "chw_supply_temp",
            "chw_supply_temperature",
            "chw_supply",
            "chws_t",
            "chwst",
            "chilled_water_supply_temp",
            "chilled_water_supply",
            "chws_temp",
        ),
        "chw_supply_t",
    ),
    (
        (
            "chw_return_temp",
            "chw_return_temperature",
            "chw_return",
            "chwr_t",
            "chwrt",
            "chilled_water_return_temp",
            "chilled_water_return",
            "chwr_temp",
        ),
        "chw_return_t",
    ),
    (
        (
            "chw_dp_sp",
            "chw_diff_pressure_setpoint",
            "chw_differential_pressure_setpoint",
            "chw_delta_p_sp",
        ),
        "chw_dp_sp",
    ),
    (
        (
            "chw_dp",
            "chw_diff_pressure",
            "chw_differential_pressure",
            "chw_delta_p",
        ),
        "chw_dp",
    ),
    (
        (
            "chw_flow",
            "chilled_water_flow",
            "chw_gpm",
        ),
        "chw_flow",
    ),
    (
        (
            "chiller_status",
            "chiller_run_status",
            "chiller_proof",
            "chiller_state",
            "chiller_run",
        ),
        "chiller_status",
    ),
    (
        (
            "chiller_cmd",
            "chiller_command",
            "chiller_enable",
        ),
        "chiller_cmd",
    ),
    (
        (
            "chiller_power",
            "chiller_kw",
            "power_demand_this_interval",
            "meter_power_sum",
        ),
        "chiller_power",
    ),
    (
        (
            "chiller_amps",
            "chiller_amp",
            "chiller_current_amps",
            "amps_a",
        ),
        "chiller_amps",
    ),
    (
        (
            "chiller_current",
        ),
        "chiller_current",
    ),
    (
        (
            "chw_pump_cmd",
            "chw_pump_command",
            "chw_pump_speed",
            "primary_chw_pump_cmd",
            "cwp_cmd",
        ),
        "chw_pump_cmd",
    ),
    (
        (
            "chw_pump_status",
            "chw_pump_run_status",
            "chw_pump_proof",
            "primary_chw_pump_status",
            "cwp_status",
        ),
        "chw_pump_status",
    ),

    # --------------------------------------------------------
    # Hot Water & Boiler Telemetry
    # --------------------------------------------------------
    (
        (
            "hw_supply_temp",
            "hw_supply_temperature",
            "hw_supply",
            "hws_t",
            "hwst",
            "hot_water_supply_temp",
            "hot_water_supply",
            "hws_temp",
        ),
        "hw_supply_t",
    ),
    (
        (
            "hw_return_temp",
            "hw_return_temperature",
            "hw_return",
            "hwr_t",
            "hwrt",
            "hot_water_return_temp",
            "hot_water_return",
            "hwr_temp",
        ),
        "hw_return_t",
    ),

    # --------------------------------------------------------
    # Condenser Water & Cooling Tower Telemetry
    # --------------------------------------------------------
    (
        (
            "cw_supply_temp",
            "cw_supply_temperature",
            "cw_supply",
            "cws_t",
            "cwst",
            "condenser_water_supply_temp",
            "condenser_water_supply",
            "tower_leaving_temp",
        ),
        "cw_supply_t",
    ),
    (
        (
            "cw_return_temp",
            "cw_return_temperature",
            "cw_return",
            "cwr_t",
            "cwrt",
            "condenser_water_return_temp",
            "condenser_water_return",
            "tower_entering_temp",
        ),
        "cw_return_t",
    ),
    (
        (
            "cw_pump_cmd",
            "cw_pump_command",
            "cw_pump_speed",
            "tower_pump_cmd",
        ),
        "cw_pump_cmd",
    ),
    (
        (
            "tower_fan_cmd",
            "tower_fan_command",
            "tower_fan_speed",
            "cw_fan_cmd",
        ),
        "tower_fan_cmd",
    ),

    # --------------------------------------------------------
    # Extended AHU Coil & Reset Diagnostics
    # --------------------------------------------------------
    (
        (
            "preheat_leave_temp",
            "preheat_leave_t",
            "preheat_leaving_temp",
            "preheat_leaving_temperature",
        ),
        "preheat_leave_t",
    ),
    (
        (
            "cooling_coil_entering_temp",
            "cooling_coil_entering_temperature",
            "ccet",
            "clg_coil_entering_temp",
        ),
        "cooling_coil_entering_temp",
    ),
    (
        (
            "cooling_coil_leaving_temp",
            "cooling_coil_leaving_temperature",
            "cclt",
            "clg_coil_leaving_temp",
        ),
        "cooling_coil_leaving_temp",
    ),
    (
        (
            "heating_coil_entering_temp",
            "heating_coil_entering_temperature",
            "hcet",
            "htg_coil_entering_temp",
        ),
        "heating_coil_entering_temp",
    ),
    (
        (
            "heating_coil_leaving_temp",
            "heating_coil_leaving_temperature",
            "hclt",
            "htg_coil_leaving_temp",
        ),
        "heating_coil_leaving_temp",
    ),
    (
        (
            "static_reset_request",
            "vav_pressure_request_sum",
            "vav_pressure_requests",
            "static_requests",
        ),
        "static_reset_request",
    ),
    (
        (
            "loop_enabled",
            "pid_enable",
            "loop_enable",
        ),
        "loop_enabled",
    ),

    # --------------------------------------------------------
    # VAV Terminal Extended Telemetry
    # --------------------------------------------------------
    (
        (
            "vav_discharge_temp",
            "vav_discharge_t",
            "vav_discharge_air_temp",
            "vav_disch_temp",
        ),
        "vav_discharge_t",
    ),
    (
        (
            "vav_inlet_temp",
            "vav_inlet_t",
            "vav_inlet_air_temp",
        ),
        "vav_inlet_t",
    ),
    (
        (
            "ahu_sat",
            "ahu_supply_air_temp",
            "ahu_discharge_air_temp",
        ),
        "ahu_sat",
    ),
    (
        (
            "clg_available",
            "cooling_available",
        ),
        "clg_available",
    ),

    # --------------------------------------------------------
    # Generic Pump & Compressor Status
    # --------------------------------------------------------
    (
        (
            "pump_status",
            "pump_run_status",
            "pump_proof",
        ),
        "pump_status",
    ),
    (
        (
            "compressor_status",
            "compressor_run_status",
            "compressor_proof",
            "compressor_state",
        ),
        "compressor_status",
    ),

    # --------------------------------------------------------
    # Building Loads & Occupancy
    # --------------------------------------------------------
    (
        (
            "building_zone_load_satisfied",
            "zone_load_satisfied",
        ),
        "building_zone_load_satisfied",
    ),
    (
        (
            "building_ahu_load_satisfied",
            "ahu_load_satisfied",
        ),
        "building_ahu_load_satisfied",
    ),
    (
        (
            "occ_mode",
            "occupancy",
            "occupied",
            "schedule",
            "occ_status",
            "occupied_mode",
        ),
        "occ_mode",
    ),
    (
        (
            "oa_humidity",
            "outside_air_humidity",
            "outdoor_air_humidity",
            "outdoor_humidity",
            "oa_rh",
            "outdoor_air_rh",
            "outside_humidity",
            "ambient_humidity",
            "ambient_rh",
            "oa_h",
        ),
        "oa_h",
    ),

    # --------------------------------------------------------
    # Exhaust Fan & Face Velocity Project Extensions
    # --------------------------------------------------------
    (
        (
            "exhaust_fan_on_command",
            "exhaust_fan_command",
            "exhaust_fan_cmd",
            "exhaust_fan_speed",
            "exhaust_fan",
            "ef_speed",
            "ef_cmd",
            "ef_spd",
            "ef_spd_dm",
            "ef_c",
        ),
        "exhaust_fan_cmd",
    ),
    (
        (
            "exhaust_fan_run_status",
            "exhaust_fan_run_sts",
            "exhaust_fan_status",
            "exhaust_fan_sts",
            "exhaust_fan_proof",
            "exhaust_fan_run",
            "ef_run_sts",
            "ef_status",
            "ef_sts",
            "ef_proof",
            "ef_s",
        ),
        "exhaust_fan_status",
    ),
    (
        (
            "fresh_air_velocity_mps",
            "fresh_air_velocity",
            "oa_velocity",
            "outdoor_air_velocity",
            "face_velocity",
            "air_velocity",
        ),
        "oa_velocity",
    ),
)


def _contains_semantic_pattern(
    normalized_column: str,
    pattern: str,
) -> bool:
    """
    Check whether a semantic pattern occurs as a complete
    underscore-delimited token sequence.
    """
    if not pattern:
        return False

    expression = (
        rf"(?<![a-z0-9])"
        rf"{re.escape(pattern)}"
        rf"(?![a-z0-9])"
    )

    return re.search(expression, normalized_column) is not None


def infer_role_candidates(
    column_name: str,
) -> list[RoleCandidate]:
    """
    Generate possible canonical role candidates for a source column name.

    This function does not choose a final winning role. It evaluates semantic
    tokens and produces all plausible candidate roles matching the column.
    """
    normalized = normalize_column_name(column_name)
    candidates: list[RoleCandidate] = []
    seen_roles: set[str] = set()

    # Rule 1: CO2 Isolation Check
    # If the column represents a CO2 point, completely isolate it from temperature channels
    is_co2_column = any(
        _contains_semantic_pattern(normalized, p)
        for p in ("co2", "carbon_dioxide", "co2_ppm", "carbon_dioxide_ppm", "co2_sensor")
    )
    is_setpoint = any(
        _contains_semantic_pattern(normalized, p)
        for p in ("setpoint", "sp", "target", "threshold", "stpt", "setpt")
    )

    for patterns, role in ROLE_PATTERNS:
        if role in seen_roles:
            continue

        # Isolate CO2 from temperature and other non-CO2 roles
        if is_co2_column and role not in ("co2", "co2_sp"):
            continue
        if not is_co2_column and role in ("co2", "co2_sp"):
            continue

        # Prevent CO2 setpoint from producing measurement role 'co2'
        if role == "co2" and is_setpoint:
            continue

        # Prevent OA dampers from matching generic VAV damper role
        if role == "damper_pct" and any(
            _contains_semantic_pattern(normalized, p)
            for p in ("oa", "outside", "outdoor", "fresh", "mad_c", "ex_dmpr", "economizer")
        ):
            continue

        # Prevent Return Fan from matching generic Supply Fan command / status
        if role == "fan_cmd" and any(
            _contains_semantic_pattern(normalized, p) for p in ("return_fan", "rf_speed", "rf_cmd", "rf_spd", "rf_c")
        ):
            continue
        if role == "fan_status" and any(
            _contains_semantic_pattern(normalized, p) for p in ("return_fan", "rf_status", "rf_sts", "rf_run", "rf_proof", "rf_s")
        ):
            continue

        # Prevent Exhaust Fan from matching generic Supply Fan command / status
        if role in ("fan_cmd", "fan_status") and any(
            _contains_semantic_pattern(normalized, p) for p in ("exhaust_fan", "ex_fan", "ef_speed", "ef_cmd", "ef_sts", "ef_run", "ef_spd", "ef_s", "ef_c")
        ):
            continue

        for pattern in patterns:
            if _contains_semantic_pattern(normalized, pattern):
                candidates.append(
                    RoleCandidate(
                        role=role,
                        reason=f"Column name contains semantic pattern '{pattern}'.",
                        matched_pattern=pattern,
                    )
                )
                seen_roles.add(role)
                break

    return candidates
