"""Puente Asistencia de campo (nómina) → Labores (finca) → Costeo real.

Fase 2 del Manejo de Fincas. La **única fuente de verdad de la asistencia** es la
captura de campo en `kernels.nomina` (`FieldCrewReport` + `FieldCrewReportLine`):
cada reporte de cuadrilla trae `labor_code`/`zone_label` como **texto libre** y sus
líneas un `day_value` (0..1) por trabajador. Aquí **leemos** esa captura (sin
recapturar nada), mapeamos el `labor_code` contra el **catálogo de labores** de la
finca para darle semántica de costo, y producimos:

  * un *rollup* de **jornales reales** por labor y por zona,
  * una **reconciliación** de los `labor_code`/`zone_label` capturados contra el
    catálogo (calidad de dato),
  * un **costeo real** (jornales reales × tarifa + insumos).

Dependencia **unidireccional** `modulos.finca → kernels.nomina` (lectura): nómina no
conoce a finca, así no hay ciclo. Ver [[erp-v2-offline-sync-architecture]] y
[[attendance-vs-manejo-finca-boundary]].
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from apps.kernels.nomina.models import FieldCrewReport, FieldCrewReportStatus
from apps.modulos.iam.models import OrgUnit

from .models import InsumoApplication, WorkOrder
from .services import CENT, ZERO, _money, _q, labors_for

# Estados de reporte de cuadrilla que cuentan como asistencia "real" para costeo.
COUNTABLE_STATUSES = (
    FieldCrewReportStatus.SUBMITTED,
    FieldCrewReportStatus.REVIEWED,
    FieldCrewReportStatus.APPROVED,
)


def _company_of(finca: OrgUnit) -> OrgUnit | None:
    parent = getattr(finca, "parent", None)
    if parent is not None and parent.unit_type == OrgUnit.UnitType.COMPANY:
        return parent
    return None


def _labor_index(finca: OrgUnit) -> dict[str, Any]:
    """{code: Labor} aplicable a la finca (catálogo de empresa + globales)."""
    company = _company_of(finca)
    if company is None:
        return {}
    return {lab.code.strip(): lab for lab in labors_for(company)}


def _reports_qs(finca: OrgUnit, *, date_from=None, date_to=None, payroll_period_id=None,
                statuses=COUNTABLE_STATUSES):
    """Reportes de cuadrilla de los días-laborales de esta finca (BRANCH)."""
    qs = (
        FieldCrewReport.objects
        .filter(crew__work_day__branch=finca)
        .select_related("crew", "crew__work_day")
        .prefetch_related("lines")
    )
    if statuses is not None:
        qs = qs.filter(status__in=list(statuses))
    if date_from:
        qs = qs.filter(crew__work_day__work_date__gte=date_from)
    if date_to:
        qs = qs.filter(crew__work_day__work_date__lte=date_to)
    if payroll_period_id:
        qs = qs.filter(crew__work_day__payroll_period_id=payroll_period_id)
    return qs


def _report_jornales(report) -> Decimal:
    """Jornales de un reporte = Σ day_value de sus líneas (ausencias = 0)."""
    return sum((_q(line.day_value) for line in report.lines.all()), ZERO)


# --------------------------------------------------------------------------- #
# Rollups
# --------------------------------------------------------------------------- #

def field_labor_rollup(finca: OrgUnit, **filters) -> list[dict[str, Any]]:
    """Jornales reales por labor (agrupa por `labor_code` capturado)."""
    index = _labor_index(finca)
    jornales: dict[str, Decimal] = defaultdict(lambda: ZERO)
    reports_n: dict[str, int] = defaultdict(int)
    workers: dict[str, set[int]] = defaultdict(set)
    captured_name: dict[str, str] = {}

    for report in _reports_qs(finca, **filters):
        code = (report.labor_code or "").strip()
        key = code or "(sin labor)"
        jornales[key] += _report_jornales(report)
        reports_n[key] += 1
        if code and key not in captured_name:
            captured_name[key] = report.labor_name or ""
        for line in report.lines.all():
            workers[key].add(line.employee_id)

    out: list[dict[str, Any]] = []
    for key in sorted(jornales):
        labor = index.get(key)
        jorn = _money(jornales[key])
        rate = _q(labor.default_rate) if (labor and labor.default_rate is not None) else None
        labor_cost = _money(jorn * rate) if rate is not None else None
        out.append({
            "labor_code": key,
            "labor_name": (labor.name if labor else captured_name.get(key, "")),
            "matched": labor is not None,
            "category": (labor.category if labor else ""),
            "default_rate": (str(_money(rate)) if rate is not None else None),
            "jornales": str(jorn),
            "workers": len(workers[key]),
            "reports": reports_n[key],
            "labor_cost": (str(labor_cost) if labor_cost is not None else None),
        })
    return out


def field_zone_rollup(finca: OrgUnit, **filters) -> list[dict[str, Any]]:
    """Jornales reales por zona (agrupa por `zone_label` capturado)."""
    jornales: dict[str, Decimal] = defaultdict(lambda: ZERO)
    reports_n: dict[str, int] = defaultdict(int)
    for report in _reports_qs(finca, **filters):
        key = (report.zone_label or "").strip() or "(sin zona)"
        jornales[key] += _report_jornales(report)
        reports_n[key] += 1
    return [
        {"zone_label": z, "jornales": str(_money(jornales[z])), "reports": reports_n[z]}
        for z in sorted(jornales)
    ]


def reconcile_field_catalog(finca: OrgUnit, **filters) -> dict[str, Any]:
    """Calidad de dato: ¿qué `labor_code`/`zone_label` del campo existen en el catálogo?

    Cuenta todos los reportes (incluye DRAFT) para medir cobertura real del catálogo.
    """
    index = _labor_index(finca)
    all_qs = _reports_qs(finca, statuses=None, **{k: v for k, v in filters.items() if k != "statuses"})
    matched: set[str] = set()
    unmatched: set[str] = set()
    zones: set[str] = set()
    total = 0
    countable = 0
    for report in all_qs:
        total += 1
        if report.status in {s.value for s in COUNTABLE_STATUSES}:
            countable += 1
        code = (report.labor_code or "").strip()
        if code:
            (matched if code in index else unmatched).add(code)
        zone = (report.zone_label or "").strip()
        if zone:
            zones.add(zone)
    return {
        "countable_statuses": [s.value for s in COUNTABLE_STATUSES],
        "reports_total": total,
        "reports_countable": countable,
        "labors_matched": sorted(matched),
        "labors_unmatched": sorted(unmatched),
        "zones_seen": sorted(zones),
    }


# --------------------------------------------------------------------------- #
# Costeo real (asistencia real × tarifa + insumos)
# --------------------------------------------------------------------------- #

def _insumo_cost(finca: OrgUnit, *, season: str | None = None) -> Decimal:
    qs = InsumoApplication.objects.filter(work_order__finca=finca).exclude(
        work_order__status=WorkOrder.Status.CANCELLED
    )
    if season:
        qs = qs.filter(work_order__season_label=season)
    return _money(sum((_q(i.quantity) * _q(i.unit_cost) for i in qs.select_related("work_order")), ZERO))


def finca_real_cost_summary(finca: OrgUnit, *, season: str | None = None, **filters) -> dict[str, Any]:
    """Costeo de una finca: mano de obra desde asistencia de campo + insumos.

    F-04: ``real_labor_cost`` es la **asistencia REAL** (jornales efectivamente
    capturados en campo) valuada a la **tarifa estándar del catálogo de labores**
    (``Labor.default_rate``), NO al salario real de planilla. Es un costo de gestión
    por finca a tarifa estándar, no el costo nominal exacto; el cruce con el salario
    real de nómina queda como evolución futura.
    """
    labors = field_labor_rollup(finca, **filters)
    real_labor_cost = _money(sum(
        (Decimal(r["labor_cost"]) for r in labors if r["labor_cost"] is not None), ZERO
    ))
    jornales = _money(sum((Decimal(r["jornales"]) for r in labors), ZERO))
    insumo_cost = _insumo_cost(finca, season=season)
    total = _money(real_labor_cost + insumo_cost)
    profile = getattr(finca, "finca_profile", None)
    area = _q(profile.area_manzanas) if profile else ZERO
    unmatched = [r["labor_code"] for r in labors if not r["matched"]]
    return {
        "finca_id": finca.id,
        "finca_name": finca.name,
        "zona": (profile.zona if profile else "") or "(sin zona)",
        "jornales": str(jornales),
        "real_labor_cost": str(real_labor_cost),
        "insumo_cost": str(insumo_cost),
        "total_cost": str(total),
        "cost_per_manzana": str((total / area).quantize(CENT) if area else ZERO),
        "uncosted_labors": unmatched,
        "by_labor": labors,
    }


def company_real_cost_summary(company: OrgUnit, *, season: str | None = None, **filters) -> dict[str, Any]:
    """Consolida el costeo real de todas las fincas de la empresa, por finca y zona."""
    fincas = OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).order_by("name")
    by_finca: list[dict[str, Any]] = []
    by_zona: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for finca in fincas:
        s = finca_real_cost_summary(finca, season=season, **filters)
        by_finca.append({
            "finca_id": s["finca_id"], "finca_name": s["finca_name"], "zona": s["zona"],
            "jornales": s["jornales"], "real_labor_cost": s["real_labor_cost"],
            "insumo_cost": s["insumo_cost"], "total_cost": s["total_cost"],
        })
        by_zona[s["zona"]] += Decimal(s["total_cost"])
    return {
        "by_finca": by_finca,
        "by_zona": [{"zona": z, "total_cost": str(_money(t))} for z, t in sorted(by_zona.items())],
    }
