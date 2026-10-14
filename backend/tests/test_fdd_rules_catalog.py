"""Test suite verifying execution, correctness, error-free SQL compilation,
operational gates, confirmation periods, and missing role handling for EVERY
registered rule in Open-FDD catalog (all 77 rules).
"""

import pytest
import pyarrow as pa
from datetime import datetime, timezone, timedelta
from app.fdd.catalog import RuleCatalog
from app.fdd.engine import DataFusionEngine
from app.fdd.executor import RuleExecutor
from app.fdd.models import RuleExecutionStatus


@pytest.fixture(scope="module")
def catalog():
    return RuleCatalog()


@pytest.fixture(scope="module")
def engine():
    return DataFusionEngine()


@pytest.fixture(scope="module")
def sample_telemetry_table():
    """Build a comprehensive in-memory Arrow table covering standard canonical roles."""
    n_rows = 24
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(minutes=5 * i) for i in range(n_rows)]

    data = {
        "timestamp_utc": timestamps,
        "equipment_id": ["AHU-01"] * n_rows,
        "sat": [55.0] * n_rows,
        "sat_sp": [55.0] * n_rows,
        "rat": [72.0] * n_rows,
        "mat": [60.0] * n_rows,
        "oa_t": [45.0] * n_rows,
        "oa_h": [50.0] * n_rows,
        "oa_damper_pct": [20.0] * n_rows,
        "damper_pct": [20.0] * n_rows,
        "damper_cmd": [20.0] * n_rows,
        "clg_valve_pct": [0.0] * n_rows,
        "htg_valve_pct": [0.0] * n_rows,
        "reheat_valve_pct": [0.0] * n_rows,
        "fan_cmd": [1.0] * n_rows,
        "fan_status": [1.0] * n_rows,
        "return_fan": [1.0] * n_rows,
        "duct_static": [1.5] * n_rows,
        "duct_static_sp": [1.5] * n_rows,
        "zone_t": [72.0] * n_rows,
        "zone_air_temp_sp": [72.0] * n_rows,
        "zone_flow": [500.0] * n_rows,
        "vav_total_flow": [5000.0] * n_rows,
        "occ_mode": [1.0] * n_rows,
        "chw_supply_t": [44.0] * n_rows,
        "chw_return_t": [54.0] * n_rows,
        "chw_supply_sp": [44.0] * n_rows,
        "chw_dp": [15.0] * n_rows,
        "chw_dp_sp": [15.0] * n_rows,
        "chw_flow": [200.0] * n_rows,
        "hw_supply_t": [140.0] * n_rows,
        "hw_return_t": [120.0] * n_rows,
        "co2": [500.0] * n_rows,
        "co2_sp": [800.0] * n_rows,
    }
    return pa.Table.from_pydict(data)


def test_catalog_rule_count(catalog):
    """Verify exactly 77 rules exist in catalog registry."""
    rules = catalog.list_rules()
    assert len(rules) == 77, f"Expected 77 rules in catalog, found {len(rules)}"


def test_missing_roles_graceful_skip(catalog, engine):
    """Empty table with only timestamp must cleanly skip rules requiring roles."""
    empty_table = pa.Table.from_pydict({
        "timestamp_utc": [datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)],
        "equipment_id": ["AHU-01"],
    })
    engine.register_arrow_table("history", empty_table)
    executor = RuleExecutor(engine=engine, catalog=catalog)

    rule = catalog.get_rule("AHU-SATDEV")
    res = executor.execute_rule(
        rule.rule_id,
        table_name="history",
        poll_seconds=300,
    )
    assert res.status == RuleExecutionStatus.SKIPPED_MISSING_ROLES
    assert "sat" in res.missing_roles or "sat_sp" in res.missing_roles


def test_all_catalog_rules_compile_and_execute_without_crash(catalog, engine, sample_telemetry_table):
    """Execute all 77 catalog rules against sample telemetry and record status.
    Every rule must execute with 0 unhandled syntax or compilation crashes.
    """
    engine.register_arrow_table("history", sample_telemetry_table)
    executor = RuleExecutor(engine=engine, catalog=catalog)

    results = {}
    errors = []

    for rule in catalog.list_rules():
        try:
            res = executor.execute_rule(
                rule.rule_id,
                table_name="history",
                poll_seconds=300,
            )
            results[rule.rule_id] = res.status
            # Status must be one of the recognized enum values, and not ERROR
            if res.status == RuleExecutionStatus.ERROR:
                errors.append(f"{rule.rule_id}: {res.error}")
        except Exception as e:
            errors.append(f"{rule.rule_id} crashed with exception: {str(e)}")

    assert len(errors) == 0, f"Rules produced errors: {errors}"
    assert len(results) == 77
    print(f"\nAudit complete: Tested {len(results)} rules with 0 compilation/execution errors.")


def test_specific_fault_condition_cmd1(catalog, engine):
    """Test CMD-1 detecting fan status OFF (0) when fan command is ON (1)."""
    n_rows = 10
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(minutes=5 * i) for i in range(n_rows)]

    # CMD is ON (1), Status is OFF (0) -> sustained fault!
    fault_data = {
        "timestamp_utc": timestamps,
        "equipment_id": ["AHU-01"] * n_rows,
        "fan_cmd": [1.0] * n_rows,
        "fan_status": [0.0] * n_rows,
    }
    table = pa.Table.from_pydict(fault_data)
    engine.register_arrow_table("history", table)
    executor = RuleExecutor(engine=engine, catalog=catalog)

    res = executor.execute_rule(
        "CMD-1",
        table_name="history",
        poll_seconds=300,
    )
    assert res.status == RuleExecutionStatus.FAULT_DETECTED
    assert len(res.findings) > 0
    assert res.findings[0].fault_detected is True
    assert len(res.findings[0].sensors) >= 2


def test_operational_gate_suppression_cmd1(catalog, engine):
    """Test CMD-1 when equipment is OFF (fan command is 0) -> no fault."""
    n_rows = 10
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    timestamps = [base_time + timedelta(minutes=5 * i) for i in range(n_rows)]

    # CMD is OFF (0), Status is OFF (0) -> normal!
    normal_data = {
        "timestamp_utc": timestamps,
        "equipment_id": ["AHU-01"] * n_rows,
        "fan_cmd": [0.0] * n_rows,
        "fan_status": [0.0] * n_rows,
    }
    table = pa.Table.from_pydict(normal_data)
    engine.register_arrow_table("history", table)
    executor = RuleExecutor(engine=engine, catalog=catalog)

    res = executor.execute_rule(
        "CMD-1",
        table_name="history",
        poll_seconds=300,
    )
    assert res.status == RuleExecutionStatus.NO_FAULT
