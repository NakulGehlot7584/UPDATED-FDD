"""FastAPI route handlers for FDD Rule Engine operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_dataset_manager
from app.datasets.manager import DatasetManager
from app.fdd.catalog import RuleCatalog, get_rule_catalog
from app.fdd.executor import RuleExecutor, get_executor
from app.fdd.models import (
    ExecuteRuleRequest,
    FDDExecutionSummary,
    FaultDetailRecord,
    FaultSummaryItem,
    RuleDefinition,
    RuleExecutionResult,
    RuleExecutionStatus,
    ResultValidationReport,
)
from app.fdd.thresholds import ThresholdCatalogResponse, get_threshold_catalog
from app.validation.result_validator import ResultValidator

router = APIRouter(prefix="/fdd", tags=["fdd"])


@router.get("/threshold-metadata", response_model=ThresholdCatalogResponse)
def get_threshold_metadata() -> ThresholdCatalogResponse:
    """Retrieve dynamic threshold catalog metadata, categories, tiers, and presets."""
    return get_threshold_catalog()


@router.get("/rules", response_model=List[RuleDefinition])
def list_rules(
    equipment_kind: Optional[str] = Query(None, description="Filter rules by equipment kind (e.g. ahu, vav, chiller)"),
    catalog: RuleCatalog = Depends(get_rule_catalog),
) -> List[RuleDefinition]:
    """List all official Open-FDD rules available in the catalog."""
    return catalog.list_rules(equipment_kind=equipment_kind)


@router.get("/rules/{rule_id}", response_model=RuleDefinition)
def get_rule_details(
    rule_id: str,
    catalog: RuleCatalog = Depends(get_rule_catalog),
) -> RuleDefinition:
    """Retrieve metadata, parameters, and SQL template for a specific rule."""
    rule = catalog.get_rule(rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{rule_id}' not found in catalog",
        )
    return rule


@router.post("/execute/{equipment_id}", response_model=FDDExecutionSummary)
def execute_rules_for_equipment(
    equipment_id: str,
    building_id: Optional[str] = Query(None, description="Optional building ID partition"),
    equipment_kind: Optional[str] = Query(None, description="Optional equipment kind override (e.g. 'ahu', 'vav', 'chiller')"),
    payload: Optional[ExecuteRuleRequest] = None,
    manager: DatasetManager = Depends(get_dataset_manager),
) -> FDDExecutionSummary:
    """Execute FDD rules against an equipment Parquet partition in the Historian."""
    executor = get_executor(storage=manager.historian.storage)
    
    rule_ids = payload.rule_ids if payload else None
    overrides = payload.parameter_overrides if payload else None
    poll_sec = payload.poll_seconds if payload else None
    bldg = (payload.building_id if payload and payload.building_id else building_id)
    kind = (payload.equipment_kind if payload and payload.equipment_kind else equipment_kind)

    try:
        summary = executor.execute_rules_for_equipment(
            equipment_id=equipment_id,
            building_id=bldg,
            equipment_kind=kind,
            rule_ids=rule_ids,
            parameter_overrides=overrides,
            poll_seconds=poll_sec,
        )
        return summary
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/execute-all", response_model=List[FDDExecutionSummary])
def execute_all_equipment(
    building_id: Optional[str] = Query(None, description="Optional building ID to restrict execution"),
    payload: Optional[ExecuteRuleRequest] = None,
    manager: DatasetManager = Depends(get_dataset_manager),
) -> List[FDDExecutionSummary]:
    """Execute rules across all equipment partitions stored in the Historian."""
    executor = get_executor(storage=manager.historian.storage)
    summary_data = manager.historian.get_summary()

    rule_ids = payload.rule_ids if payload else None
    overrides = payload.parameter_overrides if payload else None
    poll_sec = payload.poll_seconds if payload else None
    kind = (payload.equipment_kind if payload and payload.equipment_kind else None)

    summaries: List[FDDExecutionSummary] = []
    for eq in summary_data.equipment_list:
        if building_id and eq.building_id != building_id:
            continue
        try:
            res = executor.execute_rules_for_equipment(
                equipment_id=eq.equipment_id,
                building_id=eq.building_id,
                equipment_kind=kind,
                rule_ids=rule_ids,
                parameter_overrides=overrides,
                poll_seconds=poll_sec,
            )
            summaries.append(res)
        except Exception as e:
            # Continue running other equipment even if one fails
            summaries.append(
                FDDExecutionSummary(
                    building_id=eq.building_id,
                    equipment_id=eq.equipment_id,
                    total_rules_evaluated=0,
                    rules_failed=1,
                    results=[
                        RuleExecutionResult(
                            rule_id="EXECUTION_ERROR",
                            status=RuleExecutionStatus.ERROR,
                            error=str(e),
                        )
                    ],
                )
            )

    return summaries


@router.get("/faults/{equipment_id}", response_model=List[FaultDetailRecord])
def get_equipment_faults(
    equipment_id: str,
    building_id: Optional[str] = Query(None, description="Optional building ID partition"),
    rule_ids: Optional[List[str]] = Query(None, description="Optional filter of rule IDs to evaluate"),
    manager: DatasetManager = Depends(get_dataset_manager),
) -> List[FaultDetailRecord]:
    """Retrieve all detected faults with episodes, diagnostic evidence, causes, and checks for an equipment."""
    executor = get_executor(storage=manager.historian.storage)
    try:
        summary = executor.execute_rules_for_equipment(
            equipment_id=equipment_id,
            building_id=building_id,
            rule_ids=rule_ids,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    records: List[FaultDetailRecord] = []
    for res in summary.results:
        for f in res.findings:
            if f.fault_detected and f.detail:
                records.append(f.detail)

    # Sort by severity then fault duration
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    records.sort(key=lambda r: (sev_order.get(r.severity, 99), -r.total_fault_hours))
    return records


@router.get("/faults/{equipment_id}/{rule_id}", response_model=FaultDetailRecord)
def get_equipment_rule_fault(
    equipment_id: str,
    rule_id: str,
    building_id: Optional[str] = Query(None, description="Optional building ID partition"),
    manager: DatasetManager = Depends(get_dataset_manager),
    catalog: RuleCatalog = Depends(get_rule_catalog),
) -> FaultDetailRecord:
    """Retrieve detailed diagnostic record for a specific rule and equipment."""
    rule_def = catalog.get_rule(rule_id)
    if not rule_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{rule_id}' not found in catalog",
        )

    executor = get_executor(storage=manager.historian.storage)
    try:
        summary = executor.execute_rules_for_equipment(
            equipment_id=equipment_id,
            building_id=building_id,
            rule_ids=[rule_id],
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    for res in summary.results:
        for f in res.findings:
            if f.rule_id.lower() == rule_id.lower() or f.rule_id.lower() == rule_def.rule_id.lower():
                if f.detail:
                    return f.detail

    # If no fault detected, return diagnostic record indicating no fault
    from app.fdd.diagnostics import build_grounded_diagnostic
    return build_grounded_diagnostic(
        rule_id=rule_def.rule_id,
        equipment_id=equipment_id,
        building_id=building_id,
        metrics={"fault_hours": 0.0},
        episodes=[],
        rule_def=rule_def,
    )


@router.get("/validation-report/{equipment_id}", response_model=ResultValidationReport)
def get_validation_report(
    equipment_id: str,
    building_id: Optional[str] = Query(None, description="Optional building ID partition"),
    manager: DatasetManager = Depends(get_dataset_manager),
    catalog: RuleCatalog = Depends(get_rule_catalog),
) -> ResultValidationReport:
    """Audit rule execution results, finding schema, evidence integrity, and reconciliation."""
    storage = manager.historian.storage
    executor = get_executor(storage=storage)

    # Determine building and equipment kind
    bldg = building_id or "DEFAULT_BUILDING"
    meta_path = storage.get_meta_path(bldg, equipment_id)
    kind = "AHU"
    if meta_path.exists():
        import json
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                kind = meta.get("equipment_kind", "AHU")
        except Exception:
            kind = "AHU"

    try:
        summary = executor.execute_rules_for_equipment(
            equipment_id=equipment_id,
            building_id=building_id,
            equipment_kind=kind,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    # Get available roles from parquet
    try:
        p = storage.get_parquet_path(bldg, equipment_id)
        import pyarrow.parquet as pq
        schema = pq.read_schema(p)
        available_roles = schema.names
    except Exception:
        available_roles = []

    validator = ResultValidator(catalog=catalog)
    return validator.validate_execution(
        summary=summary,
        available_roles=available_roles,
        equipment_type=kind,
    )


