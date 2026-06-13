"""Presupuesto agrícola (Ola G): CRUD + presupuesto-vs-real por labor×lote×ciclo.

El real reusa la fórmula de costeo existente: Σ(jornales × tarifa de la labor) +
Σ(cantidad × costo de insumo), filtrado por el ciclo (season_label) del presupuesto.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit

from .models import FincaBudget, FincaBudgetLine, Labor, Plot, WorkOrder
from .services import ZERO, _money, _q, _work_orders


class FincaBudgetError(ValueError):
    """Error de presupuesto de finca (código en .args[0])."""


def _get_finca(company: OrgUnit, finca_id: int) -> OrgUnit:
    finca = OrgUnit.objects.filter(id=finca_id, parent=company, unit_type=OrgUnit.UnitType.BRANCH).first()
    if finca is None:
        raise FincaBudgetError("FINCA_NOT_FOUND")
    return finca


def get_budget(company: OrgUnit, budget_id: int) -> FincaBudget:
    budget = FincaBudget.objects.filter(id=budget_id, finca__parent=company).select_related("finca").first()
    if budget is None:
        raise FincaBudgetError("BUDGET_NOT_FOUND")
    return budget


def list_budgets(company: OrgUnit, *, finca_id: int | None = None) -> list[FincaBudget]:
    qs = FincaBudget.objects.filter(finca__parent=company).select_related("finca")
    if finca_id:
        qs = qs.filter(finca_id=finca_id)
    return list(qs)


@transaction.atomic
def create_budget(*, company, actor, finca_id, season_label, name, request=None) -> FincaBudget:
    finca = _get_finca(company, finca_id)
    if not str(season_label or "").strip():
        raise FincaBudgetError("SEASON_REQUIRED")
    if not str(name or "").strip():
        raise FincaBudgetError("NAME_REQUIRED")
    budget = FincaBudget.objects.create(
        finca=finca, season_label=season_label.strip(), name=name.strip(), created_by=actor
    )
    _audit(request, actor, "FINCA_BUDGET_CREATED", budget, {"season": budget.season_label, "name": budget.name})
    return budget


@transaction.atomic
def upsert_lines(*, company, actor, budget_id, lines, request=None) -> FincaBudget:
    budget = get_budget(company, budget_id)
    if budget.status != FincaBudget.Status.DRAFT:
        raise FincaBudgetError("BUDGET_NOT_DRAFT")
    budget.lines.all().delete()
    for row in lines:
        labor = Labor.objects.filter(id=row["labor_id"]).filter(
            Q(company=company) | Q(company__isnull=True)
        ).first()
        if labor is None:
            raise FincaBudgetError("LABOR_NOT_FOUND")
        plot = Plot.objects.filter(id=row["plot_id"], finca=budget.finca).first()
        if plot is None:
            raise FincaBudgetError("PLOT_NOT_FOUND")
        FincaBudgetLine.objects.create(
            budget=budget,
            labor=labor,
            plot=plot,
            planned_jornales=_q(row.get("planned_jornales", 0)),
            planned_rate=_q(row.get("planned_rate", 0)),
            planned_insumos_amount=_q(row.get("planned_insumos_amount", 0)),
        )
    return budget


@transaction.atomic
def approve_budget(*, company, actor, budget_id, request=None) -> FincaBudget:
    budget = get_budget(company, budget_id)
    if budget.status != FincaBudget.Status.DRAFT:
        raise FincaBudgetError("BUDGET_NOT_DRAFT")
    if budget.created_by_id and actor and budget.created_by_id == actor.id:
        raise FincaBudgetError("SOD_SELF_APPROVAL")
    budget.status = FincaBudget.Status.APPROVED
    budget.approved_by = actor
    budget.approved_at = timezone.now()
    budget.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    _audit(request, actor, "FINCA_BUDGET_APPROVED", budget, {})
    return budget


@transaction.atomic
def archive_budget(*, company, actor, budget_id, request=None) -> FincaBudget:
    budget = get_budget(company, budget_id)
    budget.status = FincaBudget.Status.ARCHIVED
    budget.save(update_fields=["status", "updated_at"])
    _audit(request, actor, "FINCA_BUDGET_ARCHIVED", budget, {})
    return budget


def budget_vs_actual(company: OrgUnit, budget_id: int) -> dict:
    budget = get_budget(company, budget_id)
    season = budget.season_label
    rows = []
    tot_budget = ZERO
    tot_actual = ZERO
    for line in budget.lines.select_related("labor", "plot"):
        wos = list(
            _work_orders(
                WorkOrder.objects.filter(finca=budget.finca, plot=line.plot, labor=line.labor), season
            ).select_related("labor").prefetch_related("insumos")
        )
        actual_labor = _money(sum((_q(w.jornales) * _q(w.labor.default_rate) for w in wos), ZERO))
        actual_insumos = _money(sum((_q(i.quantity) * _q(i.unit_cost) for w in wos for i in w.insumos.all()), ZERO))
        actual = _money(actual_labor + actual_insumos)
        planned = _q(line.planned_total)
        variance = _money(planned - actual)
        rows.append(
            {
                "labor_id": line.labor_id,
                "labor_name": line.labor.name,
                "plot_id": line.plot_id,
                "plot_code": line.plot.code,
                "planned_jornales": str(_q(line.planned_jornales)),
                "planned_total": str(planned),
                "actual_jornales": str(_money(sum((_q(w.jornales) for w in wos), ZERO))),
                "actual_labor": str(actual_labor),
                "actual_insumos": str(actual_insumos),
                "actual_total": str(actual),
                "variance": str(variance),
                "variance_pct": str((variance / planned * 100).quantize(Decimal("0.01"))) if planned else None,
            }
        )
        tot_budget += planned
        tot_actual += actual
    return {
        "budget_id": budget.id,
        "finca_id": budget.finca_id,
        "season_label": season,
        "status": budget.status,
        "rows": rows,
        "total_planned": str(_money(tot_budget)),
        "total_actual": str(_money(tot_actual)),
        "total_variance": str(_money(tot_budget - tot_actual)),
    }


def budget_payload(b: FincaBudget, *, include_lines: bool = False) -> dict:
    out = {
        "id": b.id,
        "finca_id": b.finca_id,
        "finca_name": b.finca.name,
        "season_label": b.season_label,
        "name": b.name,
        "status": b.status,
        "status_label": b.get_status_display(),
        "created_at": b.created_at.isoformat(),
        "approved_at": b.approved_at.isoformat() if b.approved_at else None,
    }
    if include_lines:
        out["lines"] = [
            {
                "id": ln.id,
                "labor_id": ln.labor_id,
                "labor_name": ln.labor.name,
                "plot_id": ln.plot_id,
                "plot_code": ln.plot.code,
                "planned_jornales": str(ln.planned_jornales),
                "planned_rate": str(ln.planned_rate),
                "planned_insumos_amount": str(ln.planned_insumos_amount),
                "planned_total": str(ln.planned_total),
            }
            for ln in b.lines.select_related("labor", "plot")
        ]
    return out


def _audit(request, actor, event_type, budget, extra):
    write_event(
        request=request, module="FINCA", event_type=event_type, reason_code="FINCA_OK",
        actor_user=actor, subject_type="FINCA_BUDGET", subject_id=str(budget.id),
        metadata={"finca_id": str(budget.finca_id), **extra},
    )
