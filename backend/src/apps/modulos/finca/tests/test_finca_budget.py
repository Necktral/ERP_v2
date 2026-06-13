"""Tests del presupuesto de finca (Ola G): CRUD, SoD en aprobar, y presupuesto-vs-real
con jornales×tarifa + insumos reales."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.modulos.finca.models import (
    FincaBudget,
    InsumoApplication,
    Labor,
    Plot,
    WorkOrder,
)
from apps.modulos.finca.services_budget import (
    FincaBudgetError,
    approve_budget,
    budget_vs_actual,
    create_budget,
    upsert_lines,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()
UT = OrgUnit.UnitType
SEASON = "2025A"


def _mk_company():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    return OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)


def _mk_finca(company):
    return OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"Finca_{uuid.uuid4().hex[:4]}", parent=company)


def _mk_user():
    u = f"fc_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=u, email=f"{u}@t.local", password="pass12345")


def _setup(company, finca):
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    labor = Labor.objects.create(company=company, code=f"lab{uuid.uuid4().hex[:4]}", name="Chapia", default_rate=Decimal("150.00"))
    return plot, labor


@pytest.mark.django_db
def test_create_and_lines_only_in_draft():
    company = _mk_company()
    finca = _mk_finca(company)
    plot, labor = _setup(company, finca)
    actor = _mk_user()
    budget = create_budget(company=company, actor=actor, finca_id=finca.id, season_label=SEASON, name="Operativo")
    assert budget.status == FincaBudget.Status.DRAFT
    upsert_lines(company=company, actor=actor, budget_id=budget.id, lines=[
        {"labor_id": labor.id, "plot_id": plot.id, "planned_jornales": "10", "planned_rate": "150", "planned_insumos_amount": "200"},
    ])
    budget.refresh_from_db()
    line = budget.lines.get()
    assert line.planned_total == Decimal("1700.00")  # 10*150 + 200


@pytest.mark.django_db
def test_approve_requires_different_user():
    company = _mk_company()
    finca = _mk_finca(company)
    actor = _mk_user()
    budget = create_budget(company=company, actor=actor, finca_id=finca.id, season_label=SEASON, name="P")
    with pytest.raises(FincaBudgetError) as exc:
        approve_budget(company=company, actor=actor, budget_id=budget.id)
    assert str(exc.value) == "SOD_SELF_APPROVAL"
    approver = _mk_user()
    approved = approve_budget(company=company, actor=approver, budget_id=budget.id)
    assert approved.status == FincaBudget.Status.APPROVED


@pytest.mark.django_db
def test_lines_blocked_after_approval():
    company = _mk_company()
    finca = _mk_finca(company)
    plot, labor = _setup(company, finca)
    creator = _mk_user()
    budget = create_budget(company=company, actor=creator, finca_id=finca.id, season_label=SEASON, name="P")
    approve_budget(company=company, actor=_mk_user(), budget_id=budget.id)
    with pytest.raises(FincaBudgetError) as exc:
        upsert_lines(company=company, actor=creator, budget_id=budget.id, lines=[
            {"labor_id": labor.id, "plot_id": plot.id, "planned_jornales": "5"},
        ])
    assert str(exc.value) == "BUDGET_NOT_DRAFT"


@pytest.mark.django_db
def test_budget_vs_actual_uses_jornales_and_insumos():
    company = _mk_company()
    finca = _mk_finca(company)
    plot, labor = _setup(company, finca)
    actor = _mk_user()
    # Ejecución real: 10 jornales × 150 = 1500 mano de obra + 5 × 20 = 100 insumos = 1600.
    wo = WorkOrder.objects.create(
        finca=finca, plot=plot, labor=labor, season_label=SEASON,
        status=WorkOrder.Status.DONE, jornales=Decimal("10.00"),
    )
    InsumoApplication.objects.create(work_order=wo, quantity=Decimal("5.00"), unit_cost=Decimal("20.00"))

    budget = create_budget(company=company, actor=actor, finca_id=finca.id, season_label=SEASON, name="P")
    upsert_lines(company=company, actor=actor, budget_id=budget.id, lines=[
        {"labor_id": labor.id, "plot_id": plot.id, "planned_jornales": "10", "planned_rate": "150", "planned_insumos_amount": "200"},
    ])
    vs = budget_vs_actual(company, budget.id)
    row = vs["rows"][0]
    assert row["actual_labor"] == "1500.00"
    assert row["actual_insumos"] == "100.00"
    assert row["actual_total"] == "1600.00"
    assert row["planned_total"] == "1700.00"
    assert row["variance"] == "100.00"
    assert vs["total_variance"] == "100.00"


@pytest.mark.django_db
def test_other_company_finca_rejected():
    c1 = _mk_company()
    c2 = _mk_company()
    finca2 = _mk_finca(c2)
    with pytest.raises(FincaBudgetError) as exc:
        create_budget(company=c1, actor=_mk_user(), finca_id=finca2.id, season_label=SEASON, name="X")
    assert str(exc.value) == "FINCA_NOT_FOUND"
