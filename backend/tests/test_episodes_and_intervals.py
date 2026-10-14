"""Test suite for fault episode creation, streak grouping, gap splitting,
duration calculations, and timestamp intervals.
"""

from datetime import datetime, timezone, timedelta
from app.fdd.episodes import extract_fault_episodes
from app.fdd.models import FaultEpisode


def test_single_contiguous_episode():
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    # 6 contiguous samples 5 minutes apart = 30 minutes = 0.5 hours
    timestamps = [base_time + timedelta(minutes=5 * i) for i in range(6)]

    summary, episodes = extract_fault_episodes(timestamps, poll_seconds=300.0)

    assert summary["episode_count"] == 1
    assert summary["sample_count"] == 6
    assert summary["total_fault_hours"] == 0.5
    assert len(episodes) == 1
    assert episodes[0].samples == 6
    assert episodes[0].duration_hours == 0.5
    assert episodes[0].start == timestamps[0].isoformat()
    assert episodes[0].end == timestamps[-1].isoformat()


def test_gap_splitting_into_multiple_episodes():
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    # Streak 1: 3 samples 5 min apart (10:00, 10:05, 10:10)
    streak1 = [base_time + timedelta(minutes=5 * i) for i in range(3)]

    # Gap of 2 hours
    gap_time = base_time + timedelta(hours=2)
    # Streak 2: 4 samples 5 min apart (12:00, 12:05, 12:10, 12:15)
    streak2 = [gap_time + timedelta(minutes=5 * i) for i in range(4)]

    all_ts = streak1 + streak2
    summary, episodes = extract_fault_episodes(all_ts, poll_seconds=300.0)

    assert summary["episode_count"] == 2
    assert summary["sample_count"] == 7
    # 7 samples * 300 / 3600 = 7 * 0.08333 = 0.5833 hours
    assert round(summary["total_fault_hours"], 2) == 0.58
    assert len(episodes) == 2
    assert episodes[0].samples == 3
    assert episodes[1].samples == 4


def test_empty_timestamps_returns_zero_summary():
    summary, episodes = extract_fault_episodes([], poll_seconds=300.0)
    assert summary["episode_count"] == 0
    assert summary["total_fault_hours"] == 0.0
    assert len(episodes) == 0
    assert summary["first_fault_time"] is None


def test_single_isolated_sample_episode():
    single_ts = [datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)]
    summary, episodes = extract_fault_episodes(single_ts, poll_seconds=300.0)

    assert summary["episode_count"] == 1
    assert summary["sample_count"] == 1
    assert len(episodes) == 1
    assert episodes[0].duration_hours == round(300.0 / 3600.0, 4)


def test_fault_episode_sensor_fields():
    """Verify FaultEpisode correctly holds optional sensor attribution fields."""
    ep = FaultEpisode(
        episode_id="AHU-01_mat_001",
        start="2026-01-01T10:00:00Z",
        end="2026-01-01T12:00:00Z",
        samples=24,
        duration_hours=2.0,
        summary="2.00h (24 samples)",
        sensor_name="Mixed Air Temperature",
        canonical_role="mat",
        original_column="AHU1_MixedTemp_F",
    )
    assert ep.sensor_name == "Mixed Air Temperature"
    assert ep.canonical_role == "mat"
    assert ep.original_column == "AHU1_MixedTemp_F"


def test_extract_fault_episodes_with_sensor_info():
    """Verify extract_fault_episodes propagates sensor metadata onto all created episodes."""
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    ts = [base_time + timedelta(minutes=5 * i) for i in range(5)]

    summary, episodes = extract_fault_episodes(
        ts,
        poll_seconds=300.0,
        equipment_prefix="AHU-1_sat",
        sensor_name="Supply Air Temperature",
        canonical_role="sat",
        original_column="AHU1_SAT_F",
    )
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.episode_id == "AHU-1_sat_001"
    assert ep.sensor_name == "Supply Air Temperature"
    assert ep.canonical_role == "sat"
    assert ep.original_column == "AHU1_SAT_F"


def test_sv_flatline_two_sensors_different_intervals():
    """Verify SV-FLATLINE correctly isolates two sensors with different flatline intervals."""
    import io
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    lines = ["timestamp,AHU1_MIXED_AIR_TEMP_F,AHU1_SUPPLY_AIR_TEMP_F,AHU1_OUTDOOR_AIR_TEMP_F,AHU1_FAN_RUN_STATUS"]

    # 50 rows total (5-minute intervals)
    # Fan is energized (1.0)
    # mat: flat at 65.0 for rows 0..20 (21 points = 1.75h), then oscillates rows 21..49
    # sat: oscillates rows 0..24, then flat at 55.0 for rows 25..49 (25 points = 2.08h)
    # oa_t: fluctuates throughout (0..49), never flat
    for i in range(50):
        ts = (base_time + timedelta(minutes=5 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        mat_val = 65.0 if i <= 20 else 60.0 + (i % 5) * 2.0
        sat_val = (50.0 + (i % 4) * 3.0) if i < 25 else 55.0
        oa_val = 40.0 + (i % 7) * 1.5
        lines.append(f"{ts},{mat_val},{sat_val},{oa_val},1.0")

    csv_data = "\n".join(lines) + "\n"

    # Upload dataset
    files = [("files", ("multi_flatline.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv"))]
    upload_res = client.post("/api/datasets/upload", files=files)
    assert upload_res.status_code in (200, 201), upload_res.text
    ds = upload_res.json()["datasets"][0]
    ds_id = ds["dataset_id"]
    eq_id = ds.get("equipment_id") or ds_id

    try:
        # Execute SV-FLATLINE
        exec_res = client.post(f"/api/fdd/execute/{eq_id}", json={"rule_ids": ["SV-FLATLINE"]})
        assert exec_res.status_code == 200, exec_res.text
        results = exec_res.json().get("results", [])
        assert len(results) == 1
        r = results[0]
        assert r["rule_id"] == "SV-FLATLINE"
        assert len(r["findings"]) == 1
        finding = r["findings"][0]
        assert finding["fault_detected"] is True

        episodes = finding.get("episodes", [])
        assert len(episodes) >= 2, f"Expected at least 2 episodes (one per sensor), got {len(episodes)}"

        # Check each sensor's episode
        mat_eps = [e for e in episodes if e.get("canonical_role") == "mat"]
        sat_eps = [e for e in episodes if e.get("canonical_role") == "sat"]
        oat_eps = [e for e in episodes if e.get("canonical_role") == "oa_t"]

        assert len(mat_eps) >= 1, "Expected at least 1 episode for mat"
        assert len(sat_eps) >= 1, "Expected at least 1 episode for sat"
        assert len(oat_eps) == 0, "oa_t was fluctuating and must not have flatline episodes"

        # Verify sensor attributes on mat episode
        mat_ep = mat_eps[0]
        assert mat_ep["sensor_name"] == "Mixed Air Temperature"
        assert mat_ep["canonical_role"] == "mat"
        assert mat_ep["original_column"] == "AHU1_MIXED_AIR_TEMP_F"
        assert "2026-01-01" in mat_ep["start"]

        # Verify sensor attributes on sat episode
        sat_ep = sat_eps[0]
        assert sat_ep["sensor_name"] == "Supply Air Temperature"
        assert sat_ep["canonical_role"] == "sat"
        assert sat_ep["original_column"] == "AHU1_SUPPLY_AIR_TEMP_F"
        assert "2026-01-01" in sat_ep["start"]

        # Timestamps for sat start should be later than mat start
        assert sat_ep["start"] > mat_ep["start"]
    finally:
        client.delete(f"/api/datasets/{ds_id}")


def test_arrow_table_boolean_coercion():
    """Verify DataFusionEngine.register_arrow_table coerces boolean status fields to float64."""
    import pyarrow as pa
    from app.fdd.engine import create_engine

    engine = create_engine()
    data = {"equipment_id": ["AHU_1"], "fan_status": [True], "fan_cmd": [100.0]}
    tbl = pa.Table.from_pydict(data)
    engine.register_arrow_table("test_bool_tbl", tbl)

    # In DataFusion, comparison with numeric threshold should succeed without planning error
    res = engine.query_to_dicts("SELECT CASE WHEN fan_status > 0.05 THEN 1 ELSE 0 END AS on_status FROM test_bool_tbl")
    assert len(res) == 1
    assert res[0]["on_status"] == 1


def test_f2_cmd1_exact_parity():
    """Verify CMD-1 on F2_AHU02_North detects exactly 31 contiguous episodes."""
    import os
    from app.fdd.executor import get_executor

    p_f2 = r"D:\UPDATED-FDD\data\historian\building=DEFAULT_BUILDING\equipment=F2_AHU02_North\history.parquet"
    if not os.path.exists(p_f2):
        return  # Skip if environment does not contain ingested parquet

    executor = get_executor()
    executor.engine.register_parquet_file("history", p_f2)

    res = executor.execute_rule("CMD-1", table_name="history", equipment_filter="F2_AHU02_North")
    assert res.status.name == "FAULT_DETECTED"
    assert len(res.findings) == 1
    f = res.findings[0]
    assert f.fault_detected is True
    assert len(f.episodes) == 31
    assert f.episodes[0].start.startswith("2026-06-30T18:40:00")
    assert f.episodes[-1].end.startswith("2026-07-31T12:30:00")
    assert abs(f.fault_hours - 148.58) < 0.1


def test_f2_fc1_duct_static_units():
    """Verify FC1 detects expected duct static faults on pre-converted in_wc telemetry."""
    import os
    from app.fdd.executor import get_executor

    p_f2 = r"D:\UPDATED-FDD\data\historian\building=DEFAULT_BUILDING\equipment=F2_AHU02_North\history.parquet"
    if not os.path.exists(p_f2):
        return

    executor = get_executor()
    executor.engine.register_parquet_file("history", p_f2)

    res = executor.execute_rule("FC1", table_name="history", equipment_filter="F2_AHU02_North")
    assert res.status.name == "FAULT_DETECTED"
    f = res.findings[0]
    assert f.fault_detected is True
    assert f.episodes[0].start.startswith("2026-06-30T18:45:00")
    assert abs(f.fault_hours - 45.67) < 0.1


def test_f2_ahu_satdev_operational_gate():
    """Verify AHU-SATDEV suppresses alarms during unpowered fan states and requires confirmation."""
    import os
    from app.fdd.executor import get_executor

    p_f2 = r"D:\UPDATED-FDD\data\historian\building=DEFAULT_BUILDING\equipment=F2_AHU02_North\history.parquet"
    if not os.path.exists(p_f2):
        return

    executor = get_executor()
    executor.engine.register_parquet_file("history", p_f2)

    res = executor.execute_rule("AHU-SATDEV", table_name="history", equipment_filter="F2_AHU02_North")
    assert res.status.name == "NO_FAULT"
    f = res.findings[0]
    assert f.fault_detected is False
    assert f.fault_hours == 0.0


def test_f5_missing_fan_status_graceful_handling():
    """Verify equipment lacking fan_status skips CMD-1 and executes AHU-DUCTHI without crashing."""
    import os
    from app.fdd.executor import get_executor

    p_f5 = r"D:\UPDATED-FDD\data\historian\building=DEFAULT_BUILDING\equipment=F5_AHU02_SOUTH_AHU_Month\history.parquet"
    if not os.path.exists(p_f5):
        return

    executor = get_executor()
    executor.engine.register_parquet_file("history", p_f5)

    # CMD-1 requires fan_status -> should skip gracefully
    res_cmd1 = executor.execute_rule("CMD-1", table_name="history", equipment_filter="F5_AHU02_SOUTH_AHU_Month")
    assert res_cmd1.status.name == "SKIPPED_MISSING_ROLES"

    # AHU-DUCTHI has fan_status optional -> executes successfully
    res_ducthi = executor.execute_rule("AHU-DUCTHI", table_name="history", equipment_filter="F5_AHU02_SOUTH_AHU_Month")
    assert res_ducthi.status.name == "FAULT_DETECTED"
    assert res_ducthi.findings[0].fault_detected is True


def test_custom_table_name_execution():
    """Verify RuleExecutor supports non-default table names with optional roles."""
    import os
    from app.fdd.executor import get_executor

    p_f5 = r"D:\UPDATED-FDD\data\historian\building=DEFAULT_BUILDING\equipment=F5_AHU02_SOUTH_AHU_Month\history.parquet"
    if not os.path.exists(p_f5):
        return

    executor = get_executor()
    executor.engine.register_parquet_file("custom_table_f5", p_f5)

    res = executor.execute_rule("AHU-DUCTHI", table_name="custom_table_f5", equipment_filter="F5_AHU02_SOUTH_AHU_Month")
    assert res.status.name == "FAULT_DETECTED"
    assert len(res.findings) == 1
    assert res.findings[0].fault_hours == 1.0


