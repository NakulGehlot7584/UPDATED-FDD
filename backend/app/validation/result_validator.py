"""FDD execution result, evidence, and finding validation engine.

Validates official Open-FDD execution results, finding schema, evidence integrity,
and cross-reconciles rules against findings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set
from pydantic import BaseModel, Field

from app.fdd.catalog import RuleCatalog
from app.fdd.models import (
    FDDExecutionSummary,
    ResultValidationReport,
    RuleExecutionResult,
    RuleExecutionStatus,
)


class ResultValidator:
    """Validates FDD execution results, finding schema, evidence integrity, and reconciliation."""

    def __init__(self, catalog: RuleCatalog):
        self.catalog = catalog
        self.known_rules = {r.rule_id: r for r in catalog.list_rules()}

    def validate_execution(
        self,
        summary: FDDExecutionSummary,
        available_roles: Optional[Sequence[str]] = None,
        equipment_type: str = "AHU",
        dataset_timestamps: Optional[Sequence[str]] = None,
    ) -> ResultValidationReport:
        avail_roles_set = {r.lower() for r in (available_roles or [])}
        rules_table: List[Dict[str, Any]] = []
        findings_table: List[Dict[str, Any]] = []
        reconciliation_table: List[Dict[str, Any]] = []
        issues_summary: List[str] = []

        rules_validated_count = 0
        rules_valid_count = 0
        rules_issue_count = 0

        findings_validated_count = 0
        findings_valid_count = 0
        findings_with_evidence_issues = 0
        duplicate_findings_count = 0
        reconciliation_errors_count = 0

        # Collect all findings across execution results
        all_findings = []
        findings_by_rule: Dict[str, list] = {}

        for r_res in summary.results:
            findings_by_rule[r_res.rule_id] = r_res.findings
            for f in r_res.findings:
                if f.fault_detected:
                    all_findings.append((r_res.rule_id, f))

        # 1. Audit Rule Results
        for r_res in summary.results:
            rules_validated_count += 1
            rule_issues: List[str] = []
            rule_obj = self.known_rules.get(r_res.rule_id)
            rule_name = rule_obj.description if rule_obj else f"Rule {r_res.rule_id}"
            req_roles = rule_obj.required_roles if rule_obj else []

            # Missing roles check
            missing = [r for r in req_roles if r.lower() not in avail_roles_set]

            # Equipment applicability check
            is_applicable = (
                rule_obj is not None
                and (
                    not rule_obj.equipment_kinds
                    or any(
                        k.lower() == equipment_type.lower()
                        for k in rule_obj.equipment_kinds
                    )
                )
            )

            # Check status semantics
            if not is_applicable and r_res.status not in (RuleExecutionStatus.SKIPPED_MISSING_ROLES, "NOT_APPLICABLE"):
                rule_issues.append(f"Rule is not applicable to equipment type '{equipment_type}'")

            if r_res.status == RuleExecutionStatus.SKIPPED_MISSING_ROLES:
                if rule_obj and is_applicable and not missing:
                    rule_issues.append("Status is SKIPPED_MISSING_ROLES but all required canonical roles are present")
            elif r_res.status in (RuleExecutionStatus.FAULT_DETECTED, RuleExecutionStatus.NO_FAULT, RuleExecutionStatus.SUCCESS):
                if missing:
                    rule_issues.append(f"Status is {r_res.status} but missing required roles: {missing}")

            is_valid = len(rule_issues) == 0
            if is_valid:
                rules_valid_count += 1
            else:
                rules_issue_count += 1
                for iss in rule_issues:
                    issues_summary.append(f"[{r_res.rule_id}] {iss}")

            rules_table.append({
                "Rule ID": r_res.rule_id,
                "Rule Name": rule_name,
                "Status": str(r_res.status.value if hasattr(r_res.status, 'value') else r_res.status),
                "Valid": "Yes" if is_valid else "No",
                "Missing Roles": ", ".join(missing) if missing else "None",
                "Issues": " | ".join(rule_issues) if rule_issues else "None",
            })

        # 2. Audit Findings & Evidence Quality
        seen_keys: Set[tuple] = set()

        for rule_id, f in all_findings:
            findings_validated_count += 1
            f_issues: List[str] = []
            eq_id = f.equipment_id or summary.equipment_id or "UNKNOWN"
            sev = (f.severity or "HIGH").upper()
            detail = f.detail

            # Evidence text
            ev_text = ""
            if detail and detail.evidence and len(detail.evidence) > 0:
                ev_text = detail.evidence[0].evidence_text or ""
            elif f.description:
                ev_text = f.description

            if not ev_text or ev_text.lower() in ("none", "nan", "null", ""):
                ev_status = "INVALID"
                f_issues.append("Evidence text is empty or null")
            elif len(ev_text) < 10:
                ev_status = "INCOMPLETE"
                f_issues.append(f"Evidence text is unusually brief: '{ev_text}'")
            else:
                ev_status = "VALID"

            # Check duplicate finding
            dup_key = (eq_id, rule_id)
            is_dup = dup_key in seen_keys
            if is_dup:
                f_issues.append(f"Duplicate finding detected for ({eq_id}, {rule_id})")
                duplicate_findings_count += 1
            seen_keys.add(dup_key)

            if ev_status != "VALID" or f_issues:
                findings_with_evidence_issues += 1
                for iss in f_issues:
                    issues_summary.append(f"[{rule_id}] {iss}")
            else:
                findings_valid_count += 1

            findings_table.append({
                "Timestamp": f.episodes[0].start if f.episodes else (dataset_timestamps[0] if dataset_timestamps else "2026-01-01"),
                "Equipment": eq_id,
                "Fault Code": rule_id,
                "Severity": sev,
                "Persistence": len(f.episodes) if f.episodes else 1,
                "Evidence Status": ev_status,
                "Duplicate": "Yes" if is_dup else "No",
                "Issues": " | ".join(f_issues) if f_issues else "None",
            })

        # 3. Reconcile Results & Findings
        for r_res in summary.results:
            rule_id = r_res.rule_id
            rule_obj = self.known_rules.get(rule_id)
            rule_name = rule_obj.description if rule_obj else rule_id
            f_list = [f for f in r_res.findings if f.fault_detected]
            f_count = len(f_list)

            status_str = str(r_res.status.value if hasattr(r_res.status, 'value') else r_res.status)
            is_fault = (r_res.status == RuleExecutionStatus.FAULT_DETECTED) or (f_count > 0)

            recon_status = "MATCH"
            recon_error: Optional[str] = None

            if is_fault and f_count == 0:
                recon_status = "MISMATCH (Expected Findings)"
                recon_error = f"Rule {rule_id} faulted in engine but produced 0 findings"
            elif not is_fault and f_count > 0:
                recon_status = "MISMATCH (Unexpected Findings)"
                recon_error = f"Rule {rule_id} status is {status_str} but produced {f_count} findings"

            if recon_error:
                reconciliation_errors_count += 1
                issues_summary.append(f"[Reconciliation] {recon_error}")

            reconciliation_table.append({
                "Rule ID": rule_id,
                "Rule Name": rule_name,
                "Official Status": status_str,
                "Dashboard Findings": f_count,
                "Reconciliation": recon_status,
            })

        # Overall Status determination
        if reconciliation_errors_count > 0 or rules_issue_count > 0:
            overall = "INVALID"
        elif findings_with_evidence_issues > 0 or duplicate_findings_count > 0:
            overall = "WARNING"
        else:
            overall = "VALID"

        return ResultValidationReport(
            overall_status=overall,
            rules_validated_count=rules_validated_count,
            rules_valid_count=rules_valid_count,
            rules_issue_count=rules_issue_count,
            findings_validated_count=findings_validated_count,
            findings_valid_count=findings_valid_count,
            findings_with_evidence_issues=findings_with_evidence_issues,
            duplicate_findings_count=duplicate_findings_count,
            reconciliation_errors_count=reconciliation_errors_count,
            issues_summary=issues_summary,
            rules_table=rules_table,
            findings_table=findings_table,
            reconciliation_table=reconciliation_table,
        )
