"""Tests de los handlers de sync offline de finca (#3 Fase 2).

Verifica el contrato sobre `sync_engine`: handlers registrados, captura de campo
(log_work) idempotente, rechazos controlados (SyncRejectError) y aplicación de
insumos/actualización. Se prueban los handlers directamente (la criptografía Ed25519
y la deduplicación por command_id las cubre el motor en sus propios tests).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

import apps.modulos.sync_engine.services  # noqa: F401  side-effect: registra handlers
from apps.modulos.finca.models import InsumoApplication, Labor, Plot, WorkOrder
from apps.modulos.sync_engine.errors import SyncRejectError
from apps.modulos.sync_engine.handlers_finca import (
    handle_finca_apply_insumo,
    handle_finca_log_work,
    handle_finca_update_workorder,
)
from apps.modulos.sync_engine.registry import get_handler
from apps.modulos.iam.models import OrgUnit

User = get_user_model()
UT = OrgUnit.UnitType


def _company():
    s = uuid.uuid4().hex[:6]
    h = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    return OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=h)


def _finca(company, name="Finca"):
    return OrgUnit.objects.create(unit_type=UT.BRANCH, name=name, parent=company)


def _user():
    u = f"u_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=u, email=f"{u}@t.local", password="x")


def _labor(company, code="chapia_t", rate="200.00"):
    return Labor.objects.create(
        company=company, code=code, name=code, category="MANTENIMIENTO", unit="JORNAL",
        default_rate=Decimal(rate),
    )


def _ctx(company, finca, user, *, command_id=None, command_type="FINCA_LOG_WORK"):
    request = SimpleNamespace(
        company=None, branch=None, user=user, META={}, headers={}, path="/sync/", method="POST", request_id="r1"
    )
    return {
        "request": request, "actor_user": user, "device": None,
        "company_id": company.id, "branch_id": finca.id,
        "command_id": command_id or str(uuid.uuid4()),
        "command_type": command_type, "occurred_at": "2026-06-08T00:00:00+00:00", "sequence": 1,
    }


@pytest.mark.django_db
def test_finca_handlers_registered():
    # El import side-effect en services.py debe haber registrado los handlers.
    assert get_handler("FINCA_LOG_WORK") is not None
    assert get_handler("FINCA_UPDATE_WORKORDER") is not None
    assert get_handler("FINCA_APPLY_INSUMO") is not None


@pytest.mark.django_db
def test_log_work_handler_creates_and_is_idempotent():
    company = _company()
    finca = _finca(company)
    user = _user()
    labor = _labor(company)
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    payload = {"plot_id": plot.id, "labor_id": labor.id, "jornales": "5.00",
               "status": "DONE", "done_date": "2026-06-01", "external_ref": "wo-sync-1"}

    res = handle_finca_log_work(_ctx(company, finca, user), payload)
    assert res["refs"]["status"] == "DONE"
    wo_id = res["refs"]["work_order_id"]
    assert WorkOrder.objects.filter(finca=finca).count() == 1

    # Mismo external_ref (otro command_id) → misma orden (idempotente, no duplica).
    res2 = handle_finca_log_work(_ctx(company, finca, user), payload)
    assert res2["refs"]["work_order_id"] == wo_id
    assert WorkOrder.objects.filter(finca=finca).count() == 1


@pytest.mark.django_db
def test_log_work_rejects_unknown_plot():
    company = _company()
    finca = _finca(company)
    user = _user()
    labor = _labor(company)
    with pytest.raises(SyncRejectError) as exc:
        handle_finca_log_work(_ctx(company, finca, user), {"plot_id": 999999, "labor_id": labor.id})
    assert str(exc.value) == "FINCA_NOT_FOUND"


@pytest.mark.django_db
def test_log_work_rejects_bad_scope():
    company = _company()
    finca = _finca(company)
    user = _user()
    labor = _labor(company)
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    ctx = _ctx(company, finca, user)
    ctx["branch_id"] = None  # finca requerida
    with pytest.raises(SyncRejectError) as exc:
        handle_finca_log_work(ctx, {"plot_id": plot.id, "labor_id": labor.id})
    assert str(exc.value) == "FINCA_INVALID_SCOPE"


@pytest.mark.django_db
def test_apply_insumo_and_update_workorder_handlers():
    company = _company()
    finca = _finca(company)
    user = _user()
    labor = _labor(company)
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    wo = WorkOrder.objects.create(finca=finca, plot=plot, labor=labor, status=WorkOrder.Status.PLANNED)

    res = handle_finca_apply_insumo(
        _ctx(company, finca, user, command_type="FINCA_APPLY_INSUMO"),
        {"work_order_id": wo.id, "item_name": "Urea", "quantity": "2.00", "unit_cost": "50.00"},
    )
    assert InsumoApplication.objects.filter(id=res["refs"]["insumo_id"]).exists()

    res = handle_finca_update_workorder(
        _ctx(company, finca, user, command_type="FINCA_UPDATE_WORKORDER"),
        {"work_order_id": wo.id, "status": "DONE", "jornales": "3.00"},
    )
    assert res["refs"]["status"] == "DONE"
    wo.refresh_from_db()
    assert wo.status == "DONE"
    assert wo.jornales == Decimal("3.00")


# --------------------------------------------------------------------------- #
# Rechazos controlados (rutas de error) — cobertura de los reject paths
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_log_work_rejects_unknown_company():
    company = _company()
    finca = _finca(company)
    ctx = _ctx(company, finca, _user())
    ctx["company_id"] = 999999  # empresa inexistente
    with pytest.raises(SyncRejectError) as exc:
        handle_finca_log_work(ctx, {"plot_id": 1, "labor_id": 1})
    assert str(exc.value) == "FINCA_INVALID_SCOPE"


@pytest.mark.django_db
def test_log_work_rejects_unknown_branch():
    company = _company()
    finca = _finca(company)
    ctx = _ctx(company, finca, _user())
    ctx["branch_id"] = 999999  # finca inexistente bajo la empresa
    with pytest.raises(SyncRejectError) as exc:
        handle_finca_log_work(ctx, {"plot_id": 1, "labor_id": 1})
    assert str(exc.value) == "FINCA_INVALID_SCOPE"


@pytest.mark.django_db
def test_log_work_rejects_missing_and_invalid_plot_id():
    company = _company()
    finca = _finca(company)
    user = _user()
    with pytest.raises(SyncRejectError) as e1:
        handle_finca_log_work(_ctx(company, finca, user), {"labor_id": 1})  # sin plot_id
    assert str(e1.value) == "FINCA_SCHEMA_INVALID"
    with pytest.raises(SyncRejectError) as e2:
        handle_finca_log_work(_ctx(company, finca, user), {"plot_id": "abc", "labor_id": 1})
    assert str(e2.value) == "FINCA_SCHEMA_INVALID"


@pytest.mark.django_db
def test_log_work_rejects_unknown_labor():
    company = _company()
    finca = _finca(company)
    user = _user()
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    with pytest.raises(SyncRejectError) as exc:
        handle_finca_log_work(_ctx(company, finca, user), {"plot_id": plot.id, "labor_id": 999999})
    assert str(exc.value) == "FINCA_NOT_FOUND"


@pytest.mark.django_db
def test_log_work_rejects_invalid_status():
    company = _company()
    finca = _finca(company)
    user = _user()
    labor = _labor(company)
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    with pytest.raises(SyncRejectError) as exc:
        handle_finca_log_work(
            _ctx(company, finca, user),
            {"plot_id": plot.id, "labor_id": labor.id, "status": "NOT_A_STATUS"},
        )
    assert str(exc.value) == "FINCA_SCHEMA_INVALID"  # full_clean → ValidationError


@pytest.mark.django_db
def test_update_workorder_rejects_unknown_and_invalid():
    company = _company()
    finca = _finca(company)
    user = _user()
    labor = _labor(company)
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    ctx = _ctx(company, finca, user, command_type="FINCA_UPDATE_WORKORDER")
    with pytest.raises(SyncRejectError) as e1:
        handle_finca_update_workorder(ctx, {"work_order_id": 999999, "status": "DONE"})
    assert str(e1.value) == "FINCA_NOT_FOUND"
    wo = WorkOrder.objects.create(finca=finca, plot=plot, labor=labor, status=WorkOrder.Status.PLANNED)
    with pytest.raises(SyncRejectError) as e2:
        handle_finca_update_workorder(ctx, {"work_order_id": wo.id, "status": "NOPE"})
    assert str(e2.value) == "FINCA_SCHEMA_INVALID"


@pytest.mark.django_db
def test_apply_insumo_rejects_unknown_workorder():
    company = _company()
    finca = _finca(company)
    user = _user()
    with pytest.raises(SyncRejectError) as exc:
        handle_finca_apply_insumo(
            _ctx(company, finca, user, command_type="FINCA_APPLY_INSUMO"),
            {"work_order_id": 999999, "item_name": "Urea"},
        )
    assert str(exc.value) == "FINCA_NOT_FOUND"


@pytest.mark.django_db
def test_apply_insumo_rejects_invalid_unit_cost():
    company = _company()
    finca = _finca(company)
    user = _user()
    labor = _labor(company)
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    wo = WorkOrder.objects.create(finca=finca, plot=plot, labor=labor, status=WorkOrder.Status.PLANNED)
    with pytest.raises(SyncRejectError) as exc:
        handle_finca_apply_insumo(
            _ctx(company, finca, user, command_type="FINCA_APPLY_INSUMO"),
            {"work_order_id": wo.id, "item_name": "Urea", "quantity": "1.00", "unit_cost": "abc"},
        )
    assert str(exc.value) == "FINCA_SCHEMA_INVALID"  # DecimalField.to_python → ValidationError
