"""Handlers de sync_engine para captura de campo de flota (offline-first).

Permite que la app móvil (offline en finca) encole lecturas de medidor firmadas por el
dispositivo y las sincronice idempotentemente. Reusa `fleet.services.record_meter_reading`
(misma lógica que el endpoint HTTP, incluida la guarda de salto >500 km). La idempotencia
extremo-a-extremo la garantiza `AppliedCommand` (command_id) del propio sync_engine.

Fase A.2 agregará aquí FLEET_LOG_CHECKLIST / FLEET_REPORT_DEFECT (mismo patrón).
"""
from __future__ import annotations

from typing import Any

from apps.modulos.fleet.models import FleetAsset
from apps.modulos.fleet.services import record_meter_reading
from apps.modulos.iam.models import OrgUnit

from .errors import SyncRejectError
from .registry import HandlerResult, register


def _require_int(payload: dict[str, Any], key: str) -> int:
    v = payload.get(key, None)
    if v is None:
        raise SyncRejectError("FLEET_SCHEMA_INVALID", {key: "required"})
    try:
        return int(v)
    except (TypeError, ValueError):
        raise SyncRejectError("FLEET_SCHEMA_INVALID", {key: "invalid"})


def _attach_scope(*, request, company_id: int, branch_id: int | None) -> OrgUnit:
    company = OrgUnit.objects.filter(
        id=company_id, unit_type=OrgUnit.UnitType.COMPANY, is_active=True
    ).first()
    if not company:
        raise SyncRejectError("FLEET_INVALID_SCOPE", {"company_id": "unknown"})
    request.company = company
    branch = None
    if branch_id is not None:
        branch = OrgUnit.objects.filter(id=branch_id, parent_id=company_id).first()
        if not branch:
            raise SyncRejectError("FLEET_INVALID_SCOPE", {"branch_id": "unknown"})
    request.branch = branch
    return company


@register("FLEET.METER.RECORD")
@register("FLEET_RECORD_METER")
def handle_fleet_record_meter(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    """Registra una lectura de odómetro/horómetro capturada en campo."""
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    _attach_scope(request=request, company_id=company_id, branch_id=branch_id)

    asset_id = _require_int(payload, "asset_id")
    asset = FleetAsset.objects.filter(id=asset_id, company_id=company_id).first()
    if asset is None:
        raise SyncRejectError("FLEET_NOT_FOUND", {"asset_id": asset_id})

    odometer_km = payload.get("odometer_km")
    hourmeter = payload.get("hourmeter")
    if odometer_km is None and hourmeter is None:
        raise SyncRejectError("FLEET_SCHEMA_INVALID", {"detail": "odometer_km o hourmeter requerido"})

    res = record_meter_reading(
        request=request, actor=ctx.get("actor_user"), asset=asset,
        odometer_km=odometer_km, hourmeter=hourmeter,
    )
    return {
        "refs": {
            "asset_id": asset.id,
            "verified": res["verified"],
            "current_odometer_km": res["current_odometer_km"],
            "current_hourmeter": res["current_hourmeter"],
        }
    }
