"""Ruteo de eventos FLEET → roles destino + plantilla.

Mapa declarativo evento→(roles, título, constructor de cuerpo). En Fase A se usan los
eventos de vencimiento de documentos y mantenimiento vencido. Los demás del plan
(VehicleBlocked, DefectReported, WorkOrderAssigned, InspectionFailed,
MechanicalAlertRaised) se agregan cuando lleguen sus cortes (Fase A.2/B/C).
"""
from __future__ import annotations

from typing import Any, Optional

_SUPERVISION = ["fleet_supervisor", "fleet_manager"]


def _maintenance_body(data: dict[str, Any]) -> str:
    asset = data.get("asset_code") or data.get("asset_name") or data.get("asset_id") or "activo"
    mtype = data.get("maintenance_type") or "mantenimiento"
    return f"{asset}: {mtype} vencido."


def _doc_body(data: dict[str, Any]) -> str:
    asset = data.get("asset_code") or data.get("driver_name") or "registro"
    doc = data.get("doc_type") or "documento"
    exp = data.get("expiry_date") or ""
    return f"{asset}: {doc} vence {exp}.".strip()


_ROUTING = {
    "MaintenanceDue": (_SUPERVISION, "Mantenimiento vencido", _maintenance_body),
    "DocumentExpiring": (_SUPERVISION, "Documento por vencer", _doc_body),
    "DocumentExpired": (_SUPERVISION, "Documento vencido", _doc_body),
}


def route(event_type: str, data: dict[str, Any]) -> Optional[tuple[list[str], str, str]]:
    """Devuelve (roles, título, cuerpo) o None si el evento no se notifica en esta fase."""
    entry = _ROUTING.get(event_type)
    if entry is None:
        return None
    roles, title, body_fn = entry
    return roles, title, body_fn(data if isinstance(data, dict) else {})
