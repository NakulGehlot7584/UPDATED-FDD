"""Fault Episode Segmentation Engine for Open-FDD.

Groups contiguous fault sample timestamps into discrete episodes based on
polling intervals and gap thresholds, producing standardized FaultEpisode records.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd

from app.fdd.models import FaultEpisode


def parse_timestamp(ts: Union[datetime, pd.Timestamp, str, int, float]) -> datetime:
    """Parse various timestamp representations into timezone-aware or UTC datetime."""
    if isinstance(ts, pd.Timestamp):
        return ts.to_pydatetime()
    if isinstance(ts, datetime):
        return ts
    return pd.to_datetime(ts, utc=True).to_pydatetime()


def extract_fault_episodes(
    timestamps: Sequence[Union[datetime, pd.Timestamp, str, int, float]],
    poll_seconds: float = 300.0,
    equipment_prefix: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[FaultEpisode]]:
    """Segment an array of fault timestamps into contiguous FaultEpisodes.

    Parameters
    ----------
    timestamps : Sequence
        Sequence of timestamps where fault condition was active.
    poll_seconds : float
        Sampling interval in seconds (default: 300.0 = 5 min).
    equipment_prefix : Optional[str]
        Optional prefix for episode IDs.

    Returns
    -------
    Tuple[Dict[str, Any], List[FaultEpisode]]
        Summary dictionary with overall metrics and list of FaultEpisodes.
    """
    if not timestamps:
        return {
            "total_fault_hours": 0.0,
            "episode_count": 0,
            "sample_count": 0,
            "first_fault_time": None,
            "last_fault_time": None,
        }, []

    # Parse and sort timestamps
    parsed = [parse_timestamp(t) for t in timestamps]
    sorted_ts = sorted(parsed)

    # Gap threshold: max(poll_seconds * 2.5, 600.0)
    gap_threshold_sec = max(poll_seconds * 2.5, 600.0)

    episodes: List[FaultEpisode] = []
    curr_samples: List[datetime] = [sorted_ts[0]]

    for i in range(1, len(sorted_ts)):
        prev = sorted_ts[i - 1]
        curr = sorted_ts[i]
        diff_sec = (curr - prev).total_seconds()

        if diff_sec <= gap_threshold_sec:
            curr_samples.append(curr)
        else:
            # Finalize previous episode
            ep = _create_episode(curr_samples, poll_seconds, len(episodes) + 1, equipment_prefix)
            episodes.append(ep)
            curr_samples = [curr]

    if curr_samples:
        ep = _create_episode(curr_samples, poll_seconds, len(episodes) + 1, equipment_prefix)
        episodes.append(ep)

    total_fault_hours = round(sum(e.duration_hours for e in episodes), 4)
    total_samples = sum(e.samples for e in episodes)
    first_time = episodes[0].start if episodes else None
    last_time = episodes[-1].end if episodes else None

    summary = {
        "total_fault_hours": total_fault_hours,
        "episode_count": len(episodes),
        "sample_count": total_samples,
        "first_fault_time": first_time,
        "last_fault_time": last_time,
    }

    return summary, episodes


def _create_episode(
    samples: List[datetime],
    poll_seconds: float,
    index: int,
    equipment_prefix: Optional[str] = None,
) -> FaultEpisode:
    """Create a single FaultEpisode record from a list of contiguous samples."""
    start_dt = samples[0]
    end_dt = samples[-1]
    count = len(samples)

    # In Open-FDD discrete sample calculation: count * poll_seconds / 3600.0
    duration_hours = round(count * poll_seconds / 3600.0, 4)

    start_str = start_dt.isoformat()
    end_str = end_dt.isoformat()

    prefix = f"{equipment_prefix}_" if equipment_prefix else "ep_"
    episode_id = f"{prefix}{index:03d}"

    summary = f"{duration_hours:.2f}h ({count} samples)"

    return FaultEpisode(
        episode_id=episode_id,
        start=start_str,
        end=end_str,
        samples=count,
        duration_hours=duration_hours,
        summary=summary,
    )
