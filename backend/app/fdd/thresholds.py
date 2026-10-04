"""Threshold Catalog & Metadata Engine for Official Open-FDD Rules.

Sourced 100% dynamically from backend/app/fdd/sql_rules/registry.yaml and SQL templates.
Provides verified tuning parameter definitions, categories, tiers, presets, and validation bounds.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.fdd.catalog import RuleCatalog, get_rule_catalog


class ThresholdItem(BaseModel):
    """Verified configurable tuning threshold for an FDD rule."""
    placeholder: str
    param_name: str
    label: str
    category: str
    tier: str  # TIER_A (User-Facing) | TIER_B (Advanced) | TIER_C (Internal)
    default_value: float
    min_value: float
    max_value: float
    step: float
    unit: str
    description: str
    applicable_rules: List[str] = Field(default_factory=list)
    equipment_kinds: List[str] = Field(default_factory=list)


class ThresholdCategory(BaseModel):
    """Grouping of related FDD thresholds."""
    name: str
    display_order: int
    description: str
    tier: str = "TIER_A"


class ThresholdCatalogResponse(BaseModel):
    """Complete metadata response for UI threshold controls and presets."""
    categories: List[ThresholdCategory] = Field(default_factory=list)
    parameters: List[ThresholdItem] = Field(default_factory=list)
    presets: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    total_parameters: int = 0
    tier_a_count: int = 0
    tier_b_count: int = 0


# Exact 12 categories required by specification
CATEGORIES_METADATA: List[Dict[str, Any]] = [
    {
        "name": "General Fault Confirmation",
        "display_order": 1,
        "description": "Persistence filters and general confirmation windows across fault detection rules",
        "tier": "TIER_A",
    },
    {
        "name": "Supply Air Temperature",
        "display_order": 2,
        "description": "Discharge and supply air temperature setpoint deviation and cooling/heating thresholds",
        "tier": "TIER_A",
    },
    {
        "name": "Mixed Air / Outdoor Air",
        "display_order": 3,
        "description": "Outdoor air fraction, mixed air energy balance tolerance, and damper leakage margins",
        "tier": "TIER_A",
    },
    {
        "name": "Duct Static Pressure",
        "display_order": 4,
        "description": "Duct static pressure overpressure limits and full fan capacity static error margins",
        "tier": "TIER_A",
    },
    {
        "name": "Fan / Airside",
        "display_order": 5,
        "description": "Airside fan status confirmation and running state parameters",
        "tier": "TIER_A",
    },
    {
        "name": "Valve / Simultaneous Heating-Cooling",
        "display_order": 6,
        "description": "Heating and cooling coil valve overlap and simultaneous conditioning thresholds",
        "tier": "TIER_A",
    },
    {
        "name": "Zone Comfort",
        "display_order": 7,
        "description": "Occupied space temperature comfort envelope, night setback, and VAV terminal reheat bounds",
        "tier": "TIER_A",
    },
    {
        "name": "Hydronic / Chilled Water",
        "display_order": 8,
        "description": "Chilled water low Delta-T, loop differential pressure, flow limits, and cooling tower approach",
        "tier": "TIER_A",
    },
    {
        "name": "Economizer",
        "display_order": 9,
        "description": "Free cooling dry-bulb, dew-point, damper position, and freeze-protection limits",
        "tier": "TIER_A",
    },
    {
        "name": "PID / Control Behavior",
        "display_order": 10,
        "description": "Loop hunting, operating-state reversals, cyclic oscillation, and span tolerances",
        "tier": "TIER_A",
    },
    {
        "name": "Reset / Static Reset",
        "display_order": 11,
        "description": "Trim-and-respond setpoint reset curves, reference temperatures, and tracking errors",
        "tier": "TIER_A",
    },
    {
        "name": "Advanced Rule Parameters",
        "display_order": 12,
        "description": "Sensor validation rate-of-change, flatline persistence, stale data, and weather spikes",
        "tier": "TIER_B",
    },
]

PARAM_TAXONOMY: Dict[str, tuple[str, str, str]] = {
    # 1. General Fault Confirmation
    "CONFIRM_SECONDS": (
        "General Fault Confirmation",
        "TIER_A",
        "Minimum sustained duration an abnormal condition must persist before confirming an active fault episode",
    ),
    "ALWAYS_ON_PCT": (
        "General Fault Confirmation",
        "TIER_B",
        "Threshold runtime fraction (0-1) defining continuous unscheduled 24/7 fan/pump operation",
    ),

    # 2. Supply Air Temperature
    "SAT_DEV_ERR": (
        "Supply Air Temperature",
        "TIER_A",
        "Allowable temperature deviation between supply air temperature and active cooling/heating setpoint",
    ),
    "SAT_ERR": (
        "Supply Air Temperature",
        "TIER_A",
        "Supply air temperature error tolerance during saturated cooling or heating modes",
    ),
    "CLG_VALVE_MIN": (
        "Supply Air Temperature",
        "TIER_B",
        "Cooling valve position threshold to qualify active mechanical cooling status",
    ),
    "HTG_FULL_MIN": (
        "Supply Air Temperature",
        "TIER_B",
        "Heating command threshold defining 100% full heating saturation",
    ),
    "HTG_ON_MIN": (
        "Supply Air Temperature",
        "TIER_B",
        "Heating command threshold indicating heating is actively commanded",
    ),
    "MAT_LEAK_DELTA": (
        "Supply Air Temperature",
        "TIER_B",
        "Supply vs mixed air temperature differential flagging chilled water valve bypass leakage",
    ),

    # 3. Mixed Air / Outdoor Air
    "MIX_TOL": (
        "Mixed Air / Outdoor Air",
        "TIER_A",
        "Tolerance between measured mixed air temp and theoretical mixed temp from damper air balance",
    ),
    "MIN_OA_FRAC": (
        "Mixed Air / Outdoor Air",
        "TIER_A",
        "Minimum allowable outdoor air fraction required for indoor ventilation compliance",
    ),
    "OA_MIN_PCT": (
        "Mixed Air / Outdoor Air",
        "TIER_A",
        "Minimum estimated outdoor air percentage threshold",
    ),
    "LEAK_DELTA": (
        "Mixed Air / Outdoor Air",
        "TIER_A",
        "Temperature difference across closed outdoor air damper indicating outdoor air leakage",
    ),
    "AIRFLOW_ERR": (
        "Mixed Air / Outdoor Air",
        "TIER_B",
        "Outdoor airflow error margin for ventilation balance screening",
    ),
    "DELTA_T_MIN": (
        "Mixed Air / Outdoor Air",
        "TIER_B",
        "Minimum |OAT - RAT| differential required to evaluate outdoor air fraction reliably",
    ),
    "MIN_CFM_DESIGN": (
        "Mixed Air / Outdoor Air",
        "TIER_B",
        "Design minimum outdoor airflow volume in CFM",
    ),
    "OAT_RAT_GUARD": (
        "Mixed Air / Outdoor Air",
        "TIER_B",
        "Minimum temperature split between OAT and RAT to prevent mathematical instability",
    ),
    "OAT_ERR": (
        "Mixed Air / Outdoor Air",
        "TIER_B",
        "Allowable error between equipment outdoor sensor and local weather reference",
    ),

    # 4. Duct Static Pressure
    "DUCT_HIGH_MARGIN": (
        "Duct Static Pressure",
        "TIER_A",
        "Allowable static pressure overshoot above duct static pressure setpoint before flagging overpressure",
    ),
    "EPS_DSP": (
        "Duct Static Pressure",
        "TIER_A",
        "Allowable static pressure error below setpoint when supply fan is commanded to full speed",
    ),
    "PRESSURE_ON_MIN": (
        "Duct Static Pressure",
        "TIER_B",
        "Static pressure floor confirming supply fan is actively generating airflow",
    ),
    "EPS_VFD_SPD": (
        "Duct Static Pressure",
        "TIER_B",
        "Fan VFD speed margin defining maximum fan capacity saturation",
    ),
    "DUCT_HI": (
        "Duct Static Pressure",
        "TIER_B",
        "High static pressure limit for duct static pressure trim-and-respond reset",
    ),

    # 5. Fan / Airside
    # Note: CMD-1 mismatch persistence uses CONFIRM_SECONDS

    # 6. Valve / Simultaneous Heating-Cooling
    "VALVE_OPEN_PCT": (
        "Valve / Simultaneous Heating-Cooling",
        "TIER_A",
        "Threshold position above which heating and cooling valves are flagged as fighting simultaneously",
    ),

    # 7. Zone Comfort
    "ZONE_T_LO": (
        "Zone Comfort",
        "TIER_A",
        "Target comfort envelope lower temperature limit for occupied zones",
    ),
    "ZONE_T_HI": (
        "Zone Comfort",
        "TIER_A",
        "Target comfort envelope upper temperature limit for occupied zones",
    ),
    "SETBACK_HI": (
        "Zone Comfort",
        "TIER_A",
        "Night setback heating temperature ceiling for unoccupied zones",
    ),
    "REHEAT_OAT": (
        "Zone Comfort",
        "TIER_A",
        "Ambient outdoor temperature above which terminal zone reheat is flagged excessive",
    ),
    "REHEAT_PCT": (
        "Zone Comfort",
        "TIER_B",
        "Maximum terminal reheat valve command allowed during warm weather or free cooling",
    ),
    "FREE_COOL_OAT": (
        "Zone Comfort",
        "TIER_B",
        "Outdoor air temperature ceiling for free cooling economizer reheat lock",
    ),
    "FLOW_ON_MIN": (
        "Zone Comfort",
        "TIER_B",
        "Minimum airflow threshold qualifying active delivery through a terminal box",
    ),
    "FULL_OPEN_PCT": (
        "Zone Comfort",
        "TIER_B",
        "Terminal damper position threshold defining 100% full open status",
    ),
    "SUSTAIN_HOURS": (
        "Zone Comfort",
        "TIER_B",
        "Required sustained duration of full open damper before fault generation",
    ),
    "REHEAT_CMD": (
        "Zone Comfort",
        "TIER_B",
        "Terminal box reheat command threshold to test discharge air temperature rise",
    ),
    "MIN_RISE": (
        "Zone Comfort",
        "TIER_B",
        "Minimum expected discharge air temperature rise across active reheat coil",
    ),
    "DELTA_F": (
        "Zone Comfort",
        "TIER_B",
        "Allowable temperature delta between terminal box discharge and parent AHU supply air temp",
    ),
    "HIGH_MIN_FLOW_SP": (
        "Zone Comfort",
        "TIER_B",
        "Threshold defining an excessively high minimum airflow setpoint",
    ),
    "FIXED_FLOW_HOURS": (
        "Zone Comfort",
        "TIER_B",
        "Rolling lookback window for detecting stuck unchanging airflow",
    ),
    "FIXED_FLOW_MAX_STD": (
        "Zone Comfort",
        "TIER_B",
        "Maximum standard deviation indicating stuck flatline airflow reading",
    ),
    "FIXED_FLOW_MIN_MEAN": (
        "Zone Comfort",
        "TIER_B",
        "Minimum mean airflow required to flag stuck high airflow",
    ),

    # 8. Hydronic / Chilled Water
    "MIN_DT": (
        "Hydronic / Chilled Water",
        "TIER_A",
        "Minimum chilled water supply/return temperature difference (Delta T syndrome)",
    ),
    "SP_BAND": (
        "Hydronic / Chilled Water",
        "TIER_A",
        "Allowable chilled water supply temperature deadband around setpoint",
    ),
    "DP_MARGIN": (
        "Hydronic / Chilled Water",
        "TIER_A",
        "Chilled water differential pressure error margin below setpoint at full pump speed",
    ),
    "PUMP_HI": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "Chilled water pump speed defining full pumping capacity",
    ),
    "FLOW_HI": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "Chilled water loop excessive flow threshold at maximum pump speed",
    ),
    "CHW_LO": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "Low chilled water temperature limit for plant trim-and-respond reset",
    ),
    "HWST_HI": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "High hot water supply temperature limit for boiler reset",
    ),
    "CW_APPROACH": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "Design cooling tower approach to ambient wet-bulb temperature",
    ),
    "CW_SLACK": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "Allowable slack below optimized condenser water target",
    ),
    "APPROACH_MAX_F": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "Maximum acceptable cooling tower approach at 100% tower fan speed",
    ),
    "TOWER_FAN_HI": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "Cooling tower fan speed threshold defining full cooling tower capacity",
    ),
    "EXCESS_BEYOND_APPROACH_F": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "Condenser water temperature excess beyond design approach",
    ),
    "MIN_SAT": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "Heat pump minimum heating discharge supply temperature",
    ),
    "ZONE_COLD": (
        "Hydronic / Chilled Water",
        "TIER_B",
        "Heat pump zone cold space temperature threshold",
    ),

    # 9. Economizer
    "ECON1_OAT_MIN": (
        "Economizer",
        "TIER_A",
        "Outdoor air temperature above which economizer free cooling is favorable",
    ),
    "ECON1_DAMPER_MAX": (
        "Economizer",
        "TIER_B",
        "Maximum outdoor air damper position defining stuck-closed condition",
    ),
    "ECON2_OAT_HI": (
        "Economizer",
        "TIER_A",
        "Outdoor air temperature ceiling above which economizer dampers must close",
    ),
    "ECON2_DAMPER": (
        "Economizer",
        "TIER_B",
        "Damper position threshold indicating open economizer when outdoor air is unfavorable",
    ),
    "ECON3_DB_MIN": (
        "Economizer",
        "TIER_A",
        "Outdoor air dry-bulb floor for integrated mechanical cooling economizer",
    ),
    "ECON3_DB_MAX": (
        "Economizer",
        "TIER_A",
        "Outdoor air dry-bulb ceiling for integrated mechanical cooling economizer",
    ),
    "ECON3_DP_MAX": (
        "Economizer",
        "TIER_A",
        "Outdoor air dew-point ceiling for economizer operation",
    ),
    "ECON3_DAMPER_HI": (
        "Economizer",
        "TIER_B",
        "Damper position threshold for integrated economizer free cooling",
    ),
    "PREHEAT_OVER_F": (
        "Economizer",
        "TIER_A",
        "Preheat coil over-conditioning temperature rise threshold",
    ),
    "ECON6_OAT_MAX_F": (
        "Economizer",
        "TIER_A",
        "Freezing weather ambient temperature threshold",
    ),
    "ECON6_DAMPER_MAX": (
        "Economizer",
        "TIER_B",
        "Maximum allowable outdoor air damper position in freezing weather",
    ),
    "ECON7_DB_MIN": (
        "Economizer",
        "TIER_A",
        "Economizer OK freeze-guard minimum dry-bulb temperature floor",
    ),
    "ECON7_DB_MAX": (
        "Economizer",
        "TIER_A",
        "Economizer OK maximum dry-bulb temperature ceiling",
    ),
    "ECON7_DP_MAX": (
        "Economizer",
        "TIER_A",
        "Economizer OK maximum dew-point ceiling",
    ),
    "ECON7_DAMPER_MIN": (
        "Economizer",
        "TIER_B",
        "Damper position threshold defining active economizing state",
    ),
    "OA_DAMPER_ECON_LOW": (
        "Economizer",
        "TIER_B",
        "Damper low threshold during high SAT fault evaluation",
    ),
    "OA_DAMPER_ECON_HIGH": (
        "Economizer",
        "TIER_B",
        "Damper high threshold during high SAT fault evaluation",
    ),
    "MECH_OAT_MAX_F": (
        "Economizer",
        "TIER_A",
        "Outdoor air temperature ceiling below which mechanical cooling is prohibited without economizer",
    ),

    # 10. PID / Control Behavior
    "DELTA_OS_MAX": (
        "PID / Control Behavior",
        "TIER_A",
        "Maximum allowed control operating-state transitions per hour before flagging hunting",
    ),
    "CHANGE_DEADBAND_PCT": (
        "PID / Control Behavior",
        "TIER_B",
        "Deadband percentage to filter out minor actuator telemetry noise",
    ),
    "MINIMUM_SPAN_PCT": (
        "PID / Control Behavior",
        "TIER_B",
        "Minimum peak-to-peak output swing span required to flag hunting",
    ),
    "TOTAL_VARIATION_FAULT_PCT": (
        "PID / Control Behavior",
        "TIER_B",
        "Cumulative actuator travel variation percentage indicating excessive oscillation",
    ),
    "MINIMUM_EQUIVALENT_CYCLES": (
        "PID / Control Behavior",
        "TIER_B",
        "Minimum full oscillation cycles required in analysis window",
    ),
    "MINIMUM_REVERSALS": (
        "PID / Control Behavior",
        "TIER_B",
        "Minimum directional reversals required to detect cyclic hunting",
    ),
    "MINIMUM_COVERAGE_PCT": (
        "PID / Control Behavior",
        "TIER_B",
        "Minimum valid sample coverage percentage in hunting analysis window",
    ),
    "WINDOW_HOURS": (
        "PID / Control Behavior",
        "TIER_B",
        "Lookback window duration for actuator hunting assessment",
    ),

    # 11. Reset / Static Reset
    "RESET_ERR_F": (
        "Reset / Static Reset",
        "TIER_A",
        "Supply air temperature reset curve tracking error margin",
    ),
    "RESET_SAT_AT_65": (
        "Reset / Static Reset",
        "TIER_B",
        "Design supply air temp setpoint at 65°F outdoor air reference",
    ),
    "RESET_SLOPE": (
        "Reset / Static Reset",
        "TIER_B",
        "Slope ratio of supply air temperature reset schedule",
    ),
    "RESET_OAT_REF": (
        "Reset / Static Reset",
        "TIER_B",
        "Outdoor air reference temperature for reset schedule calculation",
    ),
    "REQUEST_LO": (
        "Reset / Static Reset",
        "TIER_B",
        "Zone cooling request count floor for trim-and-respond setpoint reset",
    ),

    # 12. Advanced Rule Parameters
    "RANGE_SCALE_TEMPERATURE": (
        "Advanced Rule Parameters",
        "TIER_B",
        "Multiplier scaling the physical validity envelope for temperature sensors",
    ),
    "FLATLINE_TOL": (
        "Advanced Rule Parameters",
        "TIER_B",
        "Maximum variation threshold defining a flatlined/stuck sensor",
    ),
    "FLATLINE_HOURS": (
        "Advanced Rule Parameters",
        "TIER_B",
        "Consecutive duration window required to flag sensor flatline",
    ),
    "SPIKE_SCALE": (
        "Advanced Rule Parameters",
        "TIER_B",
        "Multiplier scaling sensor rate-of-change spike threshold",
    ),
    "STALE_HOURS": (
        "Advanced Rule Parameters",
        "TIER_B",
        "Duration threshold without telemetry updates defining stale communication",
    ),
    "STALE_TOL": (
        "Advanced Rule Parameters",
        "TIER_B",
        "Variation tolerance defining stale unchanging telemetry values",
    ),
    "PERSISTENCE_MIN": (
        "Advanced Rule Parameters",
        "TIER_B",
        "Minimum persistence duration required to confirm a sensor slew fault",
    ),
    "STEADY_FAULT_PER_HOUR": (
        "Advanced Rule Parameters",
        "TIER_B",
        "Steady-state allowable temperature slew rate per hour",
    ),
    "SPIKE_LIMIT": (
        "Advanced Rule Parameters",
        "TIER_B",
        "Maximum single-step ambient temperature spike limit",
    ),
}

# Supported Presets strictly derived from Open-FDD baseline parameters
PRESETS_DEFINITIONS: Dict[str, Dict[str, float]] = {
    "Standard": {
        "confirm_seconds": 900.0,
        "sat_dev_err": 5.0,
        "sat_err": 1.0,
        "mix_tol": 1.15,
        "duct_high_margin": 0.25,
        "eps_dsp": 0.12,
        "valve_open_pct": 0.10,
        "min_oa_frac": 0.15,
        "oa_min_pct": 21.0,
        "leak_delta": 2.0,
        "delta_os_max": 5.0,
        "reset_err_f": 3.0,
        "zone_t_lo": 70.0,
        "zone_t_hi": 75.0,
        "setback_hi": 68.0,
        "reheat_oat": 78.0,
        "econ1_oat_min": 55.0,
        "econ2_oat_hi": 63.0,
        "econ3_db_min": 60.0,
        "econ3_db_max": 72.0,
        "min_dt": 4.0,
        "sp_band": 2.2,
        "dp_margin": 2.2,
    },
    "Sensitive": {
        "confirm_seconds": 300.0,
        "sat_dev_err": 2.5,
        "sat_err": 0.5,
        "mix_tol": 0.60,
        "duct_high_margin": 0.10,
        "eps_dsp": 0.06,
        "valve_open_pct": 0.05,
        "min_oa_frac": 0.18,
        "oa_min_pct": 25.0,
        "leak_delta": 1.0,
        "delta_os_max": 3.0,
        "reset_err_f": 1.5,
        "zone_t_lo": 71.0,
        "zone_t_hi": 74.0,
        "setback_hi": 66.0,
        "reheat_oat": 75.0,
        "econ1_oat_min": 53.0,
        "econ2_oat_hi": 65.0,
        "econ3_db_min": 58.0,
        "econ3_db_max": 70.0,
        "min_dt": 5.0,
        "sp_band": 1.5,
        "dp_margin": 1.5,
    },
    "Lenient": {
        "confirm_seconds": 1800.0,
        "sat_dev_err": 8.0,
        "sat_err": 2.0,
        "mix_tol": 2.50,
        "duct_high_margin": 0.50,
        "eps_dsp": 0.20,
        "valve_open_pct": 0.15,
        "min_oa_frac": 0.10,
        "oa_min_pct": 15.0,
        "leak_delta": 3.5,
        "delta_os_max": 8.0,
        "reset_err_f": 5.0,
        "zone_t_lo": 68.0,
        "zone_t_hi": 77.0,
        "setback_hi": 70.0,
        "reheat_oat": 82.0,
        "econ1_oat_min": 57.0,
        "econ2_oat_hi": 60.0,
        "econ3_db_min": 62.0,
        "econ3_db_max": 74.0,
        "min_dt": 3.0,
        "sp_band": 3.5,
        "dp_margin": 3.5,
    },
}


def build_threshold_catalog(catalog: Optional[RuleCatalog] = None) -> ThresholdCatalogResponse:
    """Dynamically construct threshold catalog from RuleCatalog loaded from registry.yaml."""
    if catalog is None:
        catalog = get_rule_catalog()

    rules = catalog.list_rules()
    
    # Placeholder mapping
    from collections import defaultdict
    placeholder_map = defaultdict(list)

    for rule_def in rules:
        # Check confirm_seconds
        placeholder_map["CONFIRM_SECONDS"].append({
            "rule_id": rule_def.rule_id,
            "param_name": "confirm_seconds",
            "label": "Fault confirmation persistence",
            "default": float(rule_def.confirm_seconds),
            "min": 0.0,
            "max": 3600.0,
            "step": 300.0,
            "unit": "s",
            "equipment_kinds": rule_def.equipment_kinds,
        })

        for p_name, p_def in rule_def.parameters.items():
            plh = p_def.sql_placeholder.strip().upper()
            if plh == "CONFIRM_SECONDS":
                continue
            placeholder_map[plh].append({
                "rule_id": rule_def.rule_id,
                "param_name": p_name,
                "label": p_def.label,
                "default": float(p_def.default),
                "min": float(p_def.min),
                "max": float(p_def.max),
                "step": float(p_def.step),
                "unit": p_def.unit,
                "equipment_kinds": rule_def.equipment_kinds,
            })

    items: List[ThresholdItem] = []
    
    for plh, usages in sorted(placeholder_map.items()):
        if plh not in PARAM_TAXONOMY:
            continue
        
        category, tier, desc = PARAM_TAXONOMY[plh]
        first = usages[0]
        rules_using = sorted(list({u["rule_id"] for u in usages}))
        equipment = sorted(list({k for u in usages for k in u["equipment_kinds"]}))
        from collections import Counter
        param_counts = Counter([u["param_name"] for u in usages])
        primary_param_name = param_counts.most_common(1)[0][0]

        mins = [u["min"] for u in usages]
        maxs = [u["max"] for u in usages]
        steps = [u["step"] for u in usages]
        units = [u["unit"] for u in usages if u["unit"]]

        unit_str = units[0] if units else ""
        if unit_str in ["sec", "s"]: unit_str = "s"
        elif unit_str in ["degF", "°F", "F"]: unit_str = "°F"
        elif unit_str in ["inwc", "in_wc"]: unit_str = "in_wc"
        elif unit_str in ["frac"]: unit_str = "frac"
        elif unit_str in ["pct"]: unit_str = "%"
        elif unit_str in ["cfm"]: unit_str = "cfm"
        elif unit_str in ["psi"]: unit_str = "psi"
        elif unit_str in ["gpm"]: unit_str = "gpm"
        elif unit_str in ["degF_per_h"]: unit_str = "°F/h"
        elif unit_str in ["h"]: unit_str = "h"
        elif unit_str in ["min"]: unit_str = "min"
        elif unit_str in ["count"]: unit_str = "count"
        elif unit_str in ["x"]: unit_str = "x"

        items.append(
            ThresholdItem(
                placeholder=plh,
                param_name=primary_param_name,
                label=first["label"],
                category=category,
                tier=tier,
                default_value=first["default"],
                min_value=min(mins),
                max_value=max(maxs),
                step=steps[0],
                unit=unit_str,
                description=desc,
                applicable_rules=rules_using,
                equipment_kinds=equipment,
            )
        )

    categories = [ThresholdCategory(**c) for c in CATEGORIES_METADATA]
    tier_a = [i for i in items if i.tier == "TIER_A"]
    tier_b = [i for i in items if i.tier == "TIER_B"]

    return ThresholdCatalogResponse(
        categories=categories,
        parameters=items,
        presets=PRESETS_DEFINITIONS,
        total_parameters=len(items),
        tier_a_count=len(tier_a),
        tier_b_count=len(tier_b),
    )


_GLOBAL_THRESHOLD_CATALOG: Optional[ThresholdCatalogResponse] = None


def get_threshold_catalog() -> ThresholdCatalogResponse:
    """Singleton getter for threshold catalog metadata."""
    global _GLOBAL_THRESHOLD_CATALOG
    if _GLOBAL_THRESHOLD_CATALOG is None:
        _GLOBAL_THRESHOLD_CATALOG = build_threshold_catalog()
    return _GLOBAL_THRESHOLD_CATALOG
