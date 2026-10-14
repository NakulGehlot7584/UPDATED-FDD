"""Grounded Diagnostic Engine for Open-FDD.

Maps rule violations to standardized engineering titles, severities, physical causes,
actionable checks, and grounded telemetry evidence with numerical confidence scoring.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from app.fdd.models import (
    FaultDetailRecord,
    FaultEpisode,
    FaultEvidence,
    RuleDefinition,
)

# Canonical role alias mapping to normalize shorthand names to roles.py
CANONICAL_ROLE_ALIASES: Dict[str, str] = {
    "clg_vlv": "clg_valve_pct",
    "htg_vlv": "htg_valve_pct",
    "oat": "oa_t",
    "oa_damper": "oa_damper_pct",
    "damper_pct": "oa_damper_pct",
    "fan_vfd_speed": "fan_cmd",
    "chw_temp": "chw_supply_t",
    "hw_temp": "hw_supply_t",
}

# Canonical rule diagnostics database aligned with official Open-FDD catalog
OFFICIAL_RULE_DIAGNOSTICS: Dict[str, Dict[str, Any]] = {
    "FC1": {
        "name": "Duct static below setpoint at full fan (GL36 A)",
        "category": "Airside",
        "severity": "HIGH",
        "causes": [
            "VFD speed limit reached or motor undersized",
            "Static pressure setpoint set unachievably high",
            "Duct leakage or open relief/fire damper",
            "Fan or belt slippage / aerodynamic degradation",
        ],
        "checks": [
            "Inspect VFD output frequency and current draw",
            "Verify duct static pressure sensor calibration and sensing tube",
            "Inspect ductwork for major leakage or open relief damper",
            "Check air filter differential pressure",
        ],
        "roles": ["duct_static", "duct_static_sp", "fan_cmd"],
    },
    "FC2": {
        "name": "Mixed-air temperature outside OA/RA limits (GL36 B)",
        "category": "Airside",
        "severity": "HIGH",
        "causes": [
            "Mixed-air temperature sensor calibration error or drift",
            "Return or outdoor air temperature sensor error",
            "Severe thermal stratification in mixing plenum",
        ],
        "checks": [
            "Verify MAT, OAT, and RAT sensor calibrations in ice/hot baths",
            "Inspect mixing plenum for airflow stratification",
            "Check averaging sensor capillary routing and installation",
        ],
        "roles": ["mat", "oat", "rat"],
    },
    "FC3": {
        "name": "Mixed-air temp equals return air temp while OA damper open (GL36 C)",
        "category": "Airside",
        "severity": "HIGH",
        "causes": [
            "Outdoor air damper mechanically stuck closed or broken linkage",
            "Damper actuator failed or disconnected from shaft",
            "Minimum ventilation damper override or freeze-stat interlock",
        ],
        "checks": [
            "Inspect outdoor air damper blades and mechanical linkage",
            "Verify actuator stroke with 0-10V or 2-10V command signal",
            "Check freeze-stat and low-temperature interlock circuits",
        ],
        "roles": ["mat", "rat", "oa_damper", "damper_pct"],
    },
    "FC4": {
        "name": "OA damper and cooling valve open simultaneously in heating (GL36 D)",
        "category": "Airside",
        "severity": "HIGH",
        "causes": [
            "Simultaneous heating and cooling control conflict in sequence",
            "Control loop tuning instability or hunting",
            "Faulty economizer changeover / high-limit lockout logic",
        ],
        "checks": [
            "Review BMS sequence of operations and deadbands",
            "Verify economizer enable threshold and enthalpy/temperature sensors",
            "Inspect cooling and heating controller output loops",
        ],
        "roles": ["oa_damper", "clg_vlv", "htg_vlv", "sat", "sat_sp"],
    },
    "FC5": {
        "name": "Supply air temp colder than mixed air in heating mode (GL36 E)",
        "category": "Heating",
        "severity": "HIGH",
        "causes": [
            "Heating valve failed to open or actuator disconnected",
            "Heating plant offline or inadequate hot water temperature",
            "Heating coil air-bound or circulation pump failed",
        ],
        "checks": [
            "Verify heating valve actuator stroke and feedback position",
            "Check hot water supply temperature and circulating pump status",
            "Inspect heating coil air vents and strainers",
        ],
        "roles": ["sat", "mat", "htg_vlv", "hw_temp"],
    },
    "FC6": {
        "name": "Economizer hunting or erratic airflow (GL36 F)",
        "category": "Economizer",
        "severity": "MEDIUM",
        "causes": [
            "OA damper control loop tuning too aggressive (excessive Kp)",
            "Airflow measuring station turbulence or zero-drift",
            "Wind gust pressure fluctuations on outside air louvers",
        ],
        "checks": [
            "Inspect OA damper PID loop parameters (increase integral time / decrease gain)",
            "Calibrate airflow measuring station transmitters",
            "Check outdoor louvers and damper linkage play",
        ],
        "roles": ["oa_damper", "damper_pct", "oa_flow", "mat"],
    },
    "FC7": {
        "name": "Supply air temp below setpoint during 100% heating (GL36 G)",
        "category": "Heating",
        "severity": "HIGH",
        "causes": [
            "Insufficient hot water flow or undersized heating coil",
            "Hot water supply temperature below design specification",
            "Heating valve undersized, fouled, or stem binding",
        ],
        "checks": [
            "Check hot water supply temperature and primary/secondary pumps",
            "Verify heating coil differential pressure and surface cleanliness",
            "Verify valve opens to 100% stroke mechanically and electronically",
        ],
        "roles": ["sat", "sat_sp", "htg_vlv", "mat"],
    },
    "FC8": {
        "name": "Supply air temp lower than mixed air during economizer heating (GL36 H)",
        "category": "Economizer",
        "severity": "HIGH",
        "causes": [
            "Chilled water valve leaking through or commanded open",
            "Temperature sensor calibration error between MAT and SAT",
        ],
        "checks": [
            "Inspect cooling valve close-off seating and actuator zero-point",
            "Measure cooling coil differential temperature with hand probe",
            "Calibrate MAT and SAT temperature sensors",
        ],
        "roles": ["sat", "mat", "clg_vlv", "oa_damper"],
    },
    "FC9": {
        "name": "OA damper closed when economizer cooling is favorable (GL36 I)",
        "category": "Economizer",
        "severity": "HIGH",
        "causes": [
            "Economizer high-limit lockout threshold set incorrectly",
            "OA damper actuator failure or linkage slipped",
            "Freeze protection low-limit thermostat active",
        ],
        "checks": [
            "Check economizer dry-bulb or enthalpy lockout setpoint",
            "Inspect OA damper actuator power, fuse, and control wiring",
            "Verify freeze protection thermostat contacts are reset",
        ],
        "roles": ["oa_damper", "oat", "mat", "sat_sp"],
    },
    "FC10": {
        "name": "Mixed-air temp lower than outdoor air in economizer mode (GL36 J)",
        "category": "Economizer",
        "severity": "HIGH",
        "causes": [
            "Preheat coil or heating valve active during economizer",
            "Sensor calibration error between OAT and MAT",
            "Return air damper failing to shut tightly",
        ],
        "checks": [
            "Verify preheat and heating valve are closed tightly",
            "Calibrate OAT and MAT sensors",
            "Inspect return air damper blade seals for leakage",
        ],
        "roles": ["mat", "oat", "oa_damper", "htg_vlv"],
    },
    "FC11": {
        "name": "Excessive outdoor air intake during mechanical cooling (GL36 K)",
        "category": "Economizer",
        "severity": "HIGH",
        "causes": [
            "OA damper stuck open beyond minimum ventilation position",
            "Damper actuator linkage slipped or zero-point drifted",
            "Incorrect minimum outdoor air setpoint configuration",
        ],
        "checks": [
            "Inspect OA damper blade position vs commanded position",
            "Verify minimum outdoor air setpoint in BMS programming",
            "Re-zero and calibrate OA damper actuator stroke",
        ],
        "roles": ["oa_damper", "oat", "mat", "clg_vlv"],
    },
    "FC12": {
        "name": "Supply air temp above setpoint in 100% economizer mode (GL36 L)",
        "category": "Economizer",
        "severity": "HIGH",
        "causes": [
            "OA damper not opening to full 100% mechanical position",
            "Economizer cooling capacity insufficient for building load",
            "Return air damper leaking warm air into mixing plenum",
        ],
        "checks": [
            "Verify outdoor air damper physical blade angle at 100% command",
            "Inspect return air damper blade seals and close-off torque",
            "Check for fan motor heat pickup or duct thermal gain",
        ],
        "roles": ["sat", "sat_sp", "oa_damper", "oat"],
    },
    "FC13": {
        "name": "Supply air temp above setpoint with 100% cooling & min OA (GL36 M)",
        "category": "Cooling",
        "severity": "HIGH",
        "causes": [
            "Chilled water supply temperature above design (warm loop)",
            "Low chilled water flow or circulation pump trip",
            "Fouled cooling coil or sediment buildup in tubes",
            "Cooling valve actuator binding or stem sheared",
        ],
        "checks": [
            "Verify chilled water supply/return temperatures and delta-T",
            "Inspect cooling coil pressure drop and water flow rate",
            "Verify cooling valve full mechanical stroke and stem integrity",
            "Check air filter and coil fin cleanliness",
        ],
        "roles": ["sat", "sat_sp", "clg_vlv", "chw_temp", "mat"],
    },
    "FC14": {
        "name": "Cooling coil leaving temp lower than entering with valve closed (GL36 N)",
        "category": "Cooling",
        "severity": "HIGH",
        "causes": [
            "Chilled water valve leaking through seat or partially open",
            "Valve actuator stroke misaligned / insufficient close-off torque",
            "0-10V control signal calibration offset or voltage drop",
        ],
        "checks": [
            "Check chilled water valve seating and physical shutoff",
            "Re-stroke cooling valve actuator with manual calibration routine",
            "Measure voltage at actuator terminals when commanded 0%",
        ],
        "roles": ["clg_vlv", "mat", "sat"],
    },
    "FC15": {
        "name": "Heating coil leaving temp higher than entering with valve closed (GL36 O)",
        "category": "Heating",
        "severity": "HIGH",
        "causes": [
            "Heating valve leaking through or seat fouled with debris",
            "Actuator stroke misaligned / spring return failure",
            "Bypass line open or internal check valve failure",
        ],
        "checks": [
            "Check heating valve close-off seating and valve body temperature",
            "Re-stroke heating valve actuator and verify shutoff spring",
            "Inspect valve seat for scale, grit, or debris",
        ],
        "roles": ["htg_vlv", "mat", "sat"],
    },
    "AHU-SATDEV": {
        "name": "Supply air temperature deviation from setpoint",
        "category": "Airside",
        "severity": "HIGH",
        "causes": [
            "Cooling or heating coil capacity deficit",
            "Control loop sluggish, poorly tuned, or unstable",
            "Valve actuator binding, hunting, or disconnected",
            "Temperature sensor calibration drift",
        ],
        "checks": [
            "Check chilled water and hot water plant supply temperatures",
            "Inspect cooling and heating valve operations and stroke ranges",
            "Tune SAT PID control loop (gain and integral response)",
            "Calibrate supply air temperature sensor",
        ],
        "roles": ["sat", "sat_sp", "clg_valve_pct", "htg_valve_pct", "fan_cmd"],
    },
    "AHU-DUCTHI": {
        "name": "Duct static pressure high limit exceeded",
        "category": "Airside",
        "severity": "CRITICAL",
        "causes": [
            "Multiple VAV terminal dampers driven closed simultaneously",
            "Duct static pressure sensor calibration error or blocked sensor tube",
            "VFD manual speed override or failure to ramp down",
        ],
        "checks": [
            "Inspect VAV terminal box damper positions and minimum stops",
            "Verify duct static pressure transmitter calibration and pneumatic tubing",
            "Check supply fan VFD speed control signal and BMS limits",
        ],
        "roles": ["duct_static", "duct_static_sp", "fan_cmd"],
    },
    "AHU-SIMUL": {
        "name": "Simultaneous heating and cooling valve operation",
        "category": "Energy Waste",
        "severity": "CRITICAL",
        "causes": [
            "Overlapping cooling and heating controller output sequences",
            "Manual operator hand override on valve actuator or in BMS",
            "Sequencing logic deadband configured to zero or negative",
        ],
        "checks": [
            "Inspect BMS heating/cooling deadband settings (ensure at least 2-4°F separation)",
            "Check physical valve actuators for manual override levers",
            "Review dual-loop PID output interlocks",
        ],
        "roles": ["clg_valve_pct", "htg_valve_pct", "sat", "sat_sp"],
    },
    "CMD-1": {
        "name": "Supply fan command vs status mismatch",
        "category": "Equipment Health",
        "severity": "CRITICAL",
        "causes": [
            "VFD or motor starter tripped on overcurrent or fault",
            "Current switch or differential pressure proof sensor failed",
            "Local Hand-Off-Auto (HOA) switch in Off or Hand position",
            "Blown fuse, thermal overload, or safety interlock open",
        ],
        "checks": [
            "Inspect VFD display for active fault codes (overcurrent, phase loss)",
            "Test differential pressure switch or current transducer threshold",
            "Verify physical HOA switch position on unit control cabinet",
            "Check duct smoke detector, freeze-stat, and high-pressure limit trip switches",
        ],
        "roles": ["fan_cmd", "fan_status"],
    },
    "SV-RANGE": {
        "name": "Sensor out of physical range",
        "category": "Sensor Health",
        "severity": "HIGH",
        "causes": [
            "Sensor wiring open circuit or short circuit to ground",
            "Transmitter electronics failure or water ingress",
            "Incorrect engineering units / scaling range in BMS database",
        ],
        "checks": [
            "Inspect sensor wiring, terminal strip, and field junction boxes",
            "Measure sensor resistance (RTD/thermistor) or 4-20mA loop current",
            "Check input point configuration and range table in controller",
        ],
        "roles": ["sat", "mat", "rat", "oa_t", "duct_static"],
    },
    "SV-FLATLINE": {
        "name": "Sensor flatline / stuck value",
        "category": "Sensor Health",
        "severity": "MEDIUM",
        "causes": [
            "Analog input channel locked or field bus communication frozen",
            "Sensor element disconnected or failed in latch mode",
            "Software override or test mode active in BMS point",
        ],
        "checks": [
            "Verify live reading varies with physical temperature or pressure changes",
            "Check controller analog input module status LEDs",
            "Confirm point is not under software hold or manual override",
        ],
        "roles": ["sat", "mat", "rat", "oa_t", "duct_static"],
    },
    "SV-SPIKE": {
        "name": "Sensor sudden spike / unphysical rate of change",
        "category": "Sensor Health",
        "severity": "MEDIUM",
        "causes": [
            "Electrical noise or loose wire connection on terminal block",
            "Ground loop interference or unshielded cable near VFD power conductors",
            "Intermittent sensor element fracture",
        ],
        "checks": [
            "Check cable shield grounding (grounded at controller end only)",
            "Tighten all terminal block screws on sensor circuit",
            "Separate sensor cable from motor power wires in cable trays",
        ],
        "roles": ["sat", "mat", "rat", "oa_t", "duct_static"],
    },
    "SV-STALE": {
        "name": "Stale sensor data / frozen telemetry",
        "category": "Sensor Health",
        "severity": "MEDIUM",
        "causes": [
            "BMS controller trend polling stalled",
            "Field bus network driver communication dropout",
            "Database export query frozen",
        ],
        "checks": [
            "Check BMS network trunk traffic and communication error counters",
            "Verify trend log buffer configuration and polling interval",
            "Restart controller network driver if communication halted",
        ],
        "roles": ["sat", "mat", "rat", "oa_t"],
    },
    "SV-RATE": {
        "name": "Sensor excessive rate of change",
        "category": "Sensor Health",
        "severity": "MEDIUM",
        "causes": [
            "Sudden process surge or rapid environmental transient",
            "Electromagnetic interference induced on unshielded cable",
        ],
        "checks": [
            "Verify sensor filtering / dampening time constant in controller",
            "Inspect wiring shield continuity and routing",
        ],
        "roles": ["sat", "mat", "rat", "duct_static"],
    },
    "PID-HUNT-1": {
        "name": "Control output hunting / persistent oscillation",
        "category": "Controls",
        "severity": "MEDIUM",
        "causes": [
            "Excessive proportional gain (Kp) or short integral time (Ti) in PID loop",
            "Sticky valve or damper actuator with mechanical deadband/backlash",
            "Oversized control valve causing non-linear authority",
        ],
        "checks": [
            "Tune PID loop parameters (reduce Kp by 30-50%, increase Ti)",
            "Inspect valve/damper actuator linkage for play, slop, or sticking",
            "Verify valve Cv sizing relative to actual system flow",
        ],
        "roles": ["clg_vlv", "htg_vlv", "oa_damper", "duct_static"],
    },
    "ECON-1": {
        "name": "Economizer damper closed during favorable free cooling",
        "category": "Economizer",
        "severity": "HIGH",
        "causes": [
            "Economizer high-limit temperature lockout setpoint too low",
            "OA damper actuator failure or disconnected control signal",
            "Low-limit freeze protection thermostat or smoke alarm override active",
        ],
        "checks": [
            "Verify outdoor air temperature lockout setpoint in BMS",
            "Inspect OA damper actuator stroke and 0-10V control signal",
            "Check safety interlocks and freeze-stat status",
        ],
        "roles": ["oa_damper", "oat", "mat", "sat_sp"],
    },
    "ECON-2": {
        "name": "Economizer damper modulation hunting",
        "category": "Economizer",
        "severity": "MEDIUM",
        "causes": [
            "Damper PID loop tuning too aggressive for airflow response time",
            "Plenum air turbulence at intake causing sensor noise",
            "Actuator feedback potentiometer wear or oscillation",
        ],
        "checks": [
            "Increase PID integral time and add input filtering to MAT sensor",
            "Inspect physical damper linkage for mechanical slop",
            "Check averaging temperature sensor in mixed air chamber",
        ],
        "roles": ["oa_damper", "mat", "oat", "sat"],
    },
    "ECON-3": {
        "name": "Mechanical cooling active while free cooling available",
        "category": "Economizer",
        "severity": "HIGH",
        "causes": [
            "Economizer staging sequence logic error",
            "Outdoor air enthalpy or dry-bulb sensor reading warmer than actual",
            "Cooling valve manual override or minimum cooling lock",
        ],
        "checks": [
            "Review BMS economizer staging logic (free cooling should precede DX/CHW)",
            "Calibrate outdoor air temperature and humidity sensors",
            "Verify cooling valve is not held open by manual override",
        ],
        "roles": ["clg_vlv", "oa_damper", "oat", "sat_sp"],
    },
    "SCHED-1": {
        "name": "Fan operating during unoccupied schedule",
        "category": "Schedule",
        "severity": "MEDIUM",
        "causes": [
            "BMS occupancy schedule override active",
            "Night setback or warm-up cycle stuck active",
            "Local HOA switch left in Hand position",
        ],
        "checks": [
            "Check BMS weekly schedule calendar and temporary overrides",
            "Inspect field HOA switch position on unit controller",
            "Review optimum start/stop program parameters",
        ],
        "roles": ["fan_cmd", "fan_status", "occ_mode"],
    },
    "SCHED-247": {
        "name": "Equipment operating 24/7 continuously without schedule",
        "category": "Schedule",
        "severity": "MEDIUM",
        "causes": [
            "Missing occupancy schedule in building automation controller",
            "Equipment set to continuous 24/7 run mode without setback",
            "Tenant after-hours override timer permanently latched",
        ],
        "checks": [
            "Configure standard occupancy schedules and night setback setpoints",
            "Inspect BMS after-hours override software switches",
            "Verify zone temperature setback response during unoccupied periods",
        ],
        "roles": ["fan_cmd", "fan_status"],
    },
    "RESET-1": {
        "name": "Supply air temperature reset logic not functioning",
        "category": "Controls",
        "severity": "LOW",
        "causes": [
            "Trim-and-respond reset logic disabled or not mapped to zone requests",
            "Static SAT setpoint configured instead of dynamic outdoor/zone reset",
            "Zone cooling/heating request network communication lost",
        ],
        "checks": [
            "Review BMS SAT reset curve parameters and trim-and-respond logic",
            "Verify VAV terminal cooling request network bindings",
            "Ensure SAT setpoint floats between minimum and maximum bounds",
        ],
        "roles": ["sat_sp", "oat", "sat"],
    },
    "OA-1": {
        "name": "Outdoor air fraction below required ventilation rate",
        "category": "Indoor Air Quality",
        "severity": "HIGH",
        "causes": [
            "OA damper closed below minimum ventilation setpoint",
            "Intake louver blockage or severe dirty pre-filters",
            "Inaccurate mixed air or return air temperature sensors",
        ],
        "checks": [
            "Verify minimum outdoor air damper setpoint in BMS",
            "Inspect outdoor air intake louvers, bird screens, and filters",
            "Calibrate temperature sensors used for airflow fraction estimation",
        ],
        "roles": ["oa_damper", "mat", "rat", "oat"],
    },
    "DMP-1": {
        "name": "Damper position tracking failure",
        "category": "Airside",
        "severity": "HIGH",
        "causes": [
            "Damper actuator stalled, stripped gear, or motor failure",
            "Slipped shaft linkage or loose U-bolt",
            "Feedback potentiometer signal disconnected or uncalibrated",
        ],
        "checks": [
            "Inspect damper actuator linkage and tighten shaft clamps",
            "Compare commanded 0-10V signal with actual feedback position",
            "Verify damper moves freely without mechanical binding across full 0-100% stroke",
        ],
        "roles": ["oa_damper", "damper_pct"],
    },
    "VLV-1": {
        "name": "Cooling valve hunting or leakage detected",
        "category": "Hydronic",
        "severity": "HIGH",
        "causes": [
            "Cooling valve PID loop tuning too aggressive",
            "Leaking valve seat or foreign debris preventing full close-off",
            "Actuator linkage play or insufficient closing torque",
        ],
        "checks": [
            "Re-tune cooling valve PID loop with lower proportional gain",
            "Inspect valve seat for erosion, wire-drawing, or scale buildup",
            "Verify actuator spring return and seating torque",
        ],
        "roles": ["clg_vlv", "sat", "mat"],
    },
    "VAV-1": {
        "name": "VAV zone comfort temperature fault",
        "category": "Terminal / VAV",
        "severity": "HIGH",
        "causes": [
            "Zone airflow below setpoint or damper actuator binding",
            "Reheat coil valve failure or inadequate hot water temperature",
            "Thermostat sensor drift or poor installation location",
        ],
        "checks": [
            "Inspect VAV damper actuator and velocity pressure sensor",
            "Check reheat valve operation and hot water supply temperature",
            "Calibrate zone temperature sensor",
        ],
        "roles": ["zone_temp", "zone_temp_sp", "zone_flow", "damper_pct"],
    },
    "VAV-2": {
        "name": "VAV night setback temperature recovery failure",
        "category": "Terminal / VAV",
        "severity": "MEDIUM",
        "causes": [
            "Optimum start duration too short for morning warm-up/cool-down",
            "Central AHU supply temperature too cold/warm during warmup",
            "VAV reheat or damper undersized for morning pickup load",
        ],
        "checks": [
            "Review optimum start algorithm lead time parameters",
            "Verify AHU supply air temperature during morning warm-up mode",
            "Inspect VAV reheat valve full opening",
        ],
        "roles": ["zone_temp", "occ_mode", "zone_flow"],
    },
    "VAV-3": {
        "name": "Excessive reheat with cooling airflow",
        "category": "Energy Waste",
        "severity": "CRITICAL",
        "causes": [
            "VAV minimum airflow setpoint configured too high",
            "Simultaneous cooling airflow and reheat valve operation",
            "Reheat valve leaking through when cooling required",
        ],
        "checks": [
            "Verify VAV minimum airflow setpoint conforms to ASHRAE 62.1",
            "Check reheat valve seating and close-off",
            "Review dual-maximum or single-maximum VAV control logic",
        ],
        "roles": ["reheat_valve", "zone_flow", "zone_temp"],
    },
    "VAV-4": {
        "name": "VAV damper hunting or persistent oscillation",
        "category": "Terminal / VAV",
        "severity": "MEDIUM",
        "causes": [
            "Airflow controller PID loop gain too aggressive",
            "Differential pressure sensor tubing kinking or turbulence",
            "Damper actuator motor backlash",
        ],
        "checks": [
            "Increase PID integral time in VAV controller airflow loop",
            "Inspect flow cross pickup sensor tubes for condensation or kinks",
            "Check damper actuator gearbox for mechanical play",
        ],
        "roles": ["damper_pct", "zone_flow", "zone_flow_sp"],
    },
}


def get_diagnostic_meta(rule_id: str, rule_def: Optional[RuleDefinition] = None) -> Dict[str, Any]:
    """Retrieve or derive standard diagnostic metadata for a rule."""
    clean_id = (rule_id or "").strip().upper()

    # Direct match in canonical dictionary
    if clean_id in OFFICIAL_RULE_DIAGNOSTICS:
        return dict(OFFICIAL_RULE_DIAGNOSTICS[clean_id])

    # Check aliases
    for k, v in OFFICIAL_RULE_DIAGNOSTICS.items():
        if clean_id.replace("-", "_") == k.replace("-", "_"):
            return dict(v)

    # Fallback to rule_def or generic derivation
    name = clean_id
    category = "General FDD"
    severity = "HIGH"
    causes = [
        "Mechanical component degradation or actuator failure",
        "Control loop tuning or sequencing logic conflict",
        "Sensor calibration offset or signal drift",
    ]
    checks = [
        "Inspect field equipment mechanical status and actuator stroke",
        "Verify BMS control loop setpoints, schedules, and deadbands",
        "Calibrate associated sensors with calibrated test instruments",
    ]
    roles: List[str] = []

    if rule_def:
        if rule_def.description:
            name = rule_def.description
        if rule_def.priority:
            p_map = {"P0": "CRITICAL", "P1": "HIGH", "P2": "MEDIUM", "P3": "LOW"}
            severity = p_map.get(rule_def.priority, "HIGH")
        roles = list(rule_def.required_roles)

        # Categorize by prefix
        rid_lower = clean_id.lower()
        if "vav" in rid_lower:
            category = "Terminal / VAV"
        elif "chw" in rid_lower or "cw" in rid_lower:
            category = "Hydronic"
        elif "econ" in rid_lower:
            category = "Economizer"
        elif "sv" in rid_lower:
            category = "Sensor Health"
        elif "sched" in rid_lower:
            category = "Schedule"
        elif "ahu" in rid_lower or "fc" in rid_lower:
            category = "Airside"

    return {
        "name": name,
        "category": category,
        "severity": severity,
        "causes": causes,
        "checks": checks,
        "roles": roles,
    }


def build_grounded_diagnostic(
    rule_id: str,
    equipment_id: str,
    building_id: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
    episodes: Optional[List[FaultEpisode]] = None,
    telemetry_summary: Optional[Dict[str, Any]] = None,
    available_roles: Optional[Set[str]] = None,
    rule_def: Optional[RuleDefinition] = None,
    raw_sample_count: Optional[int] = None,
) -> FaultDetailRecord:
    """Build an enriched, grounded FaultDetailRecord with evidence and confidence scoring.

    Parameters
    ----------
    rule_id : str
        FDD rule identifier.
    equipment_id : str
        Equipment identifier.
    building_id : Optional[str]
        Building partition ID.
    metrics : Optional[Dict[str, Any]]
        Row metrics output by DataFusion rule execution.
    episodes : Optional[List[FaultEpisode]]
        Segmented fault episodes.
    telemetry_summary : Optional[Dict[str, Any]]
        Telemetry summary observed during fault episodes.
    available_roles : Optional[Set[str]]
        Set of canonical roles available in equipment dataset.
    rule_def : Optional[RuleDefinition]
        Rule definition from catalog.

    Returns
    -------
    FaultDetailRecord
        Enriched diagnostic record.
    """
    row_metrics = metrics or {}
    fault_eps = episodes or []
    canon_roles = available_roles or set()
    t_summary = telemetry_summary or {}

    meta = get_diagnostic_meta(rule_id, rule_def)
    rule_name = meta["name"]
    category = meta["category"]
    severity = meta["severity"]
    possible_causes = list(meta["causes"])
    recommended_checks = list(meta["checks"])
    target_roles = list(meta.get("roles", []))

    fault_hours = float(row_metrics.get("fault_hours", 0.0) or 0.0)
    fault_pct = float(row_metrics.get("fault_pct", 0.0) or 0.0) if "fault_pct" in row_metrics else None
    total_hours = float(row_metrics.get("total_hours", 0.0) or 0.0) if "total_hours" in row_metrics else None

    # Calculate duration and counts
    total_fault_hours = fault_hours if fault_hours > 0 else round(sum(e.duration_hours for e in fault_eps), 4)
    episode_count = len(fault_eps)
    sample_count = sum(e.samples for e in fault_eps)
    fault_detected = total_fault_hours > 0.001 or episode_count > 0

    # Grounded evidence formulation
    evidence_list: List[FaultEvidence] = []
    missing_context: List[str] = []

    # Check missing context roles
    for r in target_roles:
        canon_r = CANONICAL_ROLE_ALIASES.get(r.lower(), r.lower())
        if canon_r not in canon_roles and r.lower() not in canon_roles:
            missing_context.append(r)

    # Specific evidence construction based on rule telemetry
    clean_id = rule_id.upper()
    observed_vals: Dict[str, Any] = {}

    if clean_id in {"AHU-SATDEV", "FC13-SAT-HIGH", "SAT-HIGH-FAULT"}:
        sat_val = t_summary.get("sat", {}).get("mean")
        sp_val = t_summary.get("sat_sp", {}).get("mean")
        clg_val = t_summary.get("clg_valve_pct", {}).get("mean")
        if sat_val is not None and sp_val is not None:
            delta = sat_val - sp_val
            observed_vals["sat_mean"] = round(sat_val, 2)
            observed_vals["sat_sp_mean"] = round(sp_val, 2)
            observed_vals["delta_temp"] = round(delta, 2)
            if clg_val is not None:
                observed_vals["clg_valve_pct_mean"] = round(clg_val, 1)
            clg_str = f", Cooling Valve: {clg_val:.0f}%" if clg_val is not None else ""
            ev_text = (
                f"[CONFIRMED BY DATA] Supply air temperature deviates by {delta:+.1f}° from setpoint "
                f"(Observed SAT: {sat_val:.1f}°, SP: {sp_val:.1f}°{clg_str})"
            )
            evidence_list.append(
                FaultEvidence(
                    evidence_text=ev_text,
                    confidence="CONFIRMED",
                    observed_values=observed_vals,
                    missing_context_roles=missing_context,
                )
            )
        else:
            ev_text = (
                f"[SUPPORTED BY DATA] Supply air temperature deviation sustained for {total_fault_hours:.2f} hours "
                f"across {episode_count} episode(s)"
            )
            evidence_list.append(
                FaultEvidence(
                    evidence_text=ev_text,
                    confidence="SUPPORTED" if not missing_context else "LIMITED",
                    observed_values={"fault_hours": total_fault_hours},
                    missing_context_roles=missing_context,
                )
            )

    elif clean_id == "FC1":
        dsp_val = t_summary.get("duct_static", {}).get("mean")
        sp_val = t_summary.get("duct_static_sp", {}).get("mean")
        fan_val = t_summary.get("fan_cmd", {}).get("mean")
        if dsp_val is not None and sp_val is not None:
            deficit = dsp_val - sp_val
            observed_vals["duct_static_mean"] = round(dsp_val, 3)
            observed_vals["duct_static_sp_mean"] = round(sp_val, 3)
            observed_vals["deficit"] = round(deficit, 3)
            if fan_val is not None:
                observed_vals["fan_cmd_mean"] = round(fan_val, 1)
                ev_text = (
                    f"[CONFIRMED BY DATA] Duct static pressure is {dsp_val:.2f} versus {sp_val:.2f} setpoint "
                    f"({deficit:+.2f} deficit) while fan command is {fan_val:.0f}%"
                )
            else:
                ev_text = f"[CONFIRMED BY DATA] Duct static pressure is {dsp_val:.2f} versus {sp_val:.2f} setpoint ({deficit:+.2f} deficit)"
            evidence_list.append(
                FaultEvidence(
                    evidence_text=ev_text,
                    confidence="CONFIRMED",
                    observed_values=observed_vals,
                    missing_context_roles=missing_context,
                )
            )
        else:
            ev_text = (
                f"[SUPPORTED BY DATA] Duct static fault active for {total_fault_hours:.2f} hours "
                f"across {episode_count} episode(s)"
            )
            evidence_list.append(
                FaultEvidence(
                    evidence_text=ev_text,
                    confidence="SUPPORTED",
                    observed_values={"fault_hours": total_fault_hours},
                    missing_context_roles=missing_context,
                )
            )

    elif clean_id == "AHU-DUCTHI":
        dsp_val = t_summary.get("duct_static", {}).get("mean")
        sp_val = t_summary.get("duct_static_sp", {}).get("mean")
        if dsp_val is not None:
            observed_vals["duct_static_mean"] = round(dsp_val, 3)
            if sp_val is not None:
                observed_vals["duct_static_sp_mean"] = round(sp_val, 3)
                ev_text = f"[CONFIRMED BY DATA] Duct static pressure is {dsp_val:.2f} exceeding setpoint {sp_val:.2f}"
            else:
                ev_text = f"[CONFIRMED BY DATA] Duct static pressure high reading is {dsp_val:.2f}"
            evidence_list.append(
                FaultEvidence(
                    evidence_text=ev_text,
                    confidence="CONFIRMED",
                    observed_values=observed_vals,
                    missing_context_roles=missing_context,
                )
            )
        else:
            ev_text = (
                f"[SUPPORTED BY DATA] Duct static high fault active for {total_fault_hours:.2f} hours "
                f"across {episode_count} episode(s)"
            )
            evidence_list.append(
                FaultEvidence(
                    evidence_text=ev_text,
                    confidence="SUPPORTED",
                    observed_values={"fault_hours": total_fault_hours},
                    missing_context_roles=missing_context,
                )
            )

    elif clean_id == "CMD-1":
        cmd_val = t_summary.get("fan_cmd", {}).get("mean")
        stat_val = t_summary.get("fan_status", {}).get("mean")
        if cmd_val is not None and stat_val is not None:
            observed_vals["fan_cmd"] = round(cmd_val, 1)
            observed_vals["fan_status"] = round(stat_val, 1)
            cmd_fmt = f"{cmd_val:.0f}%" if cmd_val > 1.0 else f"{cmd_val:.0f}"
            ev_text = (
                f"[CONFIRMED BY DATA] Supply fan command is ON ({cmd_fmt}) "
                f"but fan run status feedback indicates OFF ({stat_val:.0f})"
            )
            evidence_list.append(
                FaultEvidence(
                    evidence_text=ev_text,
                    confidence="CONFIRMED",
                    observed_values=observed_vals,
                    missing_context_roles=missing_context,
                )
            )
        else:
            ev_text = (
                f"[SUPPORTED BY DATA] Fan command/status mismatch detected for {total_fault_hours:.2f} hours"
            )
            evidence_list.append(
                FaultEvidence(
                    evidence_text=ev_text,
                    confidence="SUPPORTED",
                    observed_values={"fault_hours": total_fault_hours},
                    missing_context_roles=missing_context,
                )
            )

    elif clean_id.startswith("SV-"):
        faulted_sensors = t_summary.get("faulted_sensors", [])
        if faulted_sensors:
            sens_str = ", ".join(faulted_sensors)
            observed_vals["faulted_sensors"] = faulted_sensors
            observed_vals["fault_hours"] = total_fault_hours
            observed_vals["episodes"] = episode_count
            ev_text = (
                f"[CONFIRMED BY DATA] Sensor validation fault detected on: {sens_str} "
                f"for {total_fault_hours:.2f} hours across {episode_count} episode(s)"
            )
        else:
            ev_text = (
                f"[CONFIRMED BY DATA] Sensor telemetry violates physical validation criteria "
                f"for {total_fault_hours:.2f} hours across {episode_count} episode(s)"
            )
            observed_vals["fault_hours"] = total_fault_hours
            observed_vals["episodes"] = episode_count
        evidence_list.append(
            FaultEvidence(
                evidence_text=ev_text,
                confidence="CONFIRMED",
                observed_values=observed_vals,
                missing_context_roles=missing_context,
            )
        )

    else:
        # Generic official rule grounding
        ev_text = (
            f"[SUPPORTED BY DATA] Official rule {rule_id} condition satisfied for "
            f"{total_fault_hours:.2f} fault hours ({episode_count} episode(s))"
        )
        conf = "CONFIRMED" if len(missing_context) == 0 and total_fault_hours > 0 else "SUPPORTED"
        evidence_list.append(
            FaultEvidence(
                evidence_text=ev_text,
                confidence=conf,
                observed_values=row_metrics,
                missing_context_roles=missing_context,
            )
        )

    # Missing context cautionary note
    if missing_context:
        evidence_list.append(
            FaultEvidence(
                evidence_text=(
                    f"[CANNOT BE FULLY CORROBORATED] Context telemetry channel(s) "
                    f"[{', '.join(missing_context)}] not present in uploaded CSV"
                ),
                confidence="LIMITED",
                observed_values={},
                missing_context_roles=missing_context,
            )
        )

    title = f"{rule_name} on {equipment_id}"
    desc = (
        f"{rule_name} active for {total_fault_hours:.2f} hours ({episode_count} episode(s)). "
        f"Severity: {severity}."
    )

    return FaultDetailRecord(
        rule_id=rule_id,
        rule_name=rule_name,
        equipment_id=equipment_id,
        building_id=building_id,
        category=category,
        severity=severity,
        title=title,
        description=desc,
        fault_detected=fault_detected,
        total_fault_hours=total_fault_hours,
        fault_pct=fault_pct,
        total_hours=total_hours,
        sample_count=sample_count,
        raw_sample_count=raw_sample_count if raw_sample_count is not None else row_metrics.get("raw_count"),
        episode_count=episode_count,
        episodes=fault_eps,
        evidence=evidence_list,
        possible_causes=possible_causes,
        recommended_checks=recommended_checks,
        metrics=row_metrics,
        associated_roles=target_roles,
    )
