"""Test suite for fault episode creation, streak grouping, gap splitting,
duration calculations, and timestamp intervals.
"""

from datetime import datetime, timezone, timedelta
from app.fdd.episodes import extract_fault_episodes


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
