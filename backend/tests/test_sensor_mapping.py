"""Test suite for sensor identification, canonical role mapping,
prefix/suffix patterns, disambiguation, unmapped column safety, and original column preservation.
"""

import pytest
from app.mapping.mapper import map_columns
from app.mapping.roles import CANONICAL_ROLES
from app.mapping.normalizer import normalize_column_name


def test_known_sensor_patterns_and_prefixes():
    cols = [
        "timestamp",
        "AHU1_SAT",
        "AHU-01.RAT",
        "AHU1_SupplyFan_Cmd",
        "AHU1_DuctStatic_SP",
        "AHU1_OA_Damper_Pct",
    ]
    res = map_columns(cols)
    assert res.has_role("sat")
    assert res.has_role("rat")
    assert res.has_role("fan_cmd")
    assert res.has_role("duct_static_sp")
    assert res.has_role("oa_damper_pct")


def test_case_insensitive_and_delimiters():
    cols = ["timestamp", "ahu1_sat", "AHU1.RAT", "Ahu1-MAT"]
    res = map_columns(cols)
    assert res.get_column_for_role("sat") == "ahu1_sat"
    assert res.get_column_for_role("rat") == "AHU1.RAT"
    assert res.get_column_for_role("mat") == "Ahu1-MAT"


def test_disambiguation_between_measurement_and_setpoint():
    cols = ["timestamp", "AHU1_SAT", "AHU1_SAT_SP", "AHU1_DSP", "AHU1_DSP_SP"]
    res = map_columns(cols)
    assert res.get_column_for_role("sat") == "AHU1_SAT"
    assert res.get_column_for_role("sat_sp") == "AHU1_SAT_SP"
    assert res.has_role("duct_static") or res.has_role("duct_static_sp")


def test_unmapped_columns_preservation_without_crashing():
    cols = [
        "timestamp",
        "AHU1_SAT",
        "Random_Vendor_Field_XYZ",
        "Building_Security_Alarm",
        "Chiller_Electric_Meter_KwH",
    ]
    res = map_columns(cols)
    assert res.has_role("sat")
    assert "Random_Vendor_Field_XYZ" in res.unmapped_columns
    assert "Building_Security_Alarm" in res.unmapped_columns
    assert len(res.conflicts) == 0


def test_original_column_preservation_in_mappings():
    cols = ["timestamp", "AHU_Floor2_SupplyAirTemperature_DegF"]
    res = map_columns(cols)
    role = res.get_role_for_column("AHU_Floor2_SupplyAirTemperature_DegF")
    assert role == "sat"
    assert res.get_column_for_role("sat") == "AHU_Floor2_SupplyAirTemperature_DegF"


def test_canonical_roles_catalog_integrity():
    assert "sat" in CANONICAL_ROLES
    assert "rat" in CANONICAL_ROLES
    assert "mat" in CANONICAL_ROLES
    assert "oa_t" in CANONICAL_ROLES
    assert "fan_cmd" in CANONICAL_ROLES
    assert "fan_status" in CANONICAL_ROLES
    assert "clg_valve_pct" in CANONICAL_ROLES
    assert "htg_valve_pct" in CANONICAL_ROLES
    assert len(CANONICAL_ROLES) >= 59
