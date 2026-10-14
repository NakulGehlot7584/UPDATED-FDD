"""Test suite for FastAPI backend endpoints, request/response validation,
HTTP status codes, and error handling.
"""

import io
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"


def test_list_rules_endpoint():
    res = client.get("/api/fdd/rules")
    assert res.status_code == 200
    rules = res.json()
    assert isinstance(rules, list)
    assert len(rules) == 77
    rule_ids = {r["rule_id"] for r in rules}
    assert "CMD-1" in rule_ids
    assert "FC1" in rule_ids
    assert "SV-STALE" in rule_ids


def test_get_rule_details_endpoint():
    res = client.get("/api/fdd/rules/CMD-1")
    assert res.status_code == 200
    detail = res.json()
    assert detail["rule_id"] == "CMD-1"
    assert "fan_cmd" in detail["required_roles"]
    assert "fan_status" in detail["required_roles"]


def test_get_nonexistent_rule_returns_404():
    res = client.get("/api/fdd/rules/NON_EXISTENT_RULE_XYZ")
    assert res.status_code == 404


def test_datasets_list_endpoint():
    res = client.get("/api/datasets")
    assert res.status_code == 200
    data = res.json()
    assert "datasets" in data


def test_nonexistent_equipment_timeline_returns_404():
    res = client.get("/api/graphs/timeline/NON_EXISTENT_EQUIPMENT_XYZ")
    assert res.status_code == 404


def test_nonexistent_equipment_validation_report_returns_404():
    res = client.get("/api/fdd/validation-report/NON_EXISTENT_EQUIPMENT_XYZ")
    assert res.status_code == 404


def test_upload_and_execute_api_workflow():
    """Test full API pipeline: upload dataset, list datasets, execute FDD rules."""
    csv_content = (
        "timestamp,AHU_TEST_SAT,AHU_TEST_RAT,AHU_TEST_FAN_CMD,AHU_TEST_FAN_STAT\n"
        "2026-01-01T00:00:00Z,55.0,72.0,1,1\n"
        "2026-01-01T00:05:00Z,55.2,72.1,1,1\n"
        "2026-01-01T00:10:00Z,55.1,72.0,1,1\n"
    )
    files = [("files", ("test_api_ahu.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv"))]

    upload_res = client.post("/api/datasets/upload", files=files)
    assert upload_res.status_code in (200, 201)
    upload_data = upload_res.json()
    datasets = upload_data.get("datasets", [])
    assert len(datasets) > 0
    ds_id = datasets[0]["dataset_id"]

    try:
        # Check dataset columns
        col_res = client.get(f"/api/datasets/{ds_id}/columns")
        assert col_res.status_code == 200

        eq_id = datasets[0].get("equipment_id") or datasets[0]["dataset_id"]
        # Execute rules for equipment
        exec_res = client.post(f"/api/fdd/execute/{eq_id}", json={})
        assert exec_res.status_code == 200
        summary = exec_res.json()
        assert "results" in summary
        assert summary["total_rules_evaluated"] >= 0
    finally:
        # Clean up uploaded dataset
        client.delete(f"/api/datasets/{ds_id}")
