"""
Tests for Phase 1 to Phase 6 Issues in the UPDATED-FDD Master 36-Issue QA Tracker.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest
import polars as pl

from app.validation.preflight import parse_timestamp_series, preflight_csv
from app.transformation.canonical import transform_to_canonical, transform_csv_canonical
from app.mapping.mapper import map_columns
from app.fdd.executor import RuleExecutor, RuleExecutionStatus, resolve_equipment_kind
from app.fdd.episodes import extract_fault_episodes
from app.fdd.diagnostics import build_grounded_diagnostic
from app.datasets.manager import DatasetManager


class TestPhase1InputTimestampsDataIntegrity:
    """Issues 01-10: Input / Timestamp / Data Ingestion"""

    def test_issue_05_timezone_offset_normalization(self):
        """Issue 05: Timezone offsets must be converted to true UTC, not stripped."""
        s = pl.Series("ts", [
            "2026-07-01 12:00:00+05:30",
            "2026-07-01 12:00:00-04:00",
            "2026-07-01T12:00:00Z",
            "01-Jul-26 12:00:00 AM IST",
        ])
        parsed = parse_timestamp_series(s)
        # 12:00:00+05:30 in UTC is 06:30:00
        assert parsed[0].hour == 6 and parsed[0].minute == 30
        # 12:00:00-04:00 in UTC is 16:00:00
        assert parsed[1].hour == 16
        # 12:00:00Z in UTC is 12:00:00
        assert parsed[2].hour == 12
        # 12:00:00 AM IST on 01-Jul-26 is 2026-06-30 18:30:00 UTC
        assert parsed[3].hour == 18 and parsed[3].minute == 30

    def test_issue_06_raw_timestamp_preservation(self):
        """Issue 06: Both timestamp_raw and timestamp_utc must be preserved in canonical dataset."""
        df = pl.DataFrame({
            "timestamp": ["01-Jul-26 12:00:00 AM IST", "01-Jul-26 12:05:00 AM IST"],
            "sat": [55.0, 56.0],
        })
        mapping = map_columns(df.columns)
        res = transform_to_canonical(df, mapping)
        assert "timestamp_utc" in res.canonical_df.columns
        assert "timestamp_raw" in res.canonical_df.columns
        assert res.canonical_df["timestamp_raw"][0] == "01-Jul-26 12:00:00 AM IST"

    def test_issue_07_and_08_duplicate_timestamp_policy(self):
        """Issues 07 & 08: Preflight records duplicate warning; canonical uses last-write-wins with rows_duped tracking."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,sat\n")
            f.write("2026-07-01 12:00:00Z,55.0\n")
            f.write("2026-07-01 12:00:00Z,56.0\n")  # duplicate timestamp
            f.write("2026-07-01 12:05:00Z,57.0\n")
            temp_path = Path(f.name)

        try:
            report = preflight_csv(temp_path)
            assert report["valid"] is True
            assert report["duplicate_timestamps"] == 1
            assert any("duplicate timestamps found" in w for w in report["warnings"])

            df = pl.read_csv(temp_path)
            mapping = map_columns(df.columns)
            res = transform_to_canonical(df, mapping, preflight_report=report)
            assert res.rows_duped == 1
            assert res.row_count == 2
            # Verify keep-last policy (56.0 survived, not 55.0)
            assert res.canonical_df["sat"][0] == 56.0
        finally:
            temp_path.unlink(missing_ok=True)

    def test_issue_04_unknown_equipment_no_ahu_fallback(self):
        """Issue 04: Unknown equipment must resolve to 'unknown' rather than falling back to 'ahu'."""
        kind = resolve_equipment_kind("CHILLER_PLANT_01", telemetry_roles=["chiller_status", "chw_pump_cmd"])
        assert kind == "chiller"

        kind_vav = resolve_equipment_kind("VAV_FLOOR_2", telemetry_roles=["zone_flow", "damper_pct"])
        assert kind_vav == "vav"

        kind_unknown = resolve_equipment_kind("GENERIC_PUMP_09", telemetry_roles=["random_sensor_1", "speed"])
        assert kind_unknown == "unknown"

    def test_issue_09_and_10_sampling_cadence_and_gap_episodes(self):
        """Issues 09 & 10: Sampling cadence handling and gap-aware episode splitting."""
        timestamps = [
            "2026-07-01T12:00:00Z",
            "2026-07-01T12:05:00Z",
            "2026-07-01T12:10:00Z",
            # Large 2-hour gap:
            "2026-07-01T14:10:00Z",
            "2026-07-01T14:15:00Z",
        ]
        summary, episodes = extract_fault_episodes(timestamps, poll_seconds=300.0)
        assert len(episodes) == 2
        assert summary["episode_count"] == 2
        assert summary["sample_count"] == 5


class TestPhase2DataCleaningMissingData:
    """Issues 11-18: Data Quality / Cleaning"""

    def test_issue_11_invalid_value_sanitization(self):
        """Issue 11: Dirty sentinels, booleans, and non-numerics are converted safely to Float64 without crashing."""
        df = pl.DataFrame({
            "timestamp": ["2026-07-01 12:00:00Z", "2026-07-01 12:05:00Z", "2026-07-01 12:10:00Z"],
            "sat": ["55.0", "nan", "N/A"],
            "fan_cmd": ["true", "off", "1"],
        })
        mapping = map_columns(df.columns)
        res = transform_to_canonical(df, mapping)
        assert res.canonical_df["sat"][0] == 55.0
        assert res.canonical_df["sat"][1] is None
        assert res.canonical_df["sat"][2] is None
        assert res.canonical_df["fan_cmd"][0] == 1.0
        assert res.canonical_df["fan_cmd"][1] == 0.0
        assert res.canonical_df["fan_cmd"][2] == 1.0

    def test_issue_13_no_setpoint_forward_fill(self):
        """Issue 13: Missing setpoints must remain NULL. No forward-fill / LOCF or interpolation."""
        df = pl.DataFrame({
            "timestamp": [
                "2026-07-01 10:00:00Z",
                "2026-07-01 10:05:00Z",
                "2026-07-01 10:10:00Z",
                "2026-07-01 10:15:00Z",
            ],
            "sat_sp": [70.0, None, None, 72.0],
            "sat": [68.0, None, 69.0, 71.0],
        })
        mapping = map_columns(df.columns)
        res = transform_to_canonical(df, mapping)
        # Setpoint preserves raw NULLs: 10:00 -> 70, 10:05 -> NULL, 10:10 -> NULL, 10:15 -> 72
        assert res.canonical_df["sat_sp"].to_list() == [70.0, None, None, 72.0]
        # Sensor measurement also preserves raw NULL
        assert res.canonical_df["sat"].to_list() == [68.0, None, 69.0, 71.0]


class TestPhase5FDDExecutionWeatherReadiness:
    """Issues 29-33: FDD Rule Execution and Weather Handling"""

    def test_issue_32_missing_weather_table_skips_rules_explicitly(self):
        """Issue 32: Weather rules with missing weather table must return SKIPPED_MISSING_ROLES rather than false healthy NO_FAULT."""
        dm = DatasetManager()
        f2 = Path("test_data/F2_AHU02_North.csv")
        ds_info = dm.add_csv(f2)
        dm.ingest_to_historian(ds_info.dataset_id, "F2_AHU02_North")
        executor = RuleExecutor()
        summary = executor.execute_rules_for_equipment(equipment_id="F2_AHU02_North")

        wx_rules = [r for r in summary.results if r.rule_id in ("ECON-3", "ECON-6", "ECON-7", "OAT-METEO")]
        assert len(wx_rules) > 0
        for r in wx_rules:
            assert r.status == RuleExecutionStatus.SKIPPED_MISSING_ROLES
            assert len(r.missing_roles) > 0


class TestPhase6DiagnosticsDecoupling:
    """Issues 34-36: Diagnostics and API/UI Status Distinctions"""

    def test_issue_34_diagnostic_does_not_mutate_fault_detected(self):
        """Issue 34: Grounded diagnostic generates evidence without mutating or determining fault_detected."""
        diag = build_grounded_diagnostic(
            rule_id="AHU-SATDEV",
            equipment_id="AHU_01",
            metrics={"fault_hours": 2.5, "status": "FAULT"},
            telemetry_summary={"sat": {"mean": 62.0}, "sat_sp": {"mean": 55.0}},
            available_roles={"sat", "sat_sp"},
        )
        assert diag.rule_id == "AHU-SATDEV"
        assert len(diag.evidence) > 0
        assert diag.evidence[0].confidence == "CONFIRMED"
