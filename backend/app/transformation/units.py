"""
Physical unit conversion functions, role unit catalogs, and semantic column classification for canonical HVAC telemetry.

Design Principles:
1. Exact Mathematical Conversions: Implements standard HVAC engineering conversion formulas.
2. Safe Vectorized Execution: Uses Polars expressions to apply conversions efficiently.
3. Identity Fallback: If units match or no conversion is defined, preserves original values without alteration.
4. Auditable: Returns descriptive conversion metadata for full pipeline traceability.
"""

from __future__ import annotations

import re
from typing import Callable
import polars as pl

from app.mapping.normalizer import normalize_column_name


# Type alias for a conversion formula operating on a Polars Series
ConversionFn = Callable[[pl.Series], pl.Series]


# ============================================================
# CANONICAL ROLE UNIT METADATA
# ============================================================

CANONICAL_ROLE_UNITS: dict[str, str | None] = {
    # Temperature (°F)
    "sat": "°F",
    "sat_sp": "°F",
    "rat": "°F",
    "mat": "°F",
    "oa_t": "°F",
    "zone_t": "°F",
    "chw_supply_t": "°F",
    "chw_return_t": "°F",
    "hw_supply_t": "°F",
    "hw_return_t": "°F",
    "cw_supply_t": "°F",
    "cw_return_t": "°F",
    "web_oa_t": "°F",
    "web_oa_dp": "°F",
    "web_wb_t": "°F",
    "preheat_leave_t": "°F",
    "cooling_coil_entering_temp": "°F",
    "cooling_coil_leaving_temp": "°F",
    "heating_coil_entering_temp": "°F",
    "heating_coil_leaving_temp": "°F",
    "vav_discharge_t": "°F",
    "vav_inlet_t": "°F",
    "ahu_sat": "°F",
    "chw_supply_sp": "°F",

    # Pressure (in_wc / psi)
    "duct_static": "in_wc",
    "duct_static_sp": "in_wc",
    "chw_dp": "psi",
    "chw_dp_sp": "psi",

    # Percentage / Position / Speed (%)
    "fan_cmd": "%",
    "oa_damper_pct": "%",
    "damper_pct": "%",
    "clg_valve_pct": "%",
    "clg_valve_fbk": "%",
    "htg_valve_pct": "%",
    "reheat_valve_pct": "%",
    "cw_pump_cmd": "%",
    "tower_fan_cmd": "%",
    "chw_pump_cmd": "%",
    "oa_h": "%",
    "web_oa_h": "%",
    "zone_h": "%",

    # Flow (CFM / GPM)
    "zone_flow": "CFM",
    "vav_total_flow": "CFM",
    "min_flow_sp": "CFM",
    "chw_flow": "GPM",

    # Concentration (ppm)
    "co2": "ppm",
    "co2_sp": "ppm",

    # Power & Current (kW / A)
    "chiller_power": "kW",
    "chiller_amps": "A",
    "chiller_current": "A",

    # Velocity (m/s)
    "oa_velocity": "m/s",
}


def _infer_source_unit(column_name: str) -> str | None:
    """
    Safely extract source unit from standard column name suffixes or bracketed unit tokens.
    Returns None if no standard unit indicator is present.
    """
    norm = column_name.lower().strip()

    # 1. Check parenthesized/bracketed units e.g. (deg C), (°C), (ppm), (Pa), (%), (%RH), etc.
    match = re.search(r"[\(\[\{]([^\)\]\}]+)[\)\]\}]", norm)
    if match:
        unit_token = match.group(1).strip()
        if unit_token in ("°c", "deg c", "degc", "c", "celsius"):
            return "°C"
        if unit_token in ("°f", "deg f", "degf", "f", "fahrenheit"):
            return "°F"
        if unit_token in ("pa", "pascal"):
            return "Pa"
        if unit_token in ("kpa", "kilopascal"):
            return "kPa"
        if unit_token in ("in_wc", "inwc", "inh2o", "in_h2o", "in. w.c.", "in. wg"):
            return "in_wc"
        if unit_token in ("%", "%rh", "% rh", "percent", "pct"):
            return "%"
        if unit_token in ("ppm", "co2_ppm", "ppm co2"):
            return "ppm"
        if unit_token in ("cfm", "cf_m", "ft3/min"):
            return "CFM"
        if unit_token in ("lps", "l/s", "l_s"):
            return "L/s"
        if unit_token in ("gpm", "gp_m", "gal/min"):
            return "GPM"
        if unit_token in ("kw", "k_w"):
            return "kW"
        if unit_token in ("amps", "amp", "a"):
            return "A"
        if unit_token in ("mps", "m/s", "m_s"):
            return "m/s"

    # 2. Suffixes
    if norm.endswith(("_c", "_degc", "_deg_c", "_celsius")):
        return "°C"
    if norm.endswith(("_f", "_degf", "_deg_f", "_fahrenheit")):
        return "°F"
    if norm.endswith(("_pa", "_pascal")):
        return "Pa"
    if norm.endswith(("_kpa", "_kilopascal")):
        return "kPa"
    if norm.endswith(("_in_wc", "_inwc", "_inh2o", "_in_h2o")):
        return "in_wc"
    if norm.endswith(("_pct", "_percent", "_percentage", "_percent_cmd")):
        return "%"
    if norm.endswith(("_ppm", "_co2_ppm")):
        return "ppm"
    if norm.endswith(("_cfm", "_cf_m")):
        return "CFM"
    if norm.endswith(("_lps", "_l_s")):
        return "L/s"
    if norm.endswith(("_gpm", "_gp_m")):
        return "GPM"
    if norm.endswith(("_kw", "_k_w")):
        return "kW"
    if norm.endswith(("_amps", "_amp", "_a")):
        return "A"
    if norm.endswith(("_mps", "_m_s")):
        return "m/s"

    return None


def _is_conversion_required(source_unit: str | None, canonical_unit: str | None) -> bool:
    """
    Determine whether physical unit conversion is required between source and canonical units.
    """
    if not source_unit or not canonical_unit:
        return False

    s = source_unit.strip().lower().replace("deg", "°")
    c = canonical_unit.strip().lower().replace("deg", "°")

    return s != c


def _classify_column_category(col_name: str, mapped: bool, is_conflict: bool) -> str:
    """
    Classify a source column into a semantic category to avoid mislabeling
    infrastructure metadata or auxiliary BMS signals as mapping errors.
    """
    if mapped:
        return "CANONICAL_SIGNAL"
    if is_conflict:
        return "CONFLICT"

    norm = normalize_column_name(col_name)

    # 1. Temporal index metadata
    if norm in (
        "timestamp",
        "timestamp_utc",
        "time_stamp",
        "date",
        "date_time",
        "datetime",
        "time",
        "event_time",
        "recorded_at",
        "ts",
        "epoch",
        "unix_time",
    ):
        return "TEMPORAL_METADATA"

    # 2. Topology / Device identifier metadata
    if norm in (
        "equipment_id",
        "equipment",
        "building_id",
        "building",
        "site_id",
        "site",
        "device_id",
        "device",
        "asset_id",
        "ahu_id",
        "vav_id",
    ):
        return "TOPOLOGY_METADATA"

    # 3. Ground-truth benchmark evaluation metadata
    if ("expected" in norm and "fault" in norm) or norm.startswith("ground_truth"):
        return "BENCHMARK_METADATA"

    # 4. Auxiliary BMS signals (HOA switch / maintenance flags)
    if any(k in norm for k in ("auto_mode", "hand_mode", "hoa", "filter_dirty", "dirty_filter", "economizer_mode")):
        return "AUXILIARY_BMS"

    return "UNSUPPORTED"


# ============================================================
# CONVERSION FORMULAS
# ============================================================

def _celsius_to_fahrenheit(s: pl.Series) -> pl.Series:
    """Convert Celsius (°C) to Fahrenheit (°F): (C * 9/5) + 32."""
    return s * (9.0 / 5.0) + 32.0


def _kelvin_to_fahrenheit(s: pl.Series) -> pl.Series:
    """Convert Kelvin (K) to Fahrenheit (°F): ((K - 273.15) * 9/5) + 32."""
    return (s - 273.15) * (9.0 / 5.0) + 32.0


def _pascal_to_in_wc(s: pl.Series) -> pl.Series:
    """Convert Pascal (Pa) to Inches of Water Column (in_wc): Pa * 0.00401463."""
    return s * 0.00401463076


def _kilopascal_to_in_wc(s: pl.Series) -> pl.Series:
    """Convert kiloPascal (kPa) to Inches of Water Column (in_wc): kPa * 4.01463."""
    return s * 4.01463076


def _pascal_to_psi(s: pl.Series) -> pl.Series:
    """Convert Pascal (Pa) to PSI: Pa * 0.0001450377."""
    return s * 0.0001450377


def _kilopascal_to_psi(s: pl.Series) -> pl.Series:
    """Convert kiloPascal (kPa) to PSI: kPa * 0.1450377."""
    return s * 0.1450377


def _bar_to_psi(s: pl.Series) -> pl.Series:
    """Convert Bar to PSI: Bar * 14.50377."""
    return s * 14.50377


def _liters_per_sec_to_cfm(s: pl.Series) -> pl.Series:
    """Convert Liters/second (L/s) to CFM: L/s * 2.11888."""
    return s * 2.11888


def _cubic_meters_per_hour_to_cfm(s: pl.Series) -> pl.Series:
    """Convert m3/h to CFM: m3/h * 0.588578."""
    return s * 0.58857778


def _cubic_meters_per_sec_to_cfm(s: pl.Series) -> pl.Series:
    """Convert m3/s to CFM: m3/s * 2118.88."""
    return s * 2118.88


def _liters_per_sec_to_gpm(s: pl.Series) -> pl.Series:
    """Convert Liters/second (L/s) to GPM: L/s * 15.8503."""
    return s * 15.8503


def _cubic_meters_per_hour_to_gpm(s: pl.Series) -> pl.Series:
    """Convert m3/h to GPM: m3/h * 4.40287."""
    return s * 4.40287


def _fpm_to_mps(s: pl.Series) -> pl.Series:
    """Convert Feet Per Minute (fpm) to Meters/second (m/s): fpm * 0.00508."""
    return s * 0.00508


def _watts_to_kw(s: pl.Series) -> pl.Series:
    """Convert Watts (W) to kiloWatts (kW): W / 1000."""
    return s / 1000.0


def _megawatts_to_kw(s: pl.Series) -> pl.Series:
    """Convert MegaWatts (MW) to kiloWatts (kW): MW * 1000."""
    return s * 1000.0


def _ratio_to_percent(s: pl.Series) -> pl.Series:
    """Convert 0.0-1.0 fraction/ratio to percentage (%): ratio * 100."""
    return s * 100.0


# ============================================================
# CONVERSION REGISTRY
# ============================================================

# Mapping of (normalized_source_unit, normalized_canonical_unit) -> (conversion_fn, formula_description)
UNIT_CONVERSION_REGISTRY: dict[tuple[str, str], tuple[ConversionFn, str]] = {
    # Temperature -> °F
    ("°c", "°f"): (_celsius_to_fahrenheit, "(val * 9/5) + 32"),
    ("deg c", "°f"): (_celsius_to_fahrenheit, "(val * 9/5) + 32"),
    ("degc", "°f"): (_celsius_to_fahrenheit, "(val * 9/5) + 32"),
    ("c", "°f"): (_celsius_to_fahrenheit, "(val * 9/5) + 32"),
    ("celsius", "°f"): (_celsius_to_fahrenheit, "(val * 9/5) + 32"),
    ("k", "°f"): (_kelvin_to_fahrenheit, "((val - 273.15) * 9/5) + 32"),
    ("kelvin", "°f"): (_kelvin_to_fahrenheit, "((val - 273.15) * 9/5) + 32"),

    # Pressure -> in_wc (air duct pressure)
    ("pa", "in_wc"): (_pascal_to_in_wc, "val * 0.00401463"),
    ("pascal", "in_wc"): (_pascal_to_in_wc, "val * 0.00401463"),
    ("kpa", "in_wc"): (_kilopascal_to_in_wc, "val * 4.01463"),
    ("kilopascal", "in_wc"): (_kilopascal_to_in_wc, "val * 4.01463"),

    # Pressure -> psi (hydronic loop differential pressure)
    ("pa", "psi"): (_pascal_to_psi, "val * 0.0001450377"),
    ("kpa", "psi"): (_kilopascal_to_psi, "val * 0.1450377"),
    ("bar", "psi"): (_bar_to_psi, "val * 14.50377"),

    # Flow -> CFM (airflow)
    ("l/s", "cfm"): (_liters_per_sec_to_cfm, "val * 2.11888"),
    ("lps", "cfm"): (_liters_per_sec_to_cfm, "val * 2.11888"),
    ("l_s", "cfm"): (_liters_per_sec_to_cfm, "val * 2.11888"),
    ("m3/h", "cfm"): (_cubic_meters_per_hour_to_cfm, "val * 0.588578"),
    ("m3/s", "cfm"): (_cubic_meters_per_sec_to_cfm, "val * 2118.88"),

    # Flow -> GPM (water flow)
    ("l/s", "gpm"): (_liters_per_sec_to_gpm, "val * 15.8503"),
    ("lps", "gpm"): (_liters_per_sec_to_gpm, "val * 15.8503"),
    ("m3/h", "gpm"): (_cubic_meters_per_hour_to_gpm, "val * 4.40287"),

    # Velocity -> m/s
    ("fpm", "m/s"): (_fpm_to_mps, "val * 0.00508"),
    ("ft/min", "m/s"): (_fpm_to_mps, "val * 0.00508"),

    # Power -> kW
    ("w", "kw"): (_watts_to_kw, "val / 1000.0"),
    ("watt", "kw"): (_watts_to_kw, "val / 1000.0"),
    ("mw", "kw"): (_megawatts_to_kw, "val * 1000.0"),

    # Ratio -> %
    ("ratio", "%"): (_ratio_to_percent, "val * 100.0"),
    ("fraction", "%"): (_ratio_to_percent, "val * 100.0"),
}


def _normalize_unit_str(unit: str | None) -> str:
    """Normalize a unit string for uniform lookup."""
    if not unit:
        return ""
    return (
        unit.strip()
        .lower()
        .replace("deg ", "°")
        .replace("deg", "°")
        .replace("%rh", "%")
        .replace("% rh", "%")
    )


def apply_unit_conversion(
    series: pl.Series,
    source_unit: str | None,
    canonical_unit: str | None,
) -> tuple[pl.Series, str | None]:
    """
    Apply physical unit conversion to a numeric Polars Series if required.

    Args:
        series: Source numeric series (must be Float64 or castable).
        source_unit: Inferred physical unit of the source column (e.g., "°C", "Pa", "L/s").
        canonical_unit: Target canonical physical unit (e.g., "°F", "in_wc", "CFM").

    Returns:
        tuple of:
        - converted_series: Polars Series with conversion formula applied.
        - formula_description: String describing applied formula, or None if no conversion applied.
    """
    if not source_unit or not canonical_unit:
        return series, None

    norm_src = _normalize_unit_str(source_unit)
    norm_tgt = _normalize_unit_str(canonical_unit)

    if norm_src == norm_tgt:
        return series, None

    lookup_key = (norm_src, norm_tgt)
    entry = UNIT_CONVERSION_REGISTRY.get(lookup_key)

    if entry is not None:
        fn, formula_desc = entry
        converted = fn(series)
        return converted, formula_desc

    # No conversion defined for this pair; preserve values unmodified without inventing arbitrary conversion
    return series, None
