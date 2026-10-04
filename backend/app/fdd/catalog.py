"""Rule Catalog for official Open-FDD SQL rules."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set
import yaml

from app.fdd.models import RuleDefinition, RuleParameterDef


class RuleCatalog:
    """Catalog holding all official Open-FDD SQL rules loaded from registry.yaml."""

    def __init__(self, rules_dir: Optional[Path] = None):
        if rules_dir is None:
            rules_dir = Path(__file__).resolve().parent / "sql_rules"
        self.rules_dir = Path(rules_dir)
        self._rules: Dict[str, RuleDefinition] = {}
        self._alias_map: Dict[str, str] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        manifest_file = self.rules_dir / "registry.yaml"
        if not manifest_file.exists():
            raise FileNotFoundError(f"Open-FDD rule registry not found at {manifest_file}")

        with open(manifest_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        raw_rules = data.get("rules", []) if isinstance(data, dict) else []
        for r in raw_rules:
            rule_id = r["rule_id"]
            aliases = r.get("aliases", []) or []
            sql_file = r.get("sql_file", "")
            description = r.get("description", "")
            required_roles = [str(x).lower() for x in (r.get("required_roles", []) or [])]
            optional_roles = [str(x).lower() for x in (r.get("optional_roles", []) or [])]
            equipment_kinds = [str(x).lower() for x in (r.get("equipment_kinds", []) or [])]
            output_columns = r.get("output_columns", []) or []
            priority = r.get("priority", "P0")
            parity_status = r.get("parity_status", "sql_screening")
            dashboard_wired = bool(r.get("dashboard_wired", False))
            confirm_seconds = int(r.get("confirm_seconds", 300))

            # Parse parameters
            parameters: Dict[str, RuleParameterDef] = {}
            raw_params = r.get("parameters", {}) or {}
            for p_name, p_data in raw_params.items():
                parameters[p_name] = RuleParameterDef(
                    label=p_data.get("label", p_name),
                    default=float(p_data.get("default", 0.0)),
                    min=float(p_data.get("min", 0.0)),
                    max=float(p_data.get("max", 100.0)),
                    step=float(p_data.get("step", 1.0)),
                    unit=p_data.get("unit", ""),
                    frontend_control=p_data.get("frontend_control", "slider"),
                    sql_placeholder=p_data.get("sql_placeholder", p_name.upper()),
                )

            # Read SQL template if available
            sql_template: Optional[str] = None
            if sql_file:
                sql_path = self.rules_dir / sql_file
                if sql_path.exists():
                    try:
                        sql_template = sql_path.read_text(encoding="utf-8")
                    except Exception:
                        sql_template = None

            rule_def = RuleDefinition(
                rule_id=rule_id,
                aliases=aliases,
                sql_file=sql_file,
                description=description,
                required_roles=required_roles,
                optional_roles=optional_roles,
                equipment_kinds=equipment_kinds,
                output_columns=output_columns,
                priority=priority,
                parity_status=parity_status,
                dashboard_wired=dashboard_wired,
                confirm_seconds=confirm_seconds,
                parameters=parameters,
                sql_template=sql_template,
            )

            self._rules[rule_id] = rule_def
            self._alias_map[rule_id.lower()] = rule_id
            for alias in aliases:
                self._alias_map[alias.lower()] = rule_id

    def get_rule(self, identifier: str) -> Optional[RuleDefinition]:
        """Get a rule definition by its rule_id or alias (case-insensitive)."""
        key = identifier.strip().lower()
        canonical_id = self._alias_map.get(key)
        if canonical_id:
            return self._rules.get(canonical_id)
        return None

    def get_rule_sql(self, identifier: str) -> str:
        """Get the SQL template string for a rule."""
        rule = self.get_rule(identifier)
        if not rule:
            raise KeyError(f"Rule '{identifier}' not found in catalog")
        if not rule.sql_template:
            sql_path = self.rules_dir / rule.sql_file
            if sql_path.exists():
                rule.sql_template = sql_path.read_text(encoding="utf-8")
            else:
                raise FileNotFoundError(f"SQL file '{rule.sql_file}' not found for rule {rule.rule_id}")
        return rule.sql_template

    def list_rules(self, equipment_kind: Optional[str] = None) -> List[RuleDefinition]:
        """List all rules, optionally filtered by equipment kind (e.g. 'ahu', 'vav', 'chiller')."""
        if equipment_kind is None:
            return list(self._rules.values())

        kind = equipment_kind.strip().lower()
        matched = []
        for rule in self._rules.values():
            if not rule.equipment_kinds:
                # No equipment filter means rule applies broadly
                matched.append(rule)
            elif any(k.lower() == kind for k in rule.equipment_kinds):
                matched.append(rule)
        return matched

    def get_applicable_rules(
        self,
        available_roles: Set[str],
        equipment_kind: Optional[str] = None,
    ) -> List[RuleDefinition]:
        """Get rules whose required roles are all present in available_roles."""
        normalized_roles = {r.lower().strip() for r in available_roles}
        candidates = self.list_rules(equipment_kind=equipment_kind)
        applicable = []
        for rule in candidates:
            req = set(rule.required_roles)
            if req.issubset(normalized_roles):
                applicable.append(rule)
        return applicable

    def __len__(self) -> int:
        return len(self._rules)


_GLOBAL_CATALOG: Optional[RuleCatalog] = None


def get_rule_catalog() -> RuleCatalog:
    """Get or initialize singleton RuleCatalog."""
    global _GLOBAL_CATALOG
    if _GLOBAL_CATALOG is None:
        _GLOBAL_CATALOG = RuleCatalog()
    return _GLOBAL_CATALOG
