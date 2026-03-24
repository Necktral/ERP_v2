from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enums import DatasetStatus, FreshnessMode, MaterializationPolicy, ScopeLevel
from .exceptions import DatasetNotFoundError


@dataclass(frozen=True)
class DatasetSpec:
    dataset_key: str
    title: str
    description: str
    domain_owner: str
    scope_level: str
    kernel_permissions: tuple[str, ...]
    domain_permissions: tuple[str, ...]
    filters_schema: dict[str, dict[str, Any]]
    dimensions: list[str]
    measures: list[str]
    grain: str
    freshness_mode: str
    materialization_policy: str
    export_capabilities: list[str]
    render_hints: dict[str, Any]
    schema_version: str = "1.0.0"
    semantic_version: str = "1.0.0"
    status: str = DatasetStatus.CERTIFIED
    is_certified: bool = True
    is_enabled: bool = True

    @property
    def required_permissions(self) -> list[str]:
        return list(self.kernel_permissions + self.domain_permissions)


_DATE_RANGE_FILTERS = {
    "year": {"type": "int", "required": False},
    "month": {"type": "int", "required": False},
    "date_from": {"type": "date", "required": False},
    "date_to": {"type": "date", "required": False},
}


DATASET_REGISTRY: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        dataset_key="accounting.trial_balance.period",
        title="Trial Balance",
        description="Balance de comprobación por período.",
        domain_owner="ACCOUNTING",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("accounting.report.read",),
        filters_schema=dict(_DATE_RANGE_FILTERS),
        dimensions=["account_code", "account_name", "account_type"],
        measures=["debit_total", "credit_total", "net_balance"],
        grain="account",
        freshness_mode=FreshnessMode.SNAPSHOT_REQUIRED,
        materialization_policy=MaterializationPolicy.SNAPSHOT_REQUIRED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "table", "numeric_format": "currency"},
    ),
    DatasetSpec(
        dataset_key="accounting.general_ledger.transaction",
        title="General Ledger",
        description="Mayor general por transacción y cuenta.",
        domain_owner="ACCOUNTING",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("accounting.report.read",),
        filters_schema={
            **_DATE_RANGE_FILTERS,
            "account_code": {"type": "str", "required": True},
        },
        dimensions=["journal_entry_id", "entry_date", "line_no", "account_code"],
        measures=["amount_tx", "debit_base", "credit_base"],
        grain="journal_entry_line",
        freshness_mode=FreshnessMode.SNAPSHOT_REQUIRED,
        materialization_policy=MaterializationPolicy.SNAPSHOT_REQUIRED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "table", "sort": ["entry_date", "line_no"]},
    ),
    DatasetSpec(
        dataset_key="accounting.pnl.period",
        title="Profit & Loss",
        description="Estado de resultados para un período.",
        domain_owner="ACCOUNTING",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("accounting.report.read",),
        filters_schema=dict(_DATE_RANGE_FILTERS),
        dimensions=["account_code", "account_name", "account_type"],
        measures=["debit_total", "credit_total", "balance"],
        grain="account",
        freshness_mode=FreshnessMode.SNAPSHOT_REQUIRED,
        materialization_policy=MaterializationPolicy.SNAPSHOT_REQUIRED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "waterfall", "numeric_format": "currency"},
    ),
    DatasetSpec(
        dataset_key="accounting.balance_sheet.as_of",
        title="Balance Sheet",
        description="Balance general a una fecha de corte.",
        domain_owner="ACCOUNTING",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("accounting.report.read",),
        filters_schema={
            "year": {"type": "int", "required": False},
            "month": {"type": "int", "required": False},
            "date_to": {"type": "date", "required": False},
            "as_of": {"type": "date", "required": False},
        },
        dimensions=["section", "account_code", "account_name"],
        measures=["debit_total", "credit_total", "balance"],
        grain="account",
        freshness_mode=FreshnessMode.SNAPSHOT_REQUIRED,
        materialization_policy=MaterializationPolicy.SNAPSHOT_REQUIRED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "table", "group_by": ["section"]},
    ),
    DatasetSpec(
        dataset_key="accounting.operational_reconciliation.period",
        title="Operational Reconciliation",
        description="Conciliación operativa contra proyección contable.",
        domain_owner="ACCOUNTING",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("accounting.report.read",),
        filters_schema={
            "date_from": {"type": "date", "required": False},
            "date_to": {"type": "date", "required": False},
        },
        dimensions=["source_module", "event_type"],
        measures=[
            "operational_count",
            "linked_count",
            "posted_count",
            "draft_exception_count",
            "operational_amount",
            "draft_amount",
            "posted_amount",
        ],
        grain="event_type",
        freshness_mode=FreshnessMode.CACHE_ALLOWED,
        materialization_policy=MaterializationPolicy.CACHE_ALLOWED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "table", "highlight": ["pending_operational_events"]},
    ),
)

_DATASET_MAP = {spec.dataset_key: spec for spec in DATASET_REGISTRY}


def list_dataset_specs() -> list[DatasetSpec]:
    return list(DATASET_REGISTRY)


def get_dataset_spec(dataset_key: str) -> DatasetSpec:
    key = str(dataset_key or "").strip()
    spec = _DATASET_MAP.get(key)
    if spec is None:
        raise DatasetNotFoundError(f"Dataset no registrado: {dataset_key}")
    return spec


def to_definition_defaults(spec: DatasetSpec) -> dict[str, Any]:
    return {
        "name": spec.title,
        "description": spec.description,
        "domain_owner": spec.domain_owner,
        "scope_level": spec.scope_level,
        "required_permissions_json": spec.required_permissions,
        "filters_schema_json": spec.filters_schema,
        "dimensions_schema_json": spec.dimensions,
        "measures_schema_json": spec.measures,
        "freshness_mode": spec.freshness_mode,
        "materialization_policy": spec.materialization_policy,
        "export_capabilities_json": spec.export_capabilities,
        "render_hints_json": spec.render_hints,
        "schema_version": spec.schema_version,
        "semantic_version": spec.semantic_version,
        "status": spec.status,
        "is_certified": spec.is_certified,
        "is_enabled": spec.is_enabled,
    }

