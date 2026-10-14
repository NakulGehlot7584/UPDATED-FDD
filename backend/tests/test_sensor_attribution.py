"""Test suite for sensor-level fault attribution engine, verifying
exact original CSV column preservation, canonical roles, observed values,
physical engineering units, single-sensor intervals, multi-sensor equipment
participating roles, and fallback behavior.
"""

import pytest
from app.fdd.attribution import resolve_sensor_attributions
from app.fdd.models import FaultEpisode, RuleDefinition


def test_single_sensor_attribution():
    rule_def = RuleDefinition(
        rule_id="FAN-RUNTIME-HOURS",
        sql_file="fan_runtime.sql",
        description="Excessive fan runtime hours",
        required_roles=["fan_status"],
    )
    episode = FaultEpisode(
        episode_id="ep_001",
        start="2026-01-01T00:00:00Z",
        end="2026-01-01T04:00:00Z",
        duration_hours=4.0,
        samples=48,
    )
    col_mappings = {"fan_status": "AHU_SUPPLY_FAN_STATUS_FBK"}
    summary = {"fan_status": {"mean": 1.0}}

    sensors = resolve_sensor_attributions(
        rule_def=rule_def,
        equipment_id="AHU-01",
        episodes=[episode],
        telemetry_summary=summary,
        column_mappings=col_mappings,
        available_roles={"fan_status"},
    )

    assert len(sensors) == 1
    s = sensors[0]
    assert s.canonical_role == "fan_status"
    assert s.original_column == "AHU_SUPPLY_FAN_STATUS_FBK"
    assert s.source_column == "AHU_SUPPLY_FAN_STATUS_FBK"
    assert s.sensor_name == "Supply Fan Status Feedback"
    assert s.interval_available is True
    assert s.fault_start == "2026-01-01T00:00:00Z"
    assert s.fault_end == "2026-01-01T04:00:00Z"
    assert s.duration_hours == 4.0
    assert s.observed_value == 1.0


def test_pair_rule_command_vs_feedback_cmd1():
    rule_def = RuleDefinition(
        rule_id="CMD-1",
        sql_file="cmd1_fan_mismatch.sql",
        description="Fan cmd/status mismatch",
        required_roles=["fan_cmd", "fan_status"],
    )
    episode = FaultEpisode(
        episode_id="ep_001",
        start="2026-01-01T08:00:00Z",
        end="2026-01-01T09:00:00Z",
        duration_hours=1.0,
        samples=12,
    )
    col_mappings = {
        "fan_cmd": "AHU1_FAN_CMD_SIG",
        "fan_status": "AHU1_FAN_RUN_STAT",
    }
    summary = {
        "fan_status": {"mean": 0.0},
        "fan_cmd": {"mean": 1.0},
    }

    sensors = resolve_sensor_attributions(
        rule_def=rule_def,
        equipment_id="AHU-01",
        episodes=[episode],
        telemetry_summary=summary,
        column_mappings=col_mappings,
        available_roles={"fan_cmd", "fan_status"},
    )

    assert len(sensors) == 2
    roles = {s.canonical_role: s for s in sensors}

    # fan_status should be primary mismatch indicator
    assert "fan_status" in roles
    stat_sensor = roles["fan_status"]
    assert stat_sensor.original_column == "AHU1_FAN_RUN_STAT"
    assert stat_sensor.role_type == "primary"
    assert stat_sensor.observed_value == 0.0

    # fan_cmd should be control command
    assert "fan_cmd" in roles
    cmd_sensor = roles["fan_cmd"]
    assert cmd_sensor.original_column == "AHU1_FAN_CMD_SIG"
    assert cmd_sensor.role_type == "control_command"
    assert cmd_sensor.observed_value == 1.0


def test_multi_sensor_equipment_level_fc2():
    rule_def = RuleDefinition(
        rule_id="FC2",
        sql_file="fc2_mixing_energy_balance.sql",
        description="Air handling unit mixed air temperature outside boundaries",
        required_roles=["mat", "oa_t", "rat", "fan_cmd"],
    )
    episode = FaultEpisode(
        episode_id="ep_001",
        start="2026-01-01T12:00:00Z",
        end="2026-01-01T15:00:00Z",
        duration_hours=3.0,
        samples=36,
    )
    col_mappings = {
        "mat": "AHU1_MixedTemp_F",
        "oa_t": "AHU1_OutdoorTemp_F",
        "rat": "AHU1_ReturnTemp_F",
        "fan_cmd": "AHU1_SupplyFan_Cmd",
    }
    summary = {
        "mat": {"mean": 65.0},
        "oa_t": {"mean": 45.0},
        "rat": {"mean": 72.0},
        "fan_cmd": {"mean": 1.0},
    }

    sensors = resolve_sensor_attributions(
        rule_def=rule_def,
        equipment_id="AHU-01",
        episodes=[episode],
        telemetry_summary=summary,
        column_mappings=col_mappings,
        available_roles={"mat", "oa_t", "rat", "fan_cmd"},
    )

    assert len(sensors) >= 3
    # Multi-sensor equipment level faults must declare interval_available = False
    for s in sensors:
        assert s.interval_available is False
        assert "not isolated" in s.interval_note.lower() or "equipment-level" in s.interval_note.lower()

    mat_s = next(s for s in sensors if s.canonical_role == "mat")
    assert mat_s.original_column == "AHU1_MixedTemp_F"
    assert mat_s.observed_value == 65.0
    assert mat_s.unit == "°F"


def test_sensor_validation_stale_isolation():
    rule_def = RuleDefinition(
        rule_id="SV-STALE",
        sql_file="sv_stale.sql",
        description="Sensor stale / flatline condition",
        required_roles=["sat"],
    )
    episode = FaultEpisode(
        episode_id="ep_001",
        start="2026-01-01T00:00:00Z",
        end="2026-01-01T06:00:00Z",
        duration_hours=6.0,
        samples=72,
    )
    col_mappings = {"sat": "Floor1_SAT_F"}
    summary = {"sat": {"mean": 55.0, "std": 0.0}}

    sensors = resolve_sensor_attributions(
        rule_def=rule_def,
        equipment_id="AHU-01",
        episodes=[episode],
        telemetry_summary=summary,
        column_mappings=col_mappings,
        available_roles={"sat"},
    )

    assert len(sensors) == 1
    s = sensors[0]
    assert s.canonical_role == "sat"
    assert s.original_column == "Floor1_SAT_F"
    assert s.interval_available is True
    assert s.duration_hours == 6.0
    assert s.observed_value == 55.0


def test_empty_attribution_fallback():
    rule_def = RuleDefinition(
        rule_id="GENERIC-CUSTOM-RULE",
        sql_file="custom.sql",
        description="Custom rule with no mapped roles",
        required_roles=[],
    )
    sensors = resolve_sensor_attributions(
        rule_def=rule_def,
        equipment_id="AHU-01",
        episodes=[],
        telemetry_summary={},
        column_mappings={},
        available_roles=set(),
    )
    assert len(sensors) == 0
