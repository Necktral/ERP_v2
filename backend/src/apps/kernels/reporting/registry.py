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
    drill_metadata: dict[str, Any]
    quality_policy: dict[str, Any]
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

_SINGLE_DAY_FILTERS = {
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
        drill_metadata={
            "supports_drill_down": True,
            "supports_drill_through": True,
            "drill_through_dataset": "accounting.general_ledger.transaction",
            "drill_filters_mapping": {"account_code": "account_code"},
        },
        quality_policy={
            "required_totals": ["debit_total", "credit_total"],
            "required_dimensions": ["account_code"],
            "allow_empty_rows": False,
        },
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
        drill_metadata={"supports_drill_down": False, "supports_drill_through": False},
        quality_policy={
            "required_totals": [],
            "required_dimensions": ["journal_entry_id", "account_code"],
            "allow_empty_rows": True,
        },
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
        drill_metadata={
            "supports_drill_down": True,
            "supports_drill_through": True,
            "drill_through_dataset": "accounting.general_ledger.transaction",
            "drill_filters_mapping": {"account_code": "account_code"},
        },
        quality_policy={
            "required_totals": ["debit_total", "credit_total"],
            "required_dimensions": ["account_code"],
            "allow_empty_rows": False,
        },
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
        drill_metadata={"supports_drill_down": True, "supports_drill_through": False},
        quality_policy={
            "required_totals": ["assets", "liabilities", "equity"],
            "required_dimensions": ["section"],
            "allow_empty_rows": False,
        },
    ),
    DatasetSpec(
        dataset_key="accounting.operational_reconciliation.period",
        title="Operational Reconciliation",
        description="Conciliación operativa contra proyección contable.",
        domain_owner="ACCOUNTING",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("accounting.report.read",),
        filters_schema=dict(_SINGLE_DAY_FILTERS),
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
        drill_metadata={"supports_drill_down": False, "supports_drill_through": False},
        quality_policy={
            "required_totals": [
                "operational_count",
                "linked_count",
                "posted_count",
                "draft_exception_count",
                "pending_operational_events",
            ],
            "required_dimensions": ["source_module", "event_type"],
            "allow_empty_rows": True,
        },
    ),
    DatasetSpec(
        dataset_key="fuel.sales.by_shift.daily",
        title="Fuel Sales by Shift",
        description="Ventas Fuel agregadas por turno.",
        domain_owner="FUEL",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("fuel.reports.view",),
        filters_schema=dict(_SINGLE_DAY_FILTERS),
        dimensions=["shift_id", "shift_status", "opened_at", "closed_at"],
        measures=["sales_active", "sales_cancelled", "total_amount", "liters_sold"],
        grain="shift",
        freshness_mode=FreshnessMode.CACHE_ALLOWED,
        materialization_policy=MaterializationPolicy.CACHE_ALLOWED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "table"},
        drill_metadata={"supports_drill_down": True, "supports_drill_through": False},
        quality_policy={
            "required_totals": ["sales_active", "sales_cancelled", "total_amount", "liters_sold"],
            "required_dimensions": ["shift_id"],
            "allow_empty_rows": True,
        },
    ),
    DatasetSpec(
        dataset_key="fuel.sales.by_pump.daily",
        title="Fuel Sales by Pump",
        description="Ventas Fuel por surtidor y producto.",
        domain_owner="FUEL",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("fuel.reports.view",),
        filters_schema=dict(_SINGLE_DAY_FILTERS),
        dimensions=["pump_code", "product"],
        measures=["dispense_count", "sales_count", "liters", "amount_total"],
        grain="pump_product",
        freshness_mode=FreshnessMode.CACHE_ALLOWED,
        materialization_policy=MaterializationPolicy.CACHE_ALLOWED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "bar"},
        drill_metadata={"supports_drill_down": True, "supports_drill_through": False},
        quality_policy={
            "required_totals": ["dispense_count", "sales_count", "liters", "amount_total"],
            "required_dimensions": ["pump_code", "product"],
            "allow_empty_rows": True,
        },
    ),
    DatasetSpec(
        dataset_key="fuel.dispense_vs_sale.daily",
        title="Fuel Dispense vs Sale",
        description="Comparativo diario entre despacho físico y ventas registradas.",
        domain_owner="FUEL",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("fuel.reports.view",),
        filters_schema=dict(_SINGLE_DAY_FILTERS),
        dimensions=["date"],
        measures=["dispense_count", "sales_count", "liters_dispensed", "amount_sold", "cancelled_sales"],
        grain="day",
        freshness_mode=FreshnessMode.CACHE_ALLOWED,
        materialization_policy=MaterializationPolicy.CACHE_ALLOWED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "line"},
        drill_metadata={"supports_drill_down": False, "supports_drill_through": False},
        quality_policy={
            "required_totals": ["dispense_count", "sales_count", "liters_dispensed", "amount_sold", "cancelled_sales"],
            "required_dimensions": ["date"],
            "allow_empty_rows": True,
        },
    ),
    # ── Billing ─────────────────────────────────────────────────────
    DatasetSpec(
        dataset_key="billing.summary.period",
        title="Billing Summary",
        description="Resumen de facturación por tipo de documento y estado.",
        domain_owner="BILLING",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("billing.report.read",),
        filters_schema=dict(_SINGLE_DAY_FILTERS),
        dimensions=["doc_type", "status"],
        measures=["doc_count", "subtotal", "tax_total", "total"],
        grain="doc_type_status",
        freshness_mode=FreshnessMode.CACHE_ALLOWED,
        materialization_policy=MaterializationPolicy.CACHE_ALLOWED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "bar", "group_by": ["doc_type"]},
        drill_metadata={"supports_drill_down": False, "supports_drill_through": False},
        quality_policy={
            "required_totals": ["doc_count", "subtotal", "tax_total", "total"],
            "required_dimensions": ["doc_type", "status"],
            "allow_empty_rows": True,
        },
    ),
    # ── Inventory ───────────────────────────────────────────────────
    DatasetSpec(
        dataset_key="inventory.stock_balance.current",
        title="Stock Balance",
        description="Balance de inventario actual por bodega y producto.",
        domain_owner="INVENTORY",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("inventory.report.read",),
        filters_schema={},
        dimensions=["warehouse_code", "warehouse_name", "sku", "item_name", "uom"],
        measures=["qty_on_hand", "avg_cost", "stock_value"],
        grain="warehouse_item",
        freshness_mode=FreshnessMode.CACHE_ALLOWED,
        materialization_policy=MaterializationPolicy.CACHE_ALLOWED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "table"},
        drill_metadata={"supports_drill_down": False, "supports_drill_through": False},
        quality_policy={
            "required_totals": ["qty_on_hand", "stock_value"],
            "required_dimensions": ["sku"],
            "allow_empty_rows": True,
        },
    ),
    DatasetSpec(
        dataset_key="inventory.movements.period",
        title="Inventory Movements",
        description="Movimientos de inventario por período.",
        domain_owner="INVENTORY",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("inventory.report.read",),
        filters_schema=dict(_SINGLE_DAY_FILTERS),
        dimensions=["movement_type", "warehouse_code", "sku", "item_name", "source_module"],
        measures=["qty_delta", "unit_cost", "total_cost"],
        grain="movement",
        freshness_mode=FreshnessMode.CACHE_ALLOWED,
        materialization_policy=MaterializationPolicy.CACHE_ALLOWED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "table"},
        drill_metadata={"supports_drill_down": False, "supports_drill_through": False},
        quality_policy={
            "required_totals": ["movement_count", "total_cost"],
            "required_dimensions": ["movement_type"],
            "allow_empty_rows": True,
        },
    ),
    # ── HR ──────────────────────────────────────────────────────────
    DatasetSpec(
        dataset_key="hr.headcount.current",
        title="HR Headcount",
        description="Headcount activo por posición/cargo.",
        domain_owner="HR",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("hr.report.read",),
        filters_schema={},
        dimensions=["position_name", "position_code"],
        measures=["active_assignments", "unique_employees"],
        grain="position",
        freshness_mode=FreshnessMode.CACHE_ALLOWED,
        materialization_policy=MaterializationPolicy.CACHE_ALLOWED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "bar"},
        drill_metadata={"supports_drill_down": False, "supports_drill_through": False},
        quality_policy={
            "required_totals": ["active_assignments", "unique_employees"],
            "required_dimensions": ["position_name"],
            "allow_empty_rows": True,
        },
    ),
    # ── Payments ────────────────────────────────────────────────────
    DatasetSpec(
        dataset_key="payments.collection.period",
        title="Payment Collection",
        description="Cobros y sesiones de caja por período.",
        domain_owner="PAYMENTS",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("payments.report.read",),
        filters_schema=dict(_SINGLE_DAY_FILTERS),
        dimensions=["status"],
        measures=["payment_count", "amount"],
        grain="payment_status",
        freshness_mode=FreshnessMode.CACHE_ALLOWED,
        materialization_policy=MaterializationPolicy.CACHE_ALLOWED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "bar"},
        drill_metadata={"supports_drill_down": False, "supports_drill_through": False},
        quality_policy={
            "required_totals": ["payment_count", "amount"],
            "required_dimensions": ["status"],
            "allow_empty_rows": True,
        },
    ),
    # ── Procurement ─────────────────────────────────────────────────
    DatasetSpec(
        dataset_key="procurement.purchases.period",
        title="Procurement Summary",
        description="Resumen de compras por tipo y estado de documento.",
        domain_owner="PROCUREMENT",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=("procurement.report.read",),
        filters_schema=dict(_SINGLE_DAY_FILTERS),
        dimensions=["doc_type", "status"],
        measures=["doc_count", "subtotal", "tax_total", "total"],
        grain="doc_type_status",
        freshness_mode=FreshnessMode.CACHE_ALLOWED,
        materialization_policy=MaterializationPolicy.CACHE_ALLOWED,
        export_capabilities=["json", "csv", "xlsx"],
        render_hints={"default_chart": "bar", "group_by": ["doc_type"]},
        drill_metadata={"supports_drill_down": False, "supports_drill_through": False},
        quality_policy={
            "required_totals": ["doc_count", "subtotal", "tax_total", "total"],
            "required_dimensions": ["doc_type", "status"],
            "allow_empty_rows": True,
        },
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
        "quality_policy_json": spec.quality_policy,
        "schema_version": spec.schema_version,
        "semantic_version": spec.semantic_version,
        "status": spec.status,
        "is_certified": spec.is_certified,
        "is_enabled": spec.is_enabled,
    }
