"""Tests for the 5 new reporting domain adapters (Billing, Inventory, HR, Payments, Procurement).

Each adapter is tested with real ORM objects against a test DB to ensure the
reporting kernel produces correct envelopes with proper totals, dimensions,
and measures.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.kernels.reporting.domain_adapters import billing as billing_adapter
from apps.kernels.reporting.domain_adapters import hr as hr_adapter
from apps.kernels.reporting.domain_adapters import inventory as inventory_adapter
from apps.kernels.reporting.domain_adapters import payments as payments_adapter
from apps.kernels.reporting.domain_adapters import procurement as procurement_adapter
from apps.kernels.reporting.exceptions import DatasetExecutionError
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch", parent=company)
    return company, branch


# ── Billing adapter ─────────────────────────────────────────────


@pytest.mark.django_db
class TestBillingAdapter:
    def test_empty_billing_returns_valid_envelope(self):
        company, branch = _mk_org()
        today = timezone.localdate()
        result = billing_adapter.run_dataset(
            dataset_key="billing.summary.period",
            company=company,
            branch=branch,
            filters={"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        assert result["grain"] == "doc_type_status"
        assert result["rows"] == []
        assert int(result["totals"]["doc_count"]) == 0
        assert result["source_summary"]["source_modules"] == ["BILLING"]

    def test_billing_with_documents(self):
        from apps.kernels.facturacion.models import BillingDocument, DocStatus, DocType

        company, branch = _mk_org()
        today = timezone.localdate()

        BillingDocument.objects.create(
            company=company,
            branch=branch,
            doc_type=DocType.INVOICE,
            status=DocStatus.ISSUED,
            subtotal=Decimal("100.00"),
            tax_total=Decimal("15.00"),
            total=Decimal("115.00"),
        )
        BillingDocument.objects.create(
            company=company,
            branch=branch,
            doc_type=DocType.INVOICE,
            status=DocStatus.ISSUED,
            subtotal=Decimal("200.00"),
            tax_total=Decimal("30.00"),
            total=Decimal("230.00"),
        )
        BillingDocument.objects.create(
            company=company,
            branch=branch,
            doc_type=DocType.CREDIT_NOTE,
            status=DocStatus.VOIDED,
            subtotal=Decimal("50.00"),
            tax_total=Decimal("7.50"),
            total=Decimal("57.50"),
        )

        result = billing_adapter.run_dataset(
            dataset_key="billing.summary.period",
            company=company,
            branch=branch,
            filters={"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        assert len(result["rows"]) == 2  # 2 unique (doc_type, status) combos
        assert int(result["totals"]["doc_count"]) == 3
        assert Decimal(result["totals"]["total"]) == Decimal("402.50")

    def test_billing_unsupported_dataset(self):
        company, branch = _mk_org()
        with pytest.raises(DatasetExecutionError, match="no soportado"):
            billing_adapter.run_dataset(
                dataset_key="billing.nonexistent",
                company=company,
                branch=branch,
                filters={},
            )


# ── Inventory adapter ───────────────────────────────────────────


@pytest.mark.django_db
class TestInventoryAdapter:
    def test_empty_stock_balance(self):
        company, branch = _mk_org()
        result = inventory_adapter.run_dataset(
            dataset_key="inventory.stock_balance.current",
            company=company,
            branch=branch,
            filters={},
        )
        assert result["grain"] == "warehouse_item"
        assert result["rows"] == []
        assert result["source_summary"]["source_modules"] == ["INVENTORY"]

    def test_stock_balance_with_data(self):
        from apps.kernels.inventarios.models import InventoryItem, StockBalance, Warehouse

        company, branch = _mk_org()
        wh = Warehouse.objects.create(company=company, branch=branch, name="Bodega 1", code="WH01")
        item = InventoryItem.objects.create(company=company, sku="SKU001", name="Producto A")
        StockBalance.objects.create(
            company=company,
            branch=branch,
            warehouse=wh,
            item=item,
            qty_on_hand=Decimal("100.0000"),
            avg_cost=Decimal("5.500000"),
        )

        result = inventory_adapter.run_dataset(
            dataset_key="inventory.stock_balance.current",
            company=company,
            branch=branch,
            filters={},
        )
        assert len(result["rows"]) == 1
        assert result["rows"][0]["sku"] == "SKU001"
        assert Decimal(result["rows"][0]["stock_value"]) == Decimal("550.00")
        assert Decimal(result["totals"]["stock_value"]) == Decimal("550.00")

    def test_empty_movements(self):
        company, branch = _mk_org()
        today = timezone.localdate()
        result = inventory_adapter.run_dataset(
            dataset_key="inventory.movements.period",
            company=company,
            branch=branch,
            filters={"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        assert result["grain"] == "movement"
        assert result["rows"] == []
        assert int(result["totals"]["movement_count"]) == 0

    def test_movements_with_data(self):
        from apps.kernels.inventarios.models import InventoryItem, MovementType, StockMovement, Warehouse

        company, branch = _mk_org()
        wh = Warehouse.objects.create(company=company, branch=branch, name="Bodega 1", code="WH01")
        item = InventoryItem.objects.create(company=company, sku="SKU002", name="Producto B")

        StockMovement.objects.create(
            company=company,
            branch=branch,
            warehouse=wh,
            item=item,
            movement_type=MovementType.RECEIVE,
            qty_delta=Decimal("50.0000"),
            unit_cost=Decimal("10.000000"),
            total_cost=Decimal("500.000000"),
        )

        today = timezone.localdate()
        result = inventory_adapter.run_dataset(
            dataset_key="inventory.movements.period",
            company=company,
            branch=branch,
            filters={"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        assert len(result["rows"]) == 1
        assert int(result["totals"]["movement_count"]) == 1
        assert Decimal(result["totals"]["total_cost"]) == Decimal("500.00")

    def test_inventory_unsupported_dataset(self):
        company, branch = _mk_org()
        with pytest.raises(DatasetExecutionError, match="no soportado"):
            inventory_adapter.run_dataset(
                dataset_key="inventory.nonexistent",
                company=company,
                branch=branch,
                filters={},
            )


# ── HR adapter ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestHRAdapter:
    def test_empty_headcount(self):
        company, branch = _mk_org()
        result = hr_adapter.run_dataset(
            dataset_key="hr.headcount.current",
            company=company,
            branch=branch,
            filters={},
        )
        assert result["grain"] == "position"
        assert result["rows"] == []
        assert result["source_summary"]["source_modules"] == ["HR"]

    def test_headcount_with_data(self):
        from apps.modulos.hr.models import Employee, EmploymentAssignment, JobPosition

        company, branch = _mk_org()
        pos = JobPosition.objects.create(company=company, name="Developer", code="DEV")
        emp1 = Employee.objects.create(company=company, first_name="Alice", last_name="A")
        emp2 = Employee.objects.create(company=company, first_name="Bob", last_name="B")
        EmploymentAssignment.objects.create(employee=emp1, position=pos, branch=branch, is_active=True)
        EmploymentAssignment.objects.create(employee=emp2, position=pos, branch=branch, is_active=True)

        result = hr_adapter.run_dataset(
            dataset_key="hr.headcount.current",
            company=company,
            branch=branch,
            filters={},
        )
        assert len(result["rows"]) == 1
        assert result["rows"][0]["position_name"] == "Developer"
        assert int(result["rows"][0]["active_assignments"]) == 2
        assert int(result["rows"][0]["unique_employees"]) == 2
        assert int(result["totals"]["active_assignments"]) == 2
        assert int(result["totals"]["unique_employees"]) == 2

    def test_hr_unsupported_dataset(self):
        company, branch = _mk_org()
        with pytest.raises(DatasetExecutionError, match="no soportado"):
            hr_adapter.run_dataset(
                dataset_key="hr.nonexistent",
                company=company,
                branch=branch,
                filters={},
            )


# ── Payments adapter ────────────────────────────────────────────


@pytest.mark.django_db
class TestPaymentsAdapter:
    def test_empty_collection(self):
        company, branch = _mk_org()
        today = timezone.localdate()
        result = payments_adapter.run_dataset(
            dataset_key="payments.collection.period",
            company=company,
            branch=branch,
            filters={"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        assert result["grain"] == "payment_status"
        assert result["rows"] == []
        assert int(result["totals"]["payment_count"]) == 0
        assert result["source_summary"]["source_modules"] == ["PAYMENTS"]

    def test_collection_with_data(self):
        from apps.kernels.payments.models import PaymentIntent

        company, branch = _mk_org()
        PaymentIntent.objects.create(
            company=company,
            branch=branch,
            amount=Decimal("500.00"),
            status=PaymentIntent.Status.CAPTURED,
        )
        PaymentIntent.objects.create(
            company=company,
            branch=branch,
            amount=Decimal("200.00"),
            status=PaymentIntent.Status.CAPTURED,
        )
        PaymentIntent.objects.create(
            company=company,
            branch=branch,
            amount=Decimal("100.00"),
            status=PaymentIntent.Status.INTENDED,
        )

        today = timezone.localdate()
        result = payments_adapter.run_dataset(
            dataset_key="payments.collection.period",
            company=company,
            branch=branch,
            filters={"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        assert len(result["rows"]) == 2  # CAPTURED + INTENDED statuses
        assert int(result["totals"]["payment_count"]) == 3
        assert Decimal(result["totals"]["amount"]) == Decimal("800.00")

    def test_payments_unsupported_dataset(self):
        company, branch = _mk_org()
        with pytest.raises(DatasetExecutionError, match="no soportado"):
            payments_adapter.run_dataset(
                dataset_key="payments.nonexistent",
                company=company,
                branch=branch,
                filters={},
            )


# ── Procurement adapter ─────────────────────────────────────────


@pytest.mark.django_db
class TestProcurementAdapter:
    def test_empty_purchases(self):
        company, branch = _mk_org()
        today = timezone.localdate()
        result = procurement_adapter.run_dataset(
            dataset_key="procurement.purchases.period",
            company=company,
            branch=branch,
            filters={"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        assert result["grain"] == "doc_type_status"
        assert result["rows"] == []
        assert int(result["totals"]["doc_count"]) == 0
        assert result["source_summary"]["source_modules"] == ["PROCUREMENT"]

    def test_purchases_with_data(self):
        from apps.modulos.compras.models import PurchaseDocStatus, PurchaseDocType, PurchaseDocument

        company, branch = _mk_org()
        PurchaseDocument.objects.create(
            company=company,
            branch=branch,
            doc_type=PurchaseDocType.GOODS_RECEIPT,
            status=PurchaseDocStatus.POSTED,
            subtotal=Decimal("1000.00"),
            tax_total=Decimal("150.00"),
            total=Decimal("1150.00"),
        )
        PurchaseDocument.objects.create(
            company=company,
            branch=branch,
            doc_type=PurchaseDocType.SUPPLIER_INVOICE,
            status=PurchaseDocStatus.DRAFT,
            subtotal=Decimal("300.00"),
            tax_total=Decimal("45.00"),
            total=Decimal("345.00"),
        )

        today = timezone.localdate()
        result = procurement_adapter.run_dataset(
            dataset_key="procurement.purchases.period",
            company=company,
            branch=branch,
            filters={"date_from": today.isoformat(), "date_to": today.isoformat()},
        )
        assert len(result["rows"]) == 2
        assert int(result["totals"]["doc_count"]) == 2
        assert Decimal(result["totals"]["total"]) == Decimal("1495.00")

    def test_procurement_unsupported_dataset(self):
        company, branch = _mk_org()
        with pytest.raises(DatasetExecutionError, match="no soportado"):
            procurement_adapter.run_dataset(
                dataset_key="procurement.nonexistent",
                company=company,
                branch=branch,
                filters={},
            )


# ── Registry completeness ───────────────────────────────────────


@pytest.mark.django_db
class TestRegistryCompleteness:
    """Verify that all new datasets are registered and can dispatch without import errors."""

    def test_all_new_datasets_registered(self):
        from apps.kernels.reporting.registry import get_dataset_spec

        new_keys = [
            "billing.summary.period",
            "inventory.stock_balance.current",
            "inventory.movements.period",
            "hr.headcount.current",
            "payments.collection.period",
            "procurement.purchases.period",
        ]
        for key in new_keys:
            spec = get_dataset_spec(key)
            assert spec.dataset_key == key
            assert spec.is_enabled is True
            assert spec.is_certified is True
            assert len(spec.dimensions) > 0
            assert len(spec.measures) > 0
            assert len(spec.export_capabilities) > 0

    def test_total_dataset_count_is_14(self):
        from apps.kernels.reporting.registry import list_dataset_specs

        specs = list_dataset_specs()
        assert len(specs) == 14
