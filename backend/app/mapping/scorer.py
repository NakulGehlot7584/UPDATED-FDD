"""
Candidate scoring engine for the FDD CSV role-mapping pipeline.

Source of Truth:
- Canonical role catalog in `backend.app.mapping.roles` (59 Open-FDD roles + co2, co2_sp)
- Semantic role weights, negative conflict penalties, and tie-breaking rules

Design Principles:
1. Evidence Scoring Only: `scorer.py` evaluates how strong the evidence is for each
   inferred candidate for a given column. It does NOT make global assignment decisions
   across columns (which is delegated to `resolver.py`).
2. Conflict Penalties:
   - Measurement candidates on explicit setpoint columns are strongly penalized (-100).
   - Fan command candidates on status/proof columns are strongly penalized (-100) and vice-versa.
   - Actuator feedback columns receive a confidence penalty (-40) relative to command signals.
   - Temperature candidates on CO2 columns are strongly penalized (-100).
   - Generic damper candidates on outdoor-air damper columns are strongly penalized (-100).
3. Single Strongest Match: Overlapping positive patterns are not double-counted; the
   single highest-weighted matching pattern provides positive evidence, followed by
   all applicable conflict penalties.
4. Deterministic Ordering: `score_candidates()` sorts candidates by score descending,
   using alphabetical role name as the secondary tie-breaker.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.mapping.inference import RoleCandidate
from app.mapping.normalizer import normalize_column_name


@dataclass(frozen=True)
class ScoredCandidate:
    """
    A role candidate evaluated with a semantic evidence score.
    """

    role: str
    score: int
    reason: str
    matched_pattern: str


# ============================================================
# POSITIVE EVIDENCE WEIGHTS
# ============================================================

ROLE_WEIGHTS: dict[str, dict[str, int]] = {
    # Supply Air Temperature & Setpoint
    "sat": {
        "supply_air_temp": 100,
        "supply_air_temperature": 100,
        "discharge_air_temp": 100,
        "discharge_air_temperature": 100,
        "discharge_temp": 100,
        "discharge_temperature": 100,
        "discharge_air": 90,
        "sat": 90,
        "dat": 90,
        "da_t": 85,
        "sa_temp": 95,
        "sa_t": 90,
        "supply_air": 80,
    },
    "sat_sp": {
        "supply_air_temp_setpoint": 100,
        "supply_air_temperature_setpoint": 100,
        "room_supply_air_temp_setpoint": 100,
        "discharge_air_temp_setpoint": 100,
        "discharge_air_temperature_setpoint": 100,
        "discharge_air_temp_sp": 100,
        "discharge_temp_setpoint": 100,
        "discharge_temp_sp": 100,
        "sat_setpoint": 100,
        "sat_sp": 95,
        "dat_sp": 95,
        "dat_setpoint": 100,
        "sa_tempspt": 95,
        "sa_temp_sp": 95,
        "sa_temp_setpoint": 100,
        "dat_reset": 95,
        "cooling_setpoint": 90,
        "effective_setpoint": 90,
        "discharge_air_sp": 90,
        "supply_air_setpoint": 90,
        "discharge_air_setpoint": 90,
        "supply_temp_setpoint": 90,
        "supply_temperature_setpoint": 90,
        "sat_sp_f": 90,
        "sat_setpoint_f": 90,
        "clg_stpt": 85,
    },

    # Return & Mixed Air Temperatures
    "rat": {
        "return_air_temp": 100,
        "return_air_temperature": 100,
        "return_temp": 100,
        "return_temperature": 100,
        "return_air": 90,
        "rat": 90,
        "ra_temp": 95,
        "ra_t": 85,
    },
    "mat": {
        "mixed_air_temp": 100,
        "mixed_air_temperature": 100,
        "mixed_air": 90,
        "mat": 90,
        "ma_temp": 95,
        "ma_t": 85,
    },

    # Outdoor Air Temperature (BAS Local)
    "oa_t": {
        "outside_air_temp": 100,
        "outside_air_temperature": 100,
        "outdoor_air_temp": 100,
        "outdoor_air_temperature": 100,
        "ambient_air_temp": 100,
        "ambient_air_temperature": 100,
        "dry_bulb": 95,
        "drybulb": 95,
        "ambient_temp": 95,
        "ambient_temperature": 95,
        "oat": 90,
        "oa_temp": 90,
        "oa_t": 90,
    },

    # Web Weather Service Telemetry
    "web_oa_t": {
        "web_outside_air_temp": 100,
        "web_oa_t": 100,
        "web_oat": 95,
        "wx_oa_t": 95,
    },
    "web_oa_dp": {
        "web_outside_air_dewpoint": 100,
        "web_dew_point": 100,
        "web_dewpoint": 100,
        "web_oa_dp": 95,
        "dew_point": 90,
        "dewpoint": 90,
    },
    "web_wb_t": {
        "web_outside_air_wetbulb": 100,
        "web_wet_bulb": 100,
        "web_wetbulb": 100,
        "web_wb_t": 95,
        "wet_bulb": 90,
        "wetbulb": 90,
    },
    "web_oa_h": {
        "web_outside_air_humidity": 100,
        "web_humidity": 100,
        "web_relative_humidity": 100,
        "web_oa_h": 95,
    },
    "oa_h": {
        "outside_air_humidity": 100,
        "outdoor_air_humidity": 100,
        "outdoor_humidity": 100,
        "oa_humidity": 95,
        "outside_humidity": 95,
        "oa_rh": 95,
        "outdoor_air_rh": 95,
        "ambient_humidity": 90,
        "ambient_rh": 90,
        "oa_h": 90,
    },

    # Duct Static Pressure & Setpoint
    "duct_static": {
        "duct_static_pressure": 100,
        "supply_air_duct_static": 100,
        "duct_static": 95,
        "duct_pressure": 90,
        "static_pressure": 85,
        "da_p_inwc": 90,
        "da_p": 80,
        "dsp": 80,
    },
    "duct_static_sp": {
        "duct_static_pressure_setpoint": 100,
        "static_pressure_setpoint": 100,
        "duct_static_sp": 95,
        "da_p_setpoint": 95,
        "da_p_sp": 95,
        "static_sp": 95,
        "duct_sp": 90,
        "duct_press_sp": 95,
        "duct_pressure_setpoint": 95,
        "dsp_sp": 90,
        "dsp_setpoint": 90,
    },

    # Fan Command, Status & Return Fan
    "fan_cmd": {
        "supply_fan_speed": 100,
        "supply_fan_command": 100,
        "supply_fan_control": 100,
        "sf_speed_command": 100,
        "sf_speed": 95,
        "ec_fan_speed_command": 100,
        "ec_fan_speed": 95,
        "fan_speed_command": 95,
        "fan_speed": 95,
        "supply_fan_cmd": 95,
        "fan_command": 95,
        "fan_control": 95,
        "sf_spd": 95,
        "sf_spd_dm": 95,
        "fan_cmd": 95,
        "fan_pct": 90,
        "fan_percent": 90,
        "supply_fan": 90,
        "sf_c": 90,
        "ahu_on_command": 90,
        "fan_on_command": 90,
        "blower_speed": 85,
        "blower_cmd": 85,
    },
    "fan_status": {
        "supply_fan_run_status": 100,
        "supply_fan_run_sts": 100,
        "supply_fan_status": 100,
        "fan_run_status": 100,
        "fan_run_sts": 100,
        "supply_fan_stat": 95,
        "supply_fan_sts": 95,
        "supply_fan_proof": 95,
        "supply_fan_run": 95,
        "fan_runsts": 95,
        "fan_status": 95,
        "fan_sts": 95,
        "fan_proof": 95,
        "ahu_run_status": 95,
        "ahu_run_sts": 95,
        "ahu_status": 90,
        "fan_stat": 90,
        "sf_run_sts": 95,
        "sf_status": 90,
        "sf_sts": 90,
        "sf_proof": 90,
        "sf_s": 90,
    },
    "return_fan": {
        "return_fan_speed": 100,
        "return_fan_cmd": 100,
        "return_fan_command": 100,
        "return_fan_speed_command": 100,
        "return_fan": 95,
        "rf_speed": 95,
        "rf_spd": 95,
        "rf_spd_dm": 95,
        "rf_speed_command": 100,
        "rf_c": 90,
    },

    # Damper Commands
    "oa_damper_pct": {
        "outside_air_damper": 100,
        "outdoor_air_damper": 100,
        "fresh_air_damper_command": 100,
        "fresh_air_damper": 95,
        "oa_damper_pct": 95,
        "oa_damper_cmd": 95,
        "oa_damper": 95,
        "oa_dmp_dm": 95,
        "oa_dmp": 90,
        "oad_pos": 90,
        "economizer_damper": 95,
        "mad_c": 90,
        "ex_dmpr": 90,
        "mixed_air_damper": 90,
        "oa_dpr": 85,
        "fresh_air_dpr": 85,
    },
    "damper_pct": {
        "vav_damper": 100,
        "zone_damper": 100,
        "damper_pct": 95,
        "damper_pos": 95,
        "damper_command": 95,
        "damper_cmd": 95,
        "vavactuator": 90,
        "vav_actuator": 90,
        "damper": 80,
    },

    # Valve Commands
    "clg_valve_pct": {
        "cooling_valve_command": 100,
        "cooling_valve_control": 100,
        "cooling_valve_pct": 100,
        "cooling_command_pct": 95,
        "cooling_command": 95,
        "cooling_cmd_pct": 95,
        "chwc_vlv_dm": 95,
        "valve_position_command": 95,
        "valve_command": 95,
        "valve_position_cmd": 95,
        "valve_pos_cmd": 90,
        "clg_valve_command": 100,
        "clg_valve_control": 100,
        "chw_valve_command": 100,
        "chw_valve_control": 100,
        "chw_valve_pct": 100,
        "chw_control": 95,
        "cooling_control": 95,
        "clg_control": 95,
        "cooling_cmd": 90,
        "chwc_vlv": 90,
        "room_chw_control": 95,
        "cooling_valve": 95,
        "clg_valve_pct": 95,
        "clg_valve": 95,
        "chw_valve": 95,
        "cooling_coil_valve": 90,
        "chilled_water_valve": 90,
        "chw_monitoring": 60,
        "cooling_monitoring": 60,
        "clg_monitoring": 60,
        "room_chw_monitoring": 60,
        "chw_valve_feedback": 60,
        "clg_valve_feedback": 60,
    },
    "htg_valve_pct": {
        "heating_valve_command": 100,
        "heating_valve_pct": 100,
        "hw_valve_pct": 100,
        "heating_valve": 95,
        "htg_valve_pct": 95,
        "htg_valve": 95,
        "hw_valve": 95,
        "heating_coil_valve": 90,
        "hot_water_valve": 90,
        "hhw_valve": 90,
    },
    "reheat_valve_pct": {
        "reheat_valve_command": 100,
        "reheat_valve_pct": 100,
        "reheat_valve": 95,
        "rht_valve": 90,
        "vav_reheat_valve": 90,
    },

    # Zone / Space & Airflow
    "zone_t": {
        "zone_temp": 100,
        "zone_temperature": 100,
        "space_temp": 95,
        "space_temperature": 95,
        "room_temp": 90,
        "room_temperature": 90,
        "zone_temp_sensor": 95,
        "room_temp_sensor": 95,
        "space_temp_sensor": 95,
        "temp_sensor": 85,
        "temperature_sensor": 85,
        "temp_sens": 80,
        "zone_t": 90,
        "zn_t": 85,
        "room_t": 85,
        "space_t": 85,
    },
    "zone_flow": {
        "zone_airflow": 100,
        "zone_flow": 95,
        "actflow": 95,
        "flow_input": 90,
        "vav_airflow": 90,
        "box_airflow": 90,
        "actual_flow": 90,
        "zone_air_flow": 90,
        "airflow": 80,
        "air_flow": 80,
    },
    "vav_total_flow": {
        "vav_total_airflow": 100,
        "vav_total_flow": 100,
        "total_airflow": 95,
        "ahu_total_airflow": 95,
        "total_air_flow": 90,
        "ahu_airflow": 85,
    },
    "min_flow_sp": {
        "min_flow_sp": 100,
        "minflowsp": 95,
        "min_airflow_setpoint": 95,
        "min_flow_setpoint": 95,
        "minimum_airflow_setpoint": 95,
        "min_airflow": 90,
        "min_flow": 85,
    },

    # Chilled Water & Chiller
    "chw_supply_t": {
        "chw_supply_temp": 100,
        "chw_supply_temperature": 100,
        "chilled_water_supply_temp": 100,
        "chw_supply": 95,
        "chws_t": 95,
        "chwst": 95,
        "chilled_water_supply": 90,
        "chws_temp": 90,
    },
    "chw_return_t": {
        "chw_return_temp": 100,
        "chw_return_temperature": 100,
        "chilled_water_return_temp": 100,
        "chw_return": 95,
        "chwr_t": 95,
        "chwrt": 95,
        "chilled_water_return": 90,
        "chwr_temp": 90,
    },
    "chw_supply_sp": {
        "chw_supply_temp_setpoint": 100,
        "chilled_water_supply_setpoint": 100,
        "chw_supply_sp": 95,
        "chws_sp": 95,
        "chws_setpoint": 90,
    },
    "chw_dp": {
        "chw_differential_pressure": 100,
        "chw_diff_pressure": 95,
        "chw_dp": 95,
        "chw_delta_p": 90,
    },
    "chw_dp_sp": {
        "chw_differential_pressure_setpoint": 100,
        "chw_diff_pressure_setpoint": 95,
        "chw_dp_sp": 95,
        "chw_delta_p_sp": 90,
    },
    "chw_flow": {
        "chilled_water_flow": 100,
        "chw_flow": 95,
        "chw_gpm": 90,
    },
    "chiller_status": {
        "chiller_run_status": 100,
        "chiller_status": 95,
        "chiller_proof": 95,
        "chiller_state": 90,
        "chiller_run": 85,
    },
    "chiller_cmd": {
        "chiller_command": 100,
        "chiller_cmd": 95,
        "chiller_enable": 90,
    },
    "chiller_power": {
        "power_demand_this_interval": 100,
        "chiller_power": 95,
        "chiller_kw": 95,
        "meter_power_sum": 90,
    },
    "chiller_amps": {
        "chiller_current_amps": 100,
        "chiller_amps": 95,
        "chiller_amp": 90,
        "amps_a": 90,
    },
    "chiller_current": {
        "chiller_current": 95,
    },
    "chw_pump_cmd": {
        "primary_chw_pump_cmd": 100,
        "chw_pump_command": 100,
        "chw_pump_cmd": 95,
        "chw_pump_speed": 90,
        "cwp_cmd": 85,
    },
    "chw_pump_status": {
        "primary_chw_pump_status": 100,
        "chw_pump_run_status": 100,
        "chw_pump_status": 95,
        "chw_pump_proof": 95,
        "cwp_status": 85,
    },

    # Hot Water & Boiler
    "hw_supply_t": {
        "hw_supply_temp": 100,
        "hw_supply_temperature": 100,
        "hot_water_supply_temp": 100,
        "hw_supply": 95,
        "hws_t": 95,
        "hwst": 95,
        "hot_water_supply": 90,
        "hws_temp": 90,
    },
    "hw_return_t": {
        "hw_return_temp": 100,
        "hw_return_temperature": 100,
        "hot_water_return_temp": 100,
        "hw_return": 95,
        "hwr_t": 95,
        "hwrt": 95,
        "hot_water_return": 90,
        "hwr_temp": 90,
    },

    # Condenser Water & Cooling Tower
    "cw_supply_t": {
        "cw_supply_temp": 100,
        "cw_supply_temperature": 100,
        "condenser_water_supply_temp": 100,
        "cw_supply": 95,
        "cws_t": 95,
        "cwst": 95,
        "condenser_water_supply": 90,
        "tower_leaving_temp": 90,
    },
    "cw_return_t": {
        "cw_return_temp": 100,
        "cw_return_temperature": 100,
        "condenser_water_return_temp": 100,
        "cw_return": 95,
        "cwr_t": 95,
        "cwrt": 95,
        "condenser_water_return": 90,
        "tower_entering_temp": 90,
    },
    "cw_pump_cmd": {
        "tower_pump_cmd": 100,
        "cw_pump_command": 100,
        "cw_pump_cmd": 95,
        "cw_pump_speed": 90,
    },
    "tower_fan_cmd": {
        "tower_fan_command": 100,
        "tower_fan_speed": 100,
        "tower_fan_cmd": 95,
        "cw_fan_cmd": 90,
    },

    # Project Extensions (CO2, Zone Humidity, Valve Feedback)
    "zone_h": {
        "room_humidity": 100,
        "zone_humidity": 100,
        "space_humidity": 100,
        "room_rh": 100,
        "zone_rh": 100,
        "space_rh": 100,
        "indoor_humidity": 100,
        "indoor_rh": 100,
        "humidity_value": 95,
        "humidity": 90,
        "relative_humidity": 90,
        "zone_h": 95,
    },
    "clg_valve_fbk": {
        "chw_valve_feedback": 100,
        "chw_valve_position": 100,
        "cooling_valve_feedback": 100,
        "cooling_valve_position": 100,
        "clg_valve_feedback": 100,
        "clg_valve_position": 100,
        "valve_position_feedback": 100,
        "valve_position_actual": 100,
        "valve_pos_feedback": 95,
        "valve_feedback": 95,
        "valve_actual": 95,
        "valve_position": 90,
        "valve_pos": 90,
        "chw_monitoring": 95,
        "room_chw_monitoring": 95,
        "cooling_monitoring": 95,
        "clg_monitoring": 95,
        "chw_valve_pos": 90,
        "cooling_valve_pos": 90,
        "clg_valve_pos": 90,
        "chw_feedback": 90,
        "clg_feedback": 90,
    },
    "co2": {
        "zone_co2": 100,
        "room_co2": 100,
        "space_co2": 100,
        "co2_ppm": 100,
        "carbon_dioxide_ppm": 100,
        "co2_sensor": 95,
        "co2": 95,
        "carbon_dioxide": 90,
        "outside_co2": 85,
        "outdoor_co2": 85,
        "return_co2": 85,
        "ra_co2": 85,
    },
    "co2_sp": {
        "zone_co2_setpoint": 100,
        "room_co2_setpoint": 100,
        "space_co2_setpoint": 100,
        "co2_setpoint_ppm": 100,
        "carbon_dioxide_setpoint": 100,
        "co2_setpoint": 100,
        "co2_sp": 95,
        "co2_target": 95,
        "co2_threshold": 90,
        "co2_stpt": 90,
        "carbon_dioxide_sp": 90,
        "carbon_dioxide_target": 90,
        "carbon_dioxide_stpt": 90,
    },

    # Extended Roles
    "occ_mode": {
        "occupied_mode": 100,
        "occ_mode": 95,
        "occupancy": 95,
        "occupied": 95,
        "schedule": 90,
        "occ_status": 90,
    },
    "ahu_sat": {
        "ahu_discharge_air_temp": 95,
        "ahu_supply_air_temp": 95,
        "ahu_sat": 95,
    },
    "clg_available": {
        "cooling_available": 100,
        "clg_available": 95,
    },
    "compressor_status": {
        "compressor_run_status": 100,
        "compressor_proof": 100,
        "compressor_status": 95,
        "compressor_state": 90,
    },
    "cooling_coil_entering_temp": {
        "cooling_coil_entering_temp": 100,
        "cooling_coil_entering_temperature": 100,
        "ccet": 95,
        "clg_coil_entering_temp": 90,
    },
    "cooling_coil_leaving_temp": {
        "cooling_coil_leaving_temp": 100,
        "cooling_coil_leaving_temperature": 100,
        "cclt": 95,
        "clg_coil_leaving_temp": 90,
    },
    "heating_coil_entering_temp": {
        "heating_coil_entering_temp": 100,
        "heating_coil_entering_temperature": 100,
        "hcet": 95,
        "htg_coil_entering_temp": 90,
    },
    "heating_coil_leaving_temp": {
        "heating_coil_leaving_temp": 100,
        "heating_coil_leaving_temperature": 100,
        "hclt": 95,
        "htg_coil_leaving_temp": 90,
    },
    "loop_enabled": {
        "loop_enabled": 100,
        "pid_enable": 95,
        "loop_enable": 90,
    },
    "preheat_leave_t": {
        "preheat_leaving_temperature": 100,
        "preheat_leaving_temp": 100,
        "preheat_leave_temp": 95,
        "preheat_leave_t": 95,
    },
    "static_reset_request": {
        "vav_pressure_request_sum": 100,
        "vav_pressure_requests": 95,
        "static_reset_request": 95,
        "static_requests": 90,
    },
    "vav_discharge_t": {
        "vav_discharge_air_temp": 100,
        "vav_discharge_temperature": 100,
        "vav_discharge_temp": 95,
        "vav_discharge_t": 95,
        "vav_disch_temp": 90,
    },
    "vav_inlet_t": {
        "vav_inlet_air_temp": 100,
        "vav_inlet_temperature": 100,
        "vav_inlet_temp": 95,
        "vav_inlet_t": 95,
    },
    "pump_status": {
        "pump_run_status": 100,
        "pump_proof": 95,
        "pump_status": 95,
    },
    "building_zone_load_satisfied": {
        "building_zone_load_satisfied": 100,
        "zone_load_satisfied": 95,
    },
    "building_ahu_load_satisfied": {
        "building_ahu_load_satisfied": 100,
        "ahu_load_satisfied": 95,
    },
    "exhaust_fan_cmd": {
        "exhaust_fan_on_command": 100,
        "exhaust_fan_command": 100,
        "exhaust_fan_cmd": 95,
        "exhaust_fan_speed": 95,
        "ef_speed": 95,
        "ef_cmd": 95,
        "ef_spd": 95,
        "ef_spd_dm": 95,
        "exhaust_fan": 90,
        "ef_c": 90,
    },
    "exhaust_fan_status": {
        "exhaust_fan_run_status": 100,
        "exhaust_fan_run_sts": 100,
        "exhaust_fan_status": 100,
        "exhaust_fan_sts": 95,
        "exhaust_fan_proof": 95,
        "exhaust_fan_run": 95,
        "ef_run_sts": 95,
        "ef_status": 90,
        "ef_sts": 90,
        "ef_proof": 90,
        "ef_s": 90,
    },
    "oa_velocity": {
        "fresh_air_velocity_mps": 100,
        "fresh_air_velocity": 95,
        "oa_velocity": 95,
        "outdoor_air_velocity": 95,
        "face_velocity": 90,
        "air_velocity": 85,
    },
}


# ============================================================
# NEGATIVE CONFLICT PENALTIES
# ============================================================

NEGATIVE_PATTERNS: dict[str, tuple[tuple[str, int], ...]] = {
    # Measurement roles penalize setpoints, limits, and alarms
    "sat": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("target", -100),
        ("limit", -100),
        ("alarm", -100),
        ("co2", -100),
        ("carbon_dioxide", -100),
    ),
    "rat": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("limit", -100),
        ("alarm", -100),
        ("co2", -100),
    ),
    "mat": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("limit", -100),
        ("alarm", -100),
        ("damper", -100),
        ("mad_c", -100),
    ),
    "oa_t": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("target", -100),
        ("limit", -100),
        ("alarm", -100),
        ("web_", -40),
        ("wx_", -40),
        ("co2", -100),
    ),
    "duct_static": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("target", -100),
        ("alarm", -100),
        ("limit", -100),
    ),
    "zone_t": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("target", -100),
        ("deadband", -100),
        ("alarm", -100),
        ("limit", -100),
        ("highlimit", -100),
        ("lowlimit", -100),
        ("co2", -100),
        ("carbon_dioxide", -100),
        ("humidity", -100),
        ("rh", -100),
        ("flow", -100),
        ("airflow", -100),
        ("supply", -100),
        ("discharge", -100),
        ("return", -100),
        ("mixed", -100),
        ("outdoor", -100),
        ("outside", -100),
        ("water", -100),
        ("chw", -100),
        ("hw", -100),
        ("cw", -100),
    ),
    "zone_flow": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("target", -100),
        ("minflow", -100),
        ("maxflow", -100),
        ("min_flow", -100),
        ("max_flow", -100),
        ("total", -100),
    ),
    "chw_supply_t": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("return", -100),
    ),
    "chw_return_t": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("supply", -100),
    ),
    "hw_supply_t": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("return", -100),
    ),
    "hw_return_t": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("supply", -100),
    ),
    "cw_supply_t": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("return", -100),
    ),
    "cw_return_t": (
        ("setpoint", -100),
        ("set_point", -100),
        ("sp", -100),
        ("stpt", -100),
        ("supply", -100),
    ),

    # Command vs Status
    "fan_cmd": (
        ("status", -100),
        ("sts", -100),
        ("run_status", -100),
        ("run_sts", -100),
        ("proof", -100),
        ("state", -100),
        ("return_fan", -100),
        ("rf_", -100),
        ("exhaust_fan", -100),
        ("ex_fan", -100),
        ("ef_", -100),
    ),
    "fan_status": (
        ("command", -100),
        ("cmd", -100),
        ("speed", -80),
        ("control", -80),
        ("return_fan", -100),
        ("rf_", -100),
        ("exhaust_fan", -100),
        ("ex_fan", -100),
        ("ef_", -100),
    ),
    "exhaust_fan_cmd": (
        ("status", -100),
        ("sts", -100),
        ("run_status", -100),
        ("run_sts", -100),
        ("proof", -100),
        ("state", -100),
        ("supply_fan", -100),
        ("sf_", -100),
        ("return_fan", -100),
        ("rf_", -100),
    ),
    "exhaust_fan_status": (
        ("command", -100),
        ("cmd", -100),
        ("speed", -80),
        ("control", -80),
        ("supply_fan", -100),
        ("sf_", -100),
        ("return_fan", -100),
        ("rf_", -100),
    ),
    "oa_velocity": (
        ("temp", -100),
        ("pressure", -100),
        ("sp", -100),
        ("setpoint", -100),
    ),
    "chw_pump_cmd": (
        ("status", -100),
        ("run_status", -100),
        ("proof", -100),
    ),
    "chw_pump_status": (
        ("command", -100),
        ("cmd", -100),
        ("speed", -80),
    ),
    "chiller_cmd": (
        ("status", -100),
        ("run_status", -100),
        ("proof", -100),
    ),
    "chiller_status": (
        ("command", -100),
        ("cmd", -100),
        ("override", -100),
        ("tstat", -100),
    ),
    "chiller_power": (
        ("peak", -100),
        ("kva", -100),
        ("va_demand", -100),
    ),
    "cw_pump_cmd": (
        ("status", -100),
        ("run_status", -100),
        ("proof", -100),
    ),
    "tower_fan_cmd": (
        ("status", -100),
        ("run_status", -100),
        ("proof", -100),
    ),

    # Valve Commands
    "clg_valve_pct": (
        ("feedback", -40),
        ("fbk", -40),
        ("actual", -40),
        ("status", -80),
        ("heating", -100),
        ("hw_", -100),
        ("reheat", -100),
    ),
    "htg_valve_pct": (
        ("feedback", -40),
        ("fbk", -40),
        ("actual", -40),
        ("status", -80),
        ("cooling", -100),
        ("chw_", -100),
    ),
    "reheat_valve_pct": (
        ("feedback", -40),
        ("fbk", -40),
        ("cooling", -100),
        ("chw_", -100),
    ),

    # Damper Isolation
    "damper_pct": (
        ("oa_damper", -100),
        ("outside_air", -100),
        ("outdoor_air", -100),
        ("fresh_air", -100),
        ("mad_c", -100),
        ("ex_dmpr", -100),
        ("economizer", -100),
        ("oa_", -100),
        ("heating_damper", -100),
    ),
    "oa_damper_pct": (
        ("enable", -100),
        ("minimum", -100),
        ("min_pos", -100),
        ("minpos", -100),
        ("temperature", -100),
        ("temp", -100),
    ),

    # CO2 Isolation
    "co2": (
        ("setpoint", -100),
        ("set_point", -100),
        ("_sp", -100),
        ("stpt", -100),
        ("target", -100),
        ("threshold", -100),
        ("limit", -100),
        ("alarm", -100),
    ),
    "co2_sp": (
        ("temp", -100),
        ("temperature", -100),
        ("pressure", -100),
        ("static", -100),
    ),
    "zone_h": (
        ("outdoor", -100),
        ("outside", -100),
        ("oa_", -100),
        ("oat", -100),
        ("web_", -100),
        ("wx_", -100),
        ("weather", -100),
        ("temp", -100),
        ("co2", -100),
    ),
    "clg_valve_fbk": (
        ("command", -100),
        ("cmd", -100),
        ("control", -60),
        ("output", -60),
        ("heating", -100),
        ("htg", -100),
        ("hw", -100),
        ("temp", -100),
    ),
}


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


def score_candidate(
    column_name: str,
    candidate: RoleCandidate,
) -> ScoredCandidate:
    """
    Score one inferred role candidate for a source column.

    Positive evidence selects the single strongest matching pattern to avoid
    over-counting overlapping tokens. Negative conflict penalties are then applied.
    """
    normalized = normalize_column_name(column_name)
    score = 0
    reasons: list[str] = []

    weights = ROLE_WEIGHTS.get(candidate.role, {})

    # Positive evidence: check explicit weights first
    matching_weights = [
        (pattern, weight)
        for pattern, weight in weights.items()
        if _contains_semantic_pattern(normalized, pattern)
    ]

    if matching_weights:
        # Prefer highest weight, with longest matching pattern as tie-breaker
        best_match = max(
            matching_weights,
            key=lambda item: (item[1], len(item[0])),
        )
        pattern, weight = best_match
        score += weight
        reasons.append(f"'{pattern}' matched ({weight:+d}).")
    elif candidate.matched_pattern:
        score += 90
        reasons.append(f"'{candidate.matched_pattern}' matched (+90).")

    # Negative evidence: check penalties
    for pattern, penalty in NEGATIVE_PATTERNS.get(candidate.role, ()):
        if _contains_semantic_pattern(normalized, pattern):
            score += penalty
            reasons.append(f"'{pattern}' conflict ({penalty:+d}).")

    if not reasons:
        reasons.append("No additional scoring evidence.")

    return ScoredCandidate(
        role=candidate.role,
        score=score,
        reason=" ".join(reasons),
        matched_pattern=candidate.matched_pattern,
    )


def score_candidates(
    column_name: str,
    candidates: list[RoleCandidate],
) -> list[ScoredCandidate]:
    """
    Score all candidates for a column.

    Results are ordered deterministically:
    1. Descending score (highest evidence first)
    2. Alphabetical role name as secondary tie-breaker
    """
    scored = [
        score_candidate(column_name, candidate)
        for candidate in candidates
    ]

    scored.sort(
        key=lambda c: (-c.score, c.role),
    )

    return scored


def pick_best_candidate(
    column_name: str,
    candidates: list[RoleCandidate],
) -> ScoredCandidate | None:
    """
    Select the highest-scoring candidate for a column.

    Returns None if:
    - candidates list is empty
    - the highest score is non-positive (<= 0)
    """
    scored = score_candidates(column_name, candidates)

    if not scored:
        return None

    best = scored[0]

    if best.score <= 0:
        return None

    return best
