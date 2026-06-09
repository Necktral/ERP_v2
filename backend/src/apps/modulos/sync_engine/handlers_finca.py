"""Handlers de sincronización offline para Manejo de Fincas (#3 Fase 2).

Hace que las capturas de campo de finca sean **offline-first** sobre el motor
canónico `sync_engine` (Ed25519): el capataz/mandador captura sin red, el agente
encola los comandos y al reconectar el motor los aplica de forma idempotente.

Contrato del cliente (importante para no fallar offline):
- `occurred_at` del sobre = **reloj del dispositivo al ENVIAR** (el motor solo lo usa
  como guarda de desfase de reloj, ~6h). NO es la fecha de la labor.
- La **fecha real de la labor** viaja en el `payload` (`planned_date`/`done_date`),
  así un lote capturado hace días sincroniza sin ser rechazado por skew.
- Idempotencia: el motor deduplica por `command_id` (`AppliedCommand`); además
  `FINCA_LOG_WORK` usa `external_ref` (= `command_id` si no se envía) → doble capa.

Reusa los servicios de `apps.modulos.finca` (no reimplementa negocio); por eso el
edge `modulos.sync_engine -> modulos.finca` (integrador de alto nivel).
"""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.modulos.finca.models import Labor, Plot, WorkOrder
from apps.modulos.finca.services import apply_insumo, log_work, update_work_order
from apps.modulos.iam.models import OrgUnit

from .errors import SyncRejectError
from .registry import HandlerResult, register


def _attach_scope(*, request, company_id: int, branch_id: int | None) -> OrgUnit:
    """Adjunta company/branch (OrgUnit) al request y devuelve la finca (BRANCH)."""
    company = OrgUnit.objects.filter(
        id=company_id, unit_type=OrgUnit.UnitType.COMPANY, is_active=True
    ).first()
    if not company:
        raise SyncRejectError("FINCA_INVALID_SCOPE", {"company_id": "unknown"})
    request.company = company

    if branch_id is None:
        raise SyncRejectError("FINCA_INVALID_SCOPE", {"branch_id": "required"})
    finca = OrgUnit.objects.filter(
        id=branch_id, unit_type=OrgUnit.UnitType.BRANCH, parent_id=company_id, is_active=True
    ).first()
    if not finca:
        raise SyncRejectError("FINCA_INVALID_SCOPE", {"branch_id": "unknown"})
    request.branch = finca
    return finca


def _require_int(payload: dict[str, Any], key: str) -> int:
    v = payload.get(key)
    if v is None:
        raise SyncRejectError("FINCA_SCHEMA_INVALID", {key: "required"})
    try:
        return int(v)
    except (TypeError, ValueError):
        raise SyncRejectError("FINCA_SCHEMA_INVALID", {key: "invalid"})


def _scope_company_branch(ctx: dict[str, Any]):
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    finca = _attach_scope(request=request, company_id=company_id, branch_id=branch_id)
    return request, finca, ctx.get("actor_user")


@register("FINCA_LOG_WORK")
def handle_finca_log_work(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    """Registra una orden de trabajo / bitácora de labor capturada en campo."""
    request, finca, actor = _scope_company_branch(ctx)

    plot = Plot.objects.filter(id=_require_int(payload, "plot_id"), finca=finca).first()
    if plot is None:
        raise SyncRejectError("FINCA_NOT_FOUND", {"plot_id": payload.get("plot_id")})
    labor = (
        Labor.objects.filter(id=_require_int(payload, "labor_id"))
        .filter(Q(company=request.company) | Q(company__isnull=True))
        .first()
    )
    if labor is None:
        raise SyncRejectError("FINCA_NOT_FOUND", {"labor_id": payload.get("labor_id")})

    data = dict(payload)
    # external_ref garantiza idempotencia aunque el motor no dedupe (clave estable).
    data["external_ref"] = str(payload.get("external_ref") or ctx["command_id"])
    try:
        wo = log_work(finca, plot=plot, labor=labor, data=data, request=request, actor=actor)
    except (ValueError, ValidationError) as e:
        raise SyncRejectError("FINCA_SCHEMA_INVALID", {"error": str(e)})
    return {"refs": {"work_order_id": wo.id, "status": wo.status}}


@register("FINCA_UPDATE_WORKORDER")
def handle_finca_update_workorder(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    """Actualiza/cierra una orden de trabajo capturada en campo."""
    request, finca, actor = _scope_company_branch(ctx)
    wo = WorkOrder.objects.filter(id=_require_int(payload, "work_order_id"), finca=finca).first()
    if wo is None:
        raise SyncRejectError("FINCA_NOT_FOUND", {"work_order_id": payload.get("work_order_id")})
    try:
        wo = update_work_order(wo, data=payload, request=request, actor=actor)
    except (ValueError, ValidationError) as e:
        raise SyncRejectError("FINCA_SCHEMA_INVALID", {"error": str(e)})
    return {"refs": {"work_order_id": wo.id, "status": wo.status}}


@register("FINCA_APPLY_INSUMO")
def handle_finca_apply_insumo(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    """Registra un insumo (manual) consumido en una orden de trabajo."""
    request, finca, actor = _scope_company_branch(ctx)
    wo = WorkOrder.objects.filter(id=_require_int(payload, "work_order_id"), finca=finca).first()
    if wo is None:
        raise SyncRejectError("FINCA_NOT_FOUND", {"work_order_id": payload.get("work_order_id")})
    try:
        app = apply_insumo(wo, data=payload, request=request, actor=actor)
    except (ValueError, ValidationError) as e:
        raise SyncRejectError("FINCA_SCHEMA_INVALID", {"error": str(e)})
    return {"refs": {"insumo_id": app.id, "work_order_id": wo.id}}
