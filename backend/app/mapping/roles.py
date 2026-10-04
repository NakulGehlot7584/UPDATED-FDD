"""
Canonical role catalog for the FDD CSV role-mapping engine.

Source of Truth:
- Open-FDD canonical role vocabulary (59 roles from fdd_core, edge, and sql_rules)
- Project-specific CO2 extensions (co2, co2_sp)

Important:
This module defines WHAT a role represents (metadata, kind, physical units, equipment).
It does not contain:
- column-name inference or regex
- aliases or vendor synonyms
- scoring or ranking heuristics
- FDD diagnostic thresholds or rule evaluation logic
"""

from __future__ import annotations


# ============================================================
# OPEN-FDD CANONICAL ROLES (59 ROLES)
# ============================================================

OPEN_FDD_CANONICAL_ROLES: tuple[str, ...] = (
    # Core Cookbook Roles (crates/fdd_core/src/columns.rs:214-251)
    "fan_cmd",
    "fan_status",
    "sat",
    "sat_sp",
    "oa_t",
    "rat",
    "mat",
    "web_oa_t",
    "web_oa_dp",
    "duct_static",
    "duct_static_sp",
    "oa_damper_pct",
    "damper_pct",
    "clg_valve_pct",
    "htg_valve_pct",
    "reheat_valve_pct",
    "zone_t",
    "zone_flow",
    "vav_total_flow",
    "min_flow_sp",
    "chiller_status",
    "chw_pump_status",
    "chw_pump_cmd",
    "building_zone_load_satisfied",
    "building_ahu_load_satisfied",
    "chw_supply_t",
    "chw_return_t",
    "chiller_power",
    "chiller_amps",
    "chiller_current",
    "pump_status",
    "hw_supply_t",
    "hw_return_t",
    "oa_h",
    "occ_mode",
    "return_fan",

    # Extended Canonical Rule & Package Ingest Roles
    "ahu_sat",
    "chiller_cmd",
    "chw_dp",
    "chw_dp_sp",
    "chw_flow",
    "chw_supply_sp",
    "clg_available",
    "compressor_status",
    "cooling_coil_entering_temp",
    "cooling_coil_leaving_temp",
    "cw_pump_cmd",
    "cw_return_t",
    "cw_supply_t",
    "heating_coil_entering_temp",
    "heating_coil_leaving_temp",
    "loop_enabled",
    "preheat_leave_t",
    "static_reset_request",
    "tower_fan_cmd",
    "vav_discharge_t",
    "vav_inlet_t",
    "web_oa_h",
    "web_wb_t",
)


# ============================================================
# PROJECT EXTENSIONS (2 ROLES)
# ============================================================

PROJECT_EXTENSION_ROLES: tuple[str, ...] = (
    "co2",
    "co2_sp",
    "zone_h",
    "clg_valve_fbk",
    "exhaust_fan_cmd",
    "exhaust_fan_status",
    "oa_velocity",
)


# ============================================================
# COMPLETE CANONICAL ROLE CATALOG (61 ROLES)
# ============================================================

CANONICAL_ROLES: dict[str, dict[str, object]] = {
    # --------------------------------------------------------
    # Air Handling & Ventilation
    # --------------------------------------------------------

    "fan_cmd": {
        "description": "Supply fan command or speed command.",
        "kind": "command",
        "equipment": ("AHU",),
    },

    "fan_status": {
        "description": "Supply fan run/status/proof signal.",
        "kind": "status",
        "equipment": ("AHU",),
    },

    "return_fan": {
        "description": "Return fan command or operating signal.",
        "kind": "command",
        "equipment": ("AHU",),
    },

    "sat": {
        "description": "Supply/discharge air temperature.",
        "kind": "sensor",
        "equipment": ("AHU",),
    },

    "sat_sp": {
        "description": "Supply/discharge air temperature setpoint.",
        "kind": "setpoint",
        "equipment": ("AHU",),
    },

    "oa_t": {
        "description": "Outdoor air temperature.",
        "kind": "sensor",
        "equipment": ("AHU", "WEATHER"),
    },

    "rat": {
        "description": "Return air temperature.",
        "kind": "sensor",
        "equipment": ("AHU",),
    },

    "mat": {
        "description": "Mixed air temperature.",
        "kind": "sensor",
        "equipment": ("AHU",),
    },

    "duct_static": {
        "description": "Duct static pressure.",
        "kind": "sensor",
        "equipment": ("AHU", "VAV"),
    },

    "duct_static_sp": {
        "description": "Duct static pressure setpoint.",
        "kind": "setpoint",
        "equipment": ("AHU",),
    },

    "oa_damper_pct": {
        "description": "Outdoor-air damper position or command.",
        "kind": "command",
        "equipment": ("AHU",),
    },

    "damper_pct": {
        "description": "VAV/zone damper position or command.",
        "kind": "command",
        "equipment": ("VAV",),
    },

    "clg_valve_pct": {
        "description": "Cooling coil valve command or position.",
        "kind": "command",
        "equipment": ("AHU",),
    },

    "htg_valve_pct": {
        "description": "Heating coil valve command or position.",
        "kind": "command",
        "equipment": ("AHU",),
    },

    "reheat_valve_pct": {
        "description": "VAV reheat valve command or position.",
        "kind": "command",
        "equipment": ("VAV",),
    },

    "vav_total_flow": {
        "description": "Total AHU / VAV supply airflow.",
        "kind": "sensor",
        "equipment": ("AHU", "VAV"),
    },

    "preheat_leave_t": {
        "description": "Preheat coil leaving air temperature.",
        "kind": "sensor",
        "equipment": ("AHU",),
    },

    "cooling_coil_entering_temp": {
        "description": "Cooling coil entering air temperature.",
        "kind": "sensor",
        "equipment": ("AHU",),
    },

    "cooling_coil_leaving_temp": {
        "description": "Cooling coil leaving air temperature.",
        "kind": "sensor",
        "equipment": ("AHU",),
    },

    "heating_coil_entering_temp": {
        "description": "Heating coil entering air temperature.",
        "kind": "sensor",
        "equipment": ("AHU",),
    },

    "heating_coil_leaving_temp": {
        "description": "Heating coil leaving air temperature.",
        "kind": "sensor",
        "equipment": ("AHU",),
    },

    "static_reset_request": {
        "description": "Duct static pressure trim-and-respond request count/sum.",
        "kind": "sensor",
        "equipment": ("AHU",),
    },

    "loop_enabled": {
        "description": "Control loop active / hunting evaluation enable flag.",
        "kind": "status",
        "equipment": ("AHU", "VAV"),
    },

    # --------------------------------------------------------
    # VAV / Zone Level
    # --------------------------------------------------------

    "zone_t": {
        "description": "Zone/space air temperature.",
        "kind": "sensor",
        "equipment": ("VAV", "AHU", "BUILDING"),
    },

    "zone_flow": {
        "description": "Zone airflow.",
        "kind": "sensor",
        "equipment": ("VAV",),
    },

    "min_flow_sp": {
        "description": "Minimum zone airflow setpoint.",
        "kind": "setpoint",
        "equipment": ("VAV",),
    },

    "vav_discharge_t": {
        "description": "VAV discharge air temperature.",
        "kind": "sensor",
        "equipment": ("VAV",),
    },

    "vav_inlet_t": {
        "description": "VAV inlet air temperature.",
        "kind": "sensor",
        "equipment": ("VAV",),
    },

    "ahu_sat": {
        "description": "Parent AHU discharge air temperature enriched onto VAV frame.",
        "kind": "sensor",
        "equipment": ("VAV",),
    },

    "clg_available": {
        "description": "Flag indicating central chilled water or economizer cooling available.",
        "kind": "status",
        "equipment": ("VAV",),
    },

    # --------------------------------------------------------
    # Chilled Water & Chiller Plant
    # --------------------------------------------------------

    "chiller_status": {
        "description": "Chiller operating/running status signal.",
        "kind": "status",
        "equipment": ("CHILLER", "PLANT"),
    },

    "chiller_cmd": {
        "description": "Chiller enable / run command.",
        "kind": "command",
        "equipment": ("CHILLER", "PLANT"),
    },

    "chiller_power": {
        "description": "Chiller active electrical power.",
        "kind": "sensor",
        "equipment": ("CHILLER", "PLANT"),
    },

    "chiller_amps": {
        "description": "Chiller electrical current (phase A or average).",
        "kind": "sensor",
        "equipment": ("CHILLER", "PLANT"),
    },

    "chiller_current": {
        "description": "Chiller electrical current draw.",
        "kind": "sensor",
        "equipment": ("CHILLER", "PLANT"),
    },

    "chw_pump_cmd": {
        "description": "Chilled-water pump command or speed.",
        "kind": "command",
        "equipment": ("CHILLER", "PLANT"),
    },

    "chw_pump_status": {
        "description": "Chilled-water pump operational proof/status.",
        "kind": "status",
        "equipment": ("CHILLER", "PLANT"),
    },

    "chw_supply_t": {
        "description": "Chilled-water supply temperature.",
        "kind": "sensor",
        "equipment": ("CHILLER", "PLANT", "AHU"),
    },

    "chw_return_t": {
        "description": "Chilled-water return temperature.",
        "kind": "sensor",
        "equipment": ("CHILLER", "PLANT", "AHU"),
    },

    "chw_supply_sp": {
        "description": "Chilled-water supply temperature setpoint.",
        "kind": "setpoint",
        "equipment": ("CHILLER", "PLANT"),
    },

    "chw_dp": {
        "description": "Chilled-water loop differential pressure.",
        "kind": "sensor",
        "equipment": ("CHILLER", "PLANT"),
    },

    "chw_dp_sp": {
        "description": "Chilled-water loop differential pressure setpoint.",
        "kind": "setpoint",
        "equipment": ("CHILLER", "PLANT"),
    },

    "chw_flow": {
        "description": "Chilled-water volumetric flow rate.",
        "kind": "sensor",
        "equipment": ("CHILLER", "PLANT"),
    },

    # --------------------------------------------------------
    # Hot Water & Boiler Plant
    # --------------------------------------------------------

    "hw_supply_t": {
        "description": "Hot-water supply temperature.",
        "kind": "sensor",
        "equipment": ("BOILER", "PLANT", "AHU"),
    },

    "hw_return_t": {
        "description": "Hot-water return temperature.",
        "kind": "sensor",
        "equipment": ("BOILER", "PLANT", "AHU"),
    },

    "pump_status": {
        "description": "Generic hydronic pump operational status/proof.",
        "kind": "status",
        "equipment": ("BOILER", "CHILLER", "PLANT"),
    },

    # --------------------------------------------------------
    # Condenser Water & Cooling Tower
    # --------------------------------------------------------

    "cw_supply_t": {
        "description": "Condenser-water supply temperature.",
        "kind": "sensor",
        "equipment": ("COOLING_TOWER", "PLANT"),
    },

    "cw_return_t": {
        "description": "Condenser-water return temperature.",
        "kind": "sensor",
        "equipment": ("COOLING_TOWER", "PLANT"),
    },

    "cw_pump_cmd": {
        "description": "Condenser-water pump command or speed.",
        "kind": "command",
        "equipment": ("COOLING_TOWER", "PLANT"),
    },

    "tower_fan_cmd": {
        "description": "Cooling-tower fan command or speed.",
        "kind": "command",
        "equipment": ("COOLING_TOWER", "PLANT"),
    },

    # --------------------------------------------------------
    # Heat Pump / DX Refrigeration
    # --------------------------------------------------------

    "compressor_status": {
        "description": "Compressor operating run/proof status signal.",
        "kind": "status",
        "equipment": ("HEAT_PUMP", "CHILLER", "AHU"),
    },

    # --------------------------------------------------------
    # Building Aggregates & Operation
    # --------------------------------------------------------

    "building_zone_load_satisfied": {
        "description": "Building zone load satisfaction aggregate signal.",
        "kind": "status",
        "equipment": ("BUILDING",),
    },

    "building_ahu_load_satisfied": {
        "description": "Building AHU SAT load satisfaction aggregate signal.",
        "kind": "status",
        "equipment": ("BUILDING",),
    },

    "occ_mode": {
        "description": "Occupancy or occupied operating mode indicator.",
        "kind": "mode",
        "equipment": ("BUILDING", "AHU", "VAV"),
    },

    # --------------------------------------------------------
    # Weather & Psychrometrics
    # --------------------------------------------------------

    "oa_h": {
        "description": "Outdoor-air relative humidity.",
        "kind": "sensor",
        "equipment": ("WEATHER", "AHU"),
    },

    "web_oa_t": {
        "description": "Weather-service outdoor air dry-bulb temperature.",
        "kind": "sensor",
        "equipment": ("WEATHER",),
    },

    "web_oa_dp": {
        "description": "Weather-service outdoor air dew point.",
        "kind": "sensor",
        "equipment": ("WEATHER",),
    },

    "web_wb_t": {
        "description": "Weather-service outdoor air wet-bulb temperature.",
        "kind": "sensor",
        "equipment": ("WEATHER",),
    },

    "web_oa_h": {
        "description": "Weather-service outdoor air relative humidity.",
        "kind": "sensor",
        "equipment": ("WEATHER",),
    },

    # --------------------------------------------------------
    # Project CO2 Extensions
    # --------------------------------------------------------

    "co2": {
        "description": "Indoor/zone CO2 concentration.",
        "kind": "sensor",
        "unit": "ppm",
        "equipment": ("AHU", "VAV", "BUILDING"),
    },

    "co2_sp": {
        "description": "Indoor/zone CO2 concentration setpoint or target.",
        "kind": "setpoint",
        "unit": "ppm",
        "equipment": ("AHU", "VAV", "BUILDING"),
    },

    "zone_h": {
        "description": "Indoor conditioned zone / space relative humidity.",
        "kind": "sensor",
        "unit": "%",
        "equipment": ("AHU", "VAV", "BUILDING"),
    },

    "clg_valve_fbk": {
        "description": "Cooling coil valve actuator position feedback or monitoring.",
        "kind": "sensor",
        "unit": "%",
        "equipment": ("AHU",),
    },

    "exhaust_fan_cmd": {
        "description": "Exhaust fan command or speed command.",
        "kind": "command",
        "equipment": ("AHU",),
    },

    "exhaust_fan_status": {
        "description": "Exhaust fan run status / operational proof signal.",
        "kind": "status",
        "equipment": ("AHU",),
    },

    "oa_velocity": {
        "description": "Outdoor air intake airflow face velocity.",
        "kind": "sensor",
        "unit": "m/s",
        "equipment": ("AHU",),
    },
}


# ============================================================
# VALIDATION
# ============================================================

EXPECTED_OPEN_FDD_ROLE_COUNT = 59
EXPECTED_PROJECT_EXTENSION_COUNT = 7
EXPECTED_TOTAL_ROLE_COUNT = 66


def validate_role_catalog() -> None:
    """Validate the canonical role catalog invariants and counts."""
    # Check duplicates in tuple declarations
    if len(set(OPEN_FDD_CANONICAL_ROLES)) != len(OPEN_FDD_CANONICAL_ROLES):
        duplicates = [r for r in OPEN_FDD_CANONICAL_ROLES if OPEN_FDD_CANONICAL_ROLES.count(r) > 1]
        raise RuntimeError(f"Duplicate roles found in OPEN_FDD_CANONICAL_ROLES: {set(duplicates)}")

    if len(set(PROJECT_EXTENSION_ROLES)) != len(PROJECT_EXTENSION_ROLES):
        duplicates = [r for r in PROJECT_EXTENSION_ROLES if PROJECT_EXTENSION_ROLES.count(r) > 1]
        raise RuntimeError(f"Duplicate roles found in PROJECT_EXTENSION_ROLES: {set(duplicates)}")

    # Check exact count requirements
    if len(OPEN_FDD_CANONICAL_ROLES) != EXPECTED_OPEN_FDD_ROLE_COUNT:
        raise RuntimeError(
            "Open-FDD canonical role count mismatch: "
            f"expected {EXPECTED_OPEN_FDD_ROLE_COUNT}, "
            f"got {len(OPEN_FDD_CANONICAL_ROLES)}"
        )

    if len(PROJECT_EXTENSION_ROLES) != EXPECTED_PROJECT_EXTENSION_COUNT:
        raise RuntimeError(
            "Project extension role count mismatch: "
            f"expected {EXPECTED_PROJECT_EXTENSION_COUNT}, "
            f"got {len(PROJECT_EXTENSION_ROLES)}"
        )

    if len(CANONICAL_ROLES) != EXPECTED_TOTAL_ROLE_COUNT:
        raise RuntimeError(
            "Total canonical role count mismatch: "
            f"expected {EXPECTED_TOTAL_ROLE_COUNT}, "
            f"got {len(CANONICAL_ROLES)}"
        )

    # Check CO2 extension presence
    if "co2" not in CANONICAL_ROLES or "co2_sp" not in CANONICAL_ROLES:
        raise RuntimeError("Project extension roles 'co2' and 'co2_sp' must exist in CANONICAL_ROLES")

    # Check that all declared roles exist in the catalog map
    all_declared = (*OPEN_FDD_CANONICAL_ROLES, *PROJECT_EXTENSION_ROLES)
    missing = [role for role in all_declared if role not in CANONICAL_ROLES]
    if missing:
        raise RuntimeError(f"Roles declared in tuples missing from CANONICAL_ROLES: {missing}")

    extra = [role for role in CANONICAL_ROLES if role not in all_declared]
    if extra:
        raise RuntimeError(f"Roles in CANONICAL_ROLES not declared in role tuples: {extra}")


validate_role_catalog()
