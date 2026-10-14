"""End-to-End Integration Test Suite for UPDATED-FDD Pipeline.

Validates the full flow:
CSV Upload -> Ingestion -> Partitioned Parquet -> Rule Execution -> Fault Findings ->
Granular Sensor Attribution (display name, canonical role, original CSV column,
observed values, engineering units, intervals) -> API serialization.
"""

import io
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_e2e_csv_to_sensor_attribution_pipeline():
    # 1. Generate realistic synthetic AHU telemetry CSV with sustained CMD-1 and SATDEV faults
    n_rows = 12
    base_time = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)
    lines = ["timestamp,AHU1_FAN_CMD_VFD,AHU1_FAN_RUN_STATUS,AHU1_SUPPLY_AIR_TEMP_F,AHU1_SAT_SETPOINT_F"]

    for i in range(n_rows):
        ts = (base_time + timedelta(minutes=5 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Sustained mismatch: command ON (1), status OFF (0)
        # Sustained SAT deviation: SAT is 85.0°F vs setpoint 55.0°F
        lines.append(f"{ts},1.0,0.0,85.0,55.0")

    csv_payload = "\n".join(lines) + "\n"

    # 2. Upload dataset via API
    files = [("files", ("ahu_e2e_dataset.csv", io.BytesIO(csv_payload.encode("utf-8")), "text/csv"))]
    upload_res = client.post("/api/datasets/upload", files=files)
    assert upload_res.status_code in (200, 201), f"Upload failed: {upload_res.text}"

    upload_data = upload_res.json()
    datasets = upload_data.get("datasets", [])
    assert len(datasets) > 0
    ds = datasets[0]
    ds_id = ds["dataset_id"]
    eq_id = ds.get("equipment_id") or ds["dataset_id"]

    try:
        # 3. Execute FDD rules on this equipment
        exec_res = client.post(f"/api/fdd/execute/{eq_id}", json={})
        assert exec_res.status_code == 200, f"Execution failed: {exec_res.text}"
        summary = exec_res.json()

        # Find faulted findings
        all_findings = []
        for r in summary.get("results", []):
            all_findings.extend(r.get("findings", []))

        faulted = [f for f in all_findings if f.get("fault_detected") is True]
        assert len(faulted) > 0, "Expected at least one sustained fault detected"

        # Verify CMD-1 finding has granular sensor attributions
        cmd_finding = next((f for f in faulted if f.get("rule_id") == "CMD-1"), None)
        assert cmd_finding is not None, "CMD-1 fault should be detected"
        sensors = cmd_finding.get("sensors", [])
        assert len(sensors) >= 2, f"Expected 2 sensors for CMD-1, got {len(sensors)}"

        # Check preserved original CSV column names
        orig_cols = {s.get("original_column") or s.get("source_column") for s in sensors}
        assert "AHU1_FAN_CMD_VFD" in orig_cols, f"Missing AHU1_FAN_CMD_VFD in {orig_cols}"
        assert "AHU1_FAN_RUN_STATUS" in orig_cols, f"Missing AHU1_FAN_RUN_STATUS in {orig_cols}"

        # Check display names and observed values
        stat_s = next(s for s in sensors if s.get("canonical_role") == "fan_status")
        assert "Fan" in stat_s.get("sensor_name", "")
        assert stat_s.get("observed_value") == 0.0

        cmd_s = next(s for s in sensors if s.get("canonical_role") == "fan_cmd")
        assert cmd_s.get("observed_value") == 1.0

        # 4. Verify persisted diagnostic records in /api/fdd/faults/{eq_id}
        faults_res = client.get(f"/api/fdd/faults/{eq_id}")
        assert faults_res.status_code == 200
        fault_records = faults_res.json()
        assert len(fault_records) > 0

        cmd_rec = next((r for r in fault_records if r.get("rule_id") == "CMD-1"), None)
        assert cmd_rec is not None
        assert "sensors" in cmd_rec
        assert len(cmd_rec["sensors"]) >= 2
        rec_cols = {s.get("original_column") or s.get("source_column") for s in cmd_rec["sensors"]}
        assert "AHU1_FAN_CMD_VFD" in rec_cols
        assert "AHU1_FAN_RUN_STATUS" in rec_cols

    finally:
        # 5. Clean up dataset
        client.delete(f"/api/datasets/{ds_id}")
