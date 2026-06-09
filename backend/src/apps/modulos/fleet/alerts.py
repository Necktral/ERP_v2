"""Evaluación de vencimientos de documentos y mantenimientos vencidos → OutboxEvent.

Publica eventos FLEET (`DocumentExpiring`/`DocumentExpired`/`MaintenanceDue`) que el módulo
`notifications` consume y entrega. Idempotente por transición de estado: sólo publica cuando
un documento PASA a por-vencer/vencido o cuando una regla PASA a vencida (`is_due` False→True);
re-correr no re-publica.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.modulos.integration.services import publish_outbox_event

from .models import (
    AssetMaintenanceState,
    AssetStatus,
    DocumentStatus,
    FleetAsset,
    FleetDocument,
)

_BUSY_STATUSES = {AssetStatus.MAINTENANCE_DUE, AssetStatus.IN_MAINTENANCE, AssetStatus.OUT_OF_SERVICE}


def evaluate_documents(*, company, horizon_days: int = 30, actor=None) -> list[dict[str, Any]]:
    today = timezone.localdate()
    horizon = today + timedelta(days=horizon_days)
    flagged: list[dict[str, Any]] = []
    qs = (
        FleetDocument.objects.filter(company=company)
        .exclude(expiry_date__isnull=True)
        .select_related("asset", "driver")
    )
    for doc in qs:
        expiry = doc.expiry_date
        if expiry is None:  # el queryset ya excluye nulls; guarda defensiva para el tipado
            continue
        if expiry < today:
            new_status = DocumentStatus.EXPIRED
        elif expiry <= horizon:
            new_status = DocumentStatus.EXPIRING
        else:
            new_status = DocumentStatus.VALID
        if new_status == doc.status:
            continue
        doc.status = new_status
        doc.save(update_fields=["status", "updated_at"])
        if new_status in (DocumentStatus.EXPIRING, DocumentStatus.EXPIRED):
            asset = doc.asset if doc.asset_id else None
            driver = doc.driver if doc.driver_id else None
            data = {
                "doc_id": doc.id, "doc_type": doc.doc_type, "expiry_date": expiry.isoformat(),
                "asset_code": asset.code if asset else None,
                "driver_name": driver.full_name if driver else None,
            }
            event = "DocumentExpired" if new_status == DocumentStatus.EXPIRED else "DocumentExpiring"
            publish_outbox_event(
                source_module="FLEET", event_type=event, payload=data, company=company,
                branch=asset.branch if asset else None, actor_user=actor,
            )
            flagged.append({"doc_id": doc.id, "status": new_status, "event": event})
    return flagged


def evaluate_maintenance(*, company, actor=None) -> list[dict[str, Any]]:
    flagged: list[dict[str, Any]] = []
    states = (
        AssetMaintenanceState.objects
        .filter(asset__company=company, is_due=False, rule__is_active=True)
        .select_related("asset", "rule", "rule__maintenance_type")
    )
    for st in states:
        asset: FleetAsset = st.asset
        if asset.status == AssetStatus.RETIRED:
            continue
        due = (
            (st.next_due_km is not None and asset.current_odometer_km >= st.next_due_km)
            or (st.next_due_hours is not None and asset.current_hourmeter >= st.next_due_hours)
            or (st.next_due_date is not None and timezone.localdate() >= st.next_due_date)
        )
        if not due:
            continue
        st.is_due = True
        st.last_flagged_at = timezone.now()
        st.save(update_fields=["is_due", "last_flagged_at"])
        if asset.status not in _BUSY_STATUSES:
            asset.status = AssetStatus.MAINTENANCE_DUE
            asset.save(update_fields=["status", "updated_at"])
        data = {
            "asset_id": asset.id, "asset_code": asset.code, "asset_name": asset.name,
            "maintenance_type": st.rule.maintenance_type.name, "rule_id": st.rule_id,
        }
        publish_outbox_event(
            source_module="FLEET", event_type="MaintenanceDue", payload=data,
            company=company, branch=asset.branch, actor_user=actor,
        )
        flagged.append({"asset_id": asset.id, "rule_id": st.rule_id})
    return flagged


def run_fleet_alerts(*, company, horizon_days: int = 30, actor=None) -> dict[str, Any]:
    docs = evaluate_documents(company=company, horizon_days=horizon_days, actor=actor)
    maint = evaluate_maintenance(company=company, actor=actor)
    return {"documents": docs, "maintenance": maint}
