"""Tests Fase 2: #2 insumos contra inventario + #1 costo de finca → GL.

#2: aplicar insumo desde stock descuenta inventario real (costo promedio) e idempotente.
#1: postear el costo real de la finca genera un asiento de reclasificación balanceado
(DÉBITO costo-cultivo == CRÉDITO costos-aplicados), best-effort, auditado.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.accounting.models import JournalDraft
from apps.kernels.inventarios.models import (
    InventoryItem,
    MovementType,
    StockMovement,
    Warehouse,
)
from apps.kernels.inventarios.services import post_receive
from apps.kernels.nomina.models import (
    FieldCrew,
    FieldCrewReport,
    FieldCrewReportLine,
    FieldCrewReportStatus,
    FieldWorkDay,
)
from apps.modulos.audit.models import AuditEvent
from apps.modulos.finca.accounting_link import post_finca_cost_to_accounting
from apps.modulos.finca.inventory_link import issue_insumo_from_stock
from apps.modulos.finca.models import InsumoApplication, Labor, Plot, WorkOrder
from apps.modulos.finca.services import upsert_finca_profile
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _mk_company():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    return OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)


def _mk_finca(company, name="Finca"):
    return OrgUnit.objects.create(unit_type=UT.BRANCH, name=name, parent=company)


def _mk_user(prefix="u"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@t.local", password="pass12345")


def _req(company, branch, user):
    return SimpleNamespace(
        company=company, branch=branch, user=user, META={}, headers={}, path="/t/", method="POST", request_id="r1"
    )


def _stock(company, finca, user, *, qty="10", unit_cost="50"):
    wh = Warehouse.objects.create(company=company, branch=finca, name="Bodega", code=f"W{uuid.uuid4().hex[:5]}")
    item = InventoryItem.objects.create(company=company, sku=f"INS-{uuid.uuid4().hex[:5]}", name="Urea", uom="UNIT")
    post_receive(
        request=_req(company, finca, user), actor=user, warehouse_id=wh.id, item_id=item.id,
        qty=Decimal(qty), unit_cost=Decimal(unit_cost), idempotency_key=f"rcv-{uuid.uuid4().hex}",
    )
    return wh, item


def _labor(company, code="chapia_t", rate="100.00"):
    return Labor.objects.create(
        company=company, code=code, name=code, category="MANTENIMIENTO", unit="JORNAL", default_rate=Decimal(rate),
    )


_DAY = [0]


def _field_jornales(finca, company, *, labor_code, day_values):
    _DAY[0] += 1
    wd = FieldWorkDay.objects.create(
        company=company, branch=finca, work_date=dt.date(2026, 2, 1) + dt.timedelta(days=_DAY[0])
    )
    sup = Employee.objects.create(company=company, first_name="Capataz")
    crew = FieldCrew.objects.create(work_day=wd, name=f"Cuad {_DAY[0]}", supervisor_employee=sup)
    report = FieldCrewReport.objects.create(
        crew=crew, status=FieldCrewReportStatus.SUBMITTED, labor_code=labor_code, labor_name=labor_code, zone_label="A"
    )
    for dv in day_values:
        emp = Employee.objects.create(company=company, first_name="T")
        FieldCrewReportLine.objects.create(report=report, employee=emp, day_value=Decimal(str(dv)))
    return report


def _wo(finca, company, labor):
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    return WorkOrder.objects.create(finca=finca, plot=plot, labor=labor, status=WorkOrder.Status.DONE)


# --------------------------------------------------------------------------- #
# #2 Insumos contra inventario
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_issue_insumo_from_stock_uses_real_avg_cost():
    company = _mk_company()
    finca = _mk_finca(company)
    user = _mk_user()
    wh, item = _stock(company, finca, user, qty="10", unit_cost="50")
    wo = _wo(finca, company, _labor(company))

    app = issue_insumo_from_stock(
        wo, warehouse_id=wh.id, item_id=item.id, qty=Decimal("4"),
        request=_req(company, finca, user), actor=user, idempotency_key="iss-1",
    )
    assert app.source == InsumoApplication.Source.INVENTORY
    assert app.unit_cost == Decimal("50.00")        # costo promedio real
    assert app.inventory_item_id == item.id
    assert app.stock_movement_ref
    assert StockMovement.objects.filter(company=company, movement_type=MovementType.ISSUE).count() == 1
    assert AuditEvent.objects.filter(event_type="FINCA_INSUMO_ISSUED").exists()


@pytest.mark.django_db
def test_issue_insumo_idempotent():
    company = _mk_company()
    finca = _mk_finca(company)
    user = _mk_user()
    wh, item = _stock(company, finca, user)
    wo = _wo(finca, company, _labor(company))
    kwargs = dict(warehouse_id=wh.id, item_id=item.id, qty=Decimal("4"),
                  request=_req(company, finca, user), actor=user, idempotency_key="iss-dup")

    a1 = issue_insumo_from_stock(wo, **kwargs)
    a2 = issue_insumo_from_stock(wo, **kwargs)
    assert a1.id == a2.id
    assert InsumoApplication.objects.filter(work_order=wo).count() == 1
    assert StockMovement.objects.filter(company=company, movement_type=MovementType.ISSUE).count() == 1


# --------------------------------------------------------------------------- #
# #1 Costo de finca → GL
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_post_finca_cost_generates_balanced_draft():
    company = _mk_company()
    finca = _mk_finca(company, "Santa Isabel")
    user = _mk_user()
    upsert_finca_profile(finca, data={"zona": "Nucleo", "area_manzanas": "120.00"})
    labor = _labor(company, rate="100.00")
    wo = _wo(finca, company, labor)
    # mano de obra real: 2 jornales * 100 = 200
    _field_jornales(finca, company, labor_code="chapia_t", day_values=["1.00", "1.00"])
    # insumo desde inventario: 4 * 50 = 200
    wh, item = _stock(company, finca, user, qty="10", unit_cost="50")
    issue_insumo_from_stock(wo, warehouse_id=wh.id, item_id=item.id, qty=Decimal("4"),
                            request=_req(company, finca, user), actor=user, idempotency_key="iss-x")

    result = post_finca_cost_to_accounting(request=_req(company, finca, user), actor=user, finca=finca)

    assert result["total_cost"] == "400.00"          # 200 MO + 200 insumo
    assert result["link_status"] in {"DRAFT_VALIDATED", "POSTED"}
    assert result["journal_draft_id"] is not None
    draft = JournalDraft.objects.get(id=result["journal_draft_id"])
    assert draft.total_debit == draft.total_credit == Decimal("400.00")
    assert OutboxEvent.objects.filter(source_module="FINCA", event_type="FincaCostAccrued").exists()
    assert AuditEvent.objects.filter(event_type="FINCA_COST_POSTED").exists()


@pytest.mark.django_db
def test_post_finca_cost_zero_is_skipped():
    company = _mk_company()
    finca = _mk_finca(company)
    user = _mk_user()
    result = post_finca_cost_to_accounting(request=_req(company, finca, user), actor=user, finca=finca)
    assert result["link_status"] == "SKIPPED"
    assert result["journal_draft_id"] is None
    assert not OutboxEvent.objects.filter(source_module="FINCA").exists()


# --------------------------------------------------------------------------- #
# HTTP + RBAC
# --------------------------------------------------------------------------- #

def _grant(user, company, branch, perm_codes):
    UserMembership.objects.get_or_create(user=user, org_unit=company, defaults={"is_active": True})
    UserMembership.objects.get_or_create(user=user, org_unit=branch, defaults={"is_active": True})
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)
    return user


def _client(user, company, branch):
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


@pytest.mark.django_db
def test_finca_cost_post_forbidden_without_perm():
    company = _mk_company()
    finca = _mk_finca(company)
    user = _grant(_mk_user("n"), company, finca, ["finca.field.read"])  # sin finca.cost.post
    r = _client(user, company, finca).post("/api/finca/reports/finca-cost/post/", {"finca_id": finca.id}, format="json")
    assert r.status_code == 403


@pytest.mark.django_db
def test_issue_insumo_and_post_cost_http():
    company = _mk_company()
    finca = _mk_finca(company, "Santa Isabel")
    upsert_finca_profile(finca, data={"zona": "Nucleo", "area_manzanas": "120.00"})
    labor = _labor(company, rate="100.00")
    wo = _wo(finca, company, labor)
    _field_jornales(finca, company, labor_code="chapia_t", day_values=["1.00"])  # 100
    admin = _mk_user("a")
    wh, item = _stock(company, finca, admin, qty="10", unit_cost="50")
    api = _client(_grant(admin, company, finca, ["finca.work.capture", "finca.cost.post"]), company, finca)

    # #2 issue-insumo vía HTTP
    r = api.post(f"/api/finca/work-orders/{wo.id}/issue-insumo/",
                 {"warehouse_id": wh.id, "item_id": item.id, "quantity": "2", "idempotency_key": "h-iss"},
                 format="json")
    assert r.status_code == 201, r.data
    assert r.data["source"] == "INVENTORY"
    assert r.data["unit_cost"] == "50.00"

    # #1 postear costo: 100 MO + 100 insumo = 200
    r = api.post("/api/finca/reports/finca-cost/post/", {"finca_id": finca.id}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["total_cost"] == "200.00"
    assert r.data["journal_draft_id"] is not None
