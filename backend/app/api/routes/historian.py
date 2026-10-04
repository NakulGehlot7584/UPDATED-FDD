"""
FastAPI route handlers for Open-FDD Historian operations.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.deps import get_dataset_manager
from app.api.schemas import (
    EquipmentSummarySchema,
    HistorianIngestResponse,
    HistorianSummarySchema,
    HistorianTelemetryResponse,
)
from app.datasets.manager import DatasetManager

router = APIRouter(prefix="/historian", tags=["historian"])


@router.get("/summary", response_model=HistorianSummarySchema)
def get_historian_summary(
    manager: DatasetManager = Depends(get_dataset_manager),
) -> HistorianSummarySchema:
    """
    Retrieve global summary metrics and equipment list from the Parquet historian.
    """
    summary = manager.historian.get_summary()
    equip_schemas = [
        EquipmentSummarySchema(
            equipment_id=e.equipment_id,
            building_id=e.building_id,
            row_count=e.row_count,
            min_timestamp=e.min_timestamp,
            max_timestamp=e.max_timestamp,
            telemetry_roles=e.telemetry_roles,
            parquet_file=e.parquet_file,
            file_size_bytes=e.file_size_bytes,
            last_updated=e.last_updated,
        )
        for e in summary.equipment_list
    ]

    return HistorianSummarySchema(
        total_equipment=summary.total_equipment,
        total_rows=summary.total_rows,
        total_bytes=summary.total_bytes,
        buildings=summary.buildings,
        global_min_timestamp=summary.global_min_timestamp,
        global_max_timestamp=summary.global_max_timestamp,
        equipment_list=equip_schemas,
    )


@router.get("/equipment", response_model=list[EquipmentSummarySchema])
def list_historian_equipment(
    manager: DatasetManager = Depends(get_dataset_manager),
) -> list[EquipmentSummarySchema]:
    """
    List all equipment partitions currently stored in the Parquet historian.
    """
    equip_list = manager.historian.list_equipment()
    return [
        EquipmentSummarySchema(
            equipment_id=e.equipment_id,
            building_id=e.building_id,
            row_count=e.row_count,
            min_timestamp=e.min_timestamp,
            max_timestamp=e.max_timestamp,
            telemetry_roles=e.telemetry_roles,
            parquet_file=e.parquet_file,
            file_size_bytes=e.file_size_bytes,
            last_updated=e.last_updated,
        )
        for e in equip_list
    ]


@router.get("/equipment/{equipment_id}", response_model=HistorianTelemetryResponse)
def get_equipment_historical_telemetry(
    equipment_id: str,
    building_id: str = Query("DEFAULT_BUILDING", description="Building ID partition"),
    preview_limit: int = Query(50, ge=1, le=1000, description="Max preview rows to return"),
    start_time: str | None = Query(None, description="ISO timestamp start filter"),
    end_time: str | None = Query(None, description="ISO timestamp end filter"),
    manager: DatasetManager = Depends(get_dataset_manager),
) -> HistorianTelemetryResponse:
    """
    Retrieve historical telemetry records and preview data for a specific equipment partition.
    """
    df = manager.historian.get_telemetry(
        building_id=building_id,
        equipment_id=equipment_id,
        start_time=start_time,
        end_time=end_time,
    )

    if df.is_empty():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No telemetry found in historian for equipment '{equipment_id}' in building '{building_id}'.",
        )

    min_ts = str(df["timestamp_utc"].min()) if "timestamp_utc" in df.columns else None
    max_ts = str(df["timestamp_utc"].max()) if "timestamp_utc" in df.columns else None

    preview_df = df.head(preview_limit)
    preview_rows = preview_df.to_dicts()

    return HistorianTelemetryResponse(
        building_id=building_id,
        equipment_id=equipment_id,
        row_count=df.height,
        column_count=df.width,
        columns=df.columns,
        min_timestamp=min_ts,
        max_timestamp=max_ts,
        preview_rows=preview_rows,
    )


@router.post("/ingest/{dataset_id}", response_model=HistorianIngestResponse)
def ingest_dataset_to_historian(
    dataset_id: str,
    building_id: str = Query("DEFAULT_BUILDING", description="Building ID partition"),
    default_equipment_id: str | None = Query(None, description="Fallback equipment ID"),
    manager: DatasetManager = Depends(get_dataset_manager),
) -> HistorianIngestResponse:
    """
    Ingest a registered dataset into the partitioned Parquet historian.
    """
    if not manager.has_dataset(dataset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID '{dataset_id}' not found.",
        )

    written_meta = manager.ingest_to_historian(
        dataset_id=dataset_id,
        building_id=building_id,
        default_equipment_id=default_equipment_id,
    )

    total_rows = sum(m.row_count for m in written_meta)

    return HistorianIngestResponse(
        dataset_id=dataset_id,
        equipment_written=len(written_meta),
        total_rows=total_rows,
        partitions=[m.to_dict() for m in written_meta],
    )


@router.get("/download/csv")
def download_normalized_csv(
    equipment_id: str | None = Query(None, description="Comma-separated equipment IDs, or omit / 'all' for all equipment"),
    building_id: str = Query("DEFAULT_BUILDING", description="Building ID partition"),
    manager: DatasetManager = Depends(get_dataset_manager),
) -> Response:
    """
    Download normalized telemetry from the historian as a CSV file.
    Reuses the exact canonical Parquet data already generated and stored by the pipeline.
    Preserves equipment_id, timestamps, and all normalized telemetry columns.
    """
    import io
    import polars as pl

    summary = manager.historian.get_summary()
    available_eqs = [e.equipment_id for e in summary.equipment_list if e.building_id == building_id]
    if not available_eqs:
        available_eqs = [e.equipment_id for e in summary.equipment_list]

    selected_eqs: list[str] = []
    if equipment_id and equipment_id.strip() and equipment_id.strip().lower() != "all" and equipment_id.strip() != "all ahus":
        requested = [eq.strip() for eq in equipment_id.split(",") if eq.strip()]
        selected_eqs = [eq for eq in requested if eq in available_eqs]
        if not selected_eqs:
            # Fallback to direct request if equipment exists in historian
            selected_eqs = requested
    else:
        selected_eqs = available_eqs

    if not selected_eqs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No equipment telemetry found in historian for download.",
        )

    dfs: list[pl.DataFrame] = []
    for eq in selected_eqs:
        try:
            df = manager.historian.get_telemetry(building_id=building_id, equipment_id=eq)
            if not df.is_empty():
                dfs.append(df)
        except Exception:
            continue

    if not dfs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No telemetry found for equipment: {', '.join(selected_eqs)}",
        )

    combined_df = pl.concat(dfs, how="diagonal") if len(dfs) > 1 else dfs[0]

    buf = io.BytesIO()
    combined_df.write_csv(buf)
    csv_bytes = buf.getvalue()

    filename = (
        f"{selected_eqs[0]}_normalized.csv"
        if len(selected_eqs) == 1
        else "all_equipment_normalized.csv"
    )

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


@router.delete("/equipment/{equipment_id}")
def delete_historian_equipment(
    equipment_id: str,
    building_id: str = Query("DEFAULT_BUILDING", description="Building ID partition"),
    manager: DatasetManager = Depends(get_dataset_manager),
) -> dict[str, bool]:
    """
    Delete an equipment partition from the historian.
    """
    removed = manager.historian.delete_equipment(building_id, equipment_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Equipment '{equipment_id}' in building '{building_id}' not found in historian.",
        )
    return {"removed": True}


