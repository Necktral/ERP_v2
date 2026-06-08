"""Servicios de Manejo de Fincas (Capa 6, básico).

Master-data + bitácora de labores + costeo básico (read-only). Reusa
`audit.writer.write_event`. El costeo agrega jornales×tarifa + insumos por lote,
y consolida por finca y por zona (vía FincaProfile.zona) — multi-finca.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit

from .models import FincaProfile, InsumoApplication, Labor, Plot, WorkOrder

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def _q(value) -> Decimal:
    return Decimal(str(value if value is not None else 0))


def _money(value: Decimal) -> Decimal:
    return _q(value).quantize(CENT)


# --------------------------------------------------------------------------- #
# Master-data
# --------------------------------------------------------------------------- #

@transaction.atomic
def upsert_finca_profile(finca: OrgUnit, *, data: dict, request=None, actor=None) -> FincaProfile:
    profile, _created = FincaProfile.objects.get_or_create(finca=finca)
    for field in ["department", "municipio", "zona", "area_manzanas", "is_headquarters", "gps_lat", "gps_lng", "notes"]:
        if field in data:
            setattr(profile, field, data[field])
    profile.full_clean()
    profile.save()
    write_event(
        request=request,
        module="FINCA",
        event_type="FINCA_PROFILE_UPSERTED",
        reason_code="OK",
        actor_user=actor,
        subject_type="FINCA",
        subject_id=str(finca.id),
        metadata={"zona": profile.zona, "company_id": str(getattr(finca.parent, "id", ""))},
    )
    return profile


@transaction.atomic
def create_plot(finca: OrgUnit, *, data: dict, request=None, actor=None) -> Plot:
    plot = Plot(finca=finca, **{k: data[k] for k in data if k in {
        "code", "name", "area_manzanas", "crop", "variety", "planting_year", "is_active"
    }})
    plot.full_clean()
    plot.save()
    write_event(
        request=request,
        module="FINCA",
        event_type="FINCA_PLOT_CREATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="FINCA_PLOT",
        subject_id=str(plot.id),
        metadata={"finca_id": str(finca.id), "code": plot.code},
    )
    return plot


@transaction.atomic
def create_labor(company: OrgUnit, *, data: dict, request=None, actor=None) -> Labor:
    labor = Labor(company=company, **{k: data[k] for k in data if k in {
        "code", "name", "category", "unit", "is_piecework", "expected_yield", "default_rate", "is_active"
    }})
    labor.full_clean()
    labor.save()
    write_event(
        request=request,
        module="FINCA",
        event_type="FINCA_LABOR_CREATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="FINCA_LABOR",
        subject_id=str(labor.id),
        metadata={"company_id": str(company.id), "code": labor.code},
    )
    return labor


def labors_for(company: OrgUnit):
    """Labores activas aplicables: las de la empresa + las globales."""
    from django.db.models import Q

    return Labor.objects.filter(is_active=True).filter(Q(company=company) | Q(company__isnull=True)).order_by(
        "category", "code"
    )


# --------------------------------------------------------------------------- #
# Bitácora / órdenes de trabajo
# --------------------------------------------------------------------------- #

@transaction.atomic
def log_work(finca: OrgUnit, *, plot: Plot, labor: Labor, data: dict, request=None, actor=None) -> WorkOrder:
    """Crea una orden de trabajo (idempotente por external_ref dentro de la finca)."""
    external_ref = str(data.get("external_ref") or "").strip()
    if external_ref:
        existing = WorkOrder.objects.filter(finca=finca, external_ref=external_ref).first()
        if existing is not None:
            return existing

    wo = WorkOrder(
        finca=finca,
        plot=plot,
        labor=labor,
        season_label=data.get("season_label", ""),
        planned_date=data.get("planned_date"),
        done_date=data.get("done_date"),
        supervisor_id=data.get("supervisor_id"),
        status=data.get("status", WorkOrder.Status.PLANNED),
        target_quantity=data.get("target_quantity"),
        actual_quantity=data.get("actual_quantity"),
        jornales=_q(data.get("jornales", 0)),
        notes=data.get("notes", ""),
        external_ref=external_ref,
        created_by=actor,
    )
    wo.full_clean(exclude=["created_by", "supervisor"])
    wo.save()
    write_event(
        request=request,
        module="FINCA",
        event_type="FINCA_WORKORDER_LOGGED",
        reason_code="OK",
        actor_user=actor,
        subject_type="FINCA_WORKORDER",
        subject_id=str(wo.id),
        metadata={"finca_id": str(finca.id), "plot_id": str(plot.id), "labor": labor.code, "status": wo.status},
    )
    return wo


@transaction.atomic
def update_work_order(wo: WorkOrder, *, data: dict, request=None, actor=None) -> WorkOrder:
    before = {"status": wo.status, "jornales": str(wo.jornales)}
    for field in ["status", "done_date", "target_quantity", "actual_quantity", "jornales", "notes", "season_label"]:
        if field in data:
            setattr(wo, field, data[field])
    wo.full_clean(exclude=["created_by", "supervisor"])
    wo.save()
    write_event(
        request=request,
        module="FINCA",
        event_type="FINCA_WORKORDER_LOGGED",
        reason_code="OK",
        actor_user=actor,
        subject_type="FINCA_WORKORDER",
        subject_id=str(wo.id),
        before_snapshot=before,
        after_snapshot={"status": wo.status, "jornales": str(wo.jornales)},
        metadata={"finca_id": str(wo.finca_id)},
    )
    return wo


@transaction.atomic
def apply_insumo(work_order: WorkOrder, *, data: dict, request=None, actor=None) -> InsumoApplication:
    app = InsumoApplication.objects.create(
        work_order=work_order,
        item_code=data.get("item_code", ""),
        item_name=data.get("item_name", ""),
        quantity=_q(data.get("quantity", 0)),
        unit=data.get("unit", ""),
        unit_cost=data.get("unit_cost"),
        notes=data.get("notes", ""),
    )
    write_event(
        request=request,
        module="FINCA",
        event_type="FINCA_INSUMO_APPLIED",
        reason_code="OK",
        actor_user=actor,
        subject_type="FINCA_WORKORDER",
        subject_id=str(work_order.id),
        metadata={"item": app.item_code or app.item_name, "quantity": str(app.quantity)},
    )
    return app


# --------------------------------------------------------------------------- #
# Costeo básico
# --------------------------------------------------------------------------- #

def _work_orders(qs, season):
    qs = qs.exclude(status=WorkOrder.Status.CANCELLED)
    if season:
        qs = qs.filter(season_label=season)
    return qs


def plot_cost_summary(finca: OrgUnit, *, season: str | None = None) -> list[dict[str, Any]]:
    """Agrega por lote: jornales, costo mano de obra, insumos y costo/manzana."""
    out: list[dict[str, Any]] = []
    plots = Plot.objects.filter(finca=finca).order_by("code")
    for plot in plots:
        wos = list(
            _work_orders(WorkOrder.objects.filter(plot=plot), season).select_related("labor").prefetch_related("insumos")
        )
        jornales = _money(sum((_q(w.jornales) for w in wos), ZERO))
        labor_cost = _money(sum((_q(w.jornales) * _q(w.labor.default_rate) for w in wos), ZERO))
        insumo_cost = _money(sum((_q(i.quantity) * _q(i.unit_cost) for w in wos for i in w.insumos.all()), ZERO))
        total = _money(labor_cost + insumo_cost)
        area = _q(plot.area_manzanas)
        out.append(
            {
                "plot_id": plot.id,
                "plot_code": plot.code,
                "area_manzanas": str(_money(area)),
                "work_orders": len(wos),
                "jornales": str(jornales),
                "labor_cost": str(labor_cost),
                "insumo_cost": str(insumo_cost),
                "total_cost": str(total),
                "cost_per_manzana": str((total / area).quantize(CENT) if area else ZERO),
            }
        )
    return out


def company_cost_summary(company: OrgUnit, *, season: str | None = None) -> dict[str, Any]:
    """Consolida el costeo de todas las fincas de la empresa, por finca y por zona."""
    fincas = OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).order_by("name")
    by_finca: list[dict[str, Any]] = []
    by_zona: dict[str, Decimal] = {}
    for finca in fincas:
        plots = plot_cost_summary(finca, season=season)
        finca_total = sum((Decimal(p["total_cost"]) for p in plots), ZERO)
        finca_jornales = sum((Decimal(p["jornales"]) for p in plots), ZERO)
        profile = getattr(finca, "finca_profile", None)
        zona = (profile.zona if profile else "") or "(sin zona)"
        by_finca.append(
            {
                "finca_id": finca.id,
                "finca_name": finca.name,
                "zona": zona,
                "plots": len(plots),
                "jornales": str(finca_jornales),
                "total_cost": str(finca_total),
            }
        )
        by_zona[zona] = by_zona.get(zona, ZERO) + finca_total
    return {
        "by_finca": by_finca,
        "by_zona": [{"zona": z, "total_cost": str(total)} for z, total in sorted(by_zona.items())],
    }
