"""FastAPI route handlers for dynamic graph visualizations and fault timelines."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query, status
import pyarrow.parquet as pq

from app.api.deps import get_dataset_manager
from app.datasets.manager import DatasetManager
from app.fdd.catalog import RuleCatalog, get_rule_catalog
from app.fdd.executor import RuleExecutor, get_executor
from app.fdd.graphs import (
    build_fault_timeline,
    build_rule_graph,
    build_telemetry_graph,
    get_available_graph_categories,
)
from app.fdd.models import (
    AvailableGraphCategory,
    FaultTimelinePayload,
    GraphPayload,
)

router = APIRouter(prefix="/graphs", tags=["graphs"])


def _find_equipment_parquet(storage: Any, equipment_id: str, building_id: Optional[str] = None) -> Tuple[Path, str]:
    """Helper to locate parquet path and resolve building ID."""
    building = building_id
    if building:
        p = storage.get_parquet_path(building, equipment_id)
        if p.exists():
            return p, building
    else:
        for b_dir in storage.root_dir.glob("building=*"):
            b_name = b_dir.name.split("=")[1]
            p = storage.get_parquet_path(b_name, equipment_id)
            if p.exists():
                return p, b_name

    # Fallback search in sidecar metadata
    import json
    for b_dir in storage.root_dir.glob("building=*"):
        b_name = b_dir.name.split("=")[1]
        for eq_dir in b_dir.glob("equipment=*"):
            meta_path = eq_dir / "metadata.json"
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as mf:
                        m = json.load(mf)
                    src_file = str(m.get("source_file", ""))
                    eq_name = str(m.get("equipment_id", eq_dir.name.split("=")[1]))
                    p_file = eq_dir / "history.parquet"
                    if p_file.exists() and (
                        equipment_id.lower() == eq_name.lower()
                        or equipment_id.lower() in src_file.lower()
                        or Path(src_file).stem.lower() == equipment_id.lower()
                        or Path(src_file).name.lower() == equipment_id.lower()
                    ):
                        return p_file, b_name
                except Exception:
                    pass

    raise FileNotFoundError(f"Parquet historian data not found for equipment '{equipment_id}'")


@router.get("/available/{equipment_id}", response_model=List[AvailableGraphCategory])
def get_available_graphs(
    equipment_id: str,
    building_id: Optional[str] = Query(None, description="Optional building ID partition"),
    manager: DatasetManager = Depends(get_dataset_manager),
) -> List[AvailableGraphCategory]:
    """List available graph visualization categories based on uploaded telemetry columns."""
    storage = manager.historian.storage
    try:
        parquet_path, _ = _find_equipment_parquet(storage, equipment_id, building_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    schema = pq.read_schema(parquet_path)
    categories = get_available_graph_categories(schema.names)
    return categories


@router.get("/telemetry/{equipment_id}", response_model=GraphPayload)
def get_telemetry_graph(
    equipment_id: str,
    building_id: Optional[str] = Query(None, description="Optional building ID partition"),
    category: Optional[str] = Query(None, description="Graph category (e.g. temperature_dynamics, airside, hydronic, zone_comfort)"),
    max_points: int = Query(5000, ge=10, le=50000, description="Downsampling point cap"),
    start_utc: Optional[str] = Query(None, description="Optional start time ISO string filter"),
    end_utc: Optional[str] = Query(None, description="Optional end time ISO string filter"),
    manager: DatasetManager = Depends(get_dataset_manager),
) -> GraphPayload:
    """Retrieve multi-axis telemetry timeseries payload for plotting."""
    storage = manager.historian.storage
    try:
        parquet_path, resolved_bldg = _find_equipment_parquet(storage, equipment_id, building_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    try:
        payload = build_telemetry_graph(
            parquet_path=parquet_path,
            equipment_id=equipment_id,
            building_id=resolved_bldg,
            category=category,
            max_points=max_points,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        return payload
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/rule/{equipment_id}/{rule_id}", response_model=GraphPayload)
def get_rule_graph(
    equipment_id: str,
    rule_id: str,
    building_id: Optional[str] = Query(None, description="Optional building ID partition"),
    max_points: int = Query(5000, ge=10, le=50000, description="Downsampling point cap"),
    manager: DatasetManager = Depends(get_dataset_manager),
    catalog: RuleCatalog = Depends(get_rule_catalog),
) -> GraphPayload:
    """Retrieve focused investigation graph payload for a specific rule with shaded fault episodes."""
    storage = manager.historian.storage
    try:
        parquet_path, resolved_bldg = _find_equipment_parquet(storage, equipment_id, building_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    rule_def = catalog.get_rule(rule_id)
    if not rule_def:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule '{rule_id}' not found in catalog")

    executor = get_executor(storage=storage)
    episodes = []
    try:
        summary = executor.execute_rules_for_equipment(
            equipment_id=equipment_id,
            building_id=resolved_bldg,
            rule_ids=[rule_id],
        )
        for res in summary.results:
            for f in res.findings:
                if f.episodes:
                    episodes.extend(f.episodes)
    except Exception:
        episodes = []

    try:
        payload = build_rule_graph(
            parquet_path=parquet_path,
            equipment_id=equipment_id,
            rule_id=rule_def.rule_id,
            rule_def=rule_def,
            episodes=episodes,
            building_id=resolved_bldg,
            max_points=max_points,
        )
        return payload
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/timeline/{equipment_id}", response_model=FaultTimelinePayload)
def get_fault_timeline(
    equipment_id: str,
    building_id: Optional[str] = Query(None, description="Optional building ID partition"),
    rule_ids: Optional[List[str]] = Query(None, description="Optional list of rule IDs"),
    manager: DatasetManager = Depends(get_dataset_manager),
) -> FaultTimelinePayload:
    """Retrieve horizontal fault timeline swimlanes for all active faults on an equipment."""
    storage = manager.historian.storage
    try:
        _, resolved_bldg = _find_equipment_parquet(storage, equipment_id, building_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    executor = get_executor(storage=storage)
    try:
        summary = executor.execute_rules_for_equipment(
            equipment_id=equipment_id,
            building_id=resolved_bldg,
            rule_ids=rule_ids,
        )
        timeline = build_fault_timeline(
            equipment_id=equipment_id,
            rule_results=summary.results,
            building_id=resolved_bldg,
        )
        return timeline
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
