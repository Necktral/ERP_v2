"""Servicios de notificaciones: registro de tokens, emisión idempotente y consumo del outbox.

Consume `OutboxEvent`(source=FLEET) con idempotencia de consumidor vía `integration.InboxEvent`
(unique event_id+consumer), rutea con `fleet_router` y emite `NotificationRecord` a los usuarios
con el rol correcto en la empresa/sucursal. Idempotente extremo-a-extremo: `dedupe_key` por
(evento de origen, destinatario).
"""
from __future__ import annotations

from typing import Any, Optional

from django.db import transaction
from django.db.models import Subquery
from django.utils import timezone

from apps.modulos.audit.service_audit import emit_service_event
from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.rbac.models import RoleAssignment

from . import fleet_router
from .models import DeviceToken, NotificationRecord
from .senders import get_active_sender

CONSUMER = "notifications"


def register_device_token(*, user, company, platform: str, token: str) -> DeviceToken:
    obj, created = DeviceToken.objects.update_or_create(
        user=user, token=token,
        defaults={"company": company, "platform": platform, "is_active": True, "last_seen": timezone.now()},
    )
    emit_service_event(
        company=company,
        module="NOTIFICATIONS",
        event_type="NOTIF_DEVICE_REGISTERED",
        reason_code="NOTIF_OK",
        actor_user=user,
        subject_type="NOTIF_DEVICE",
        subject_id=str(obj.id),
        after_snapshot={"platform": obj.platform, "is_active": obj.is_active},
        metadata={"created": bool(created)},
    )
    return obj


def emit_notification(
    *, company, branch, recipient_user_id: int, event_type: str, title: str,
    body: str = "", payload: Optional[dict] = None, dedupe_key: str,
) -> NotificationRecord:
    """Crea (idempotente por dedupe_key) un NotificationRecord y lo entrega por el sender activo."""
    rec, created = NotificationRecord.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "company": company, "branch": branch, "recipient_user_id": recipient_user_id,
            "event_type": event_type, "title": title, "body": body, "payload_json": payload or {},
        },
    )
    if created:
        get_active_sender().send(rec)
    return rec


def notify_roles(
    *, company, branch, roles: list[str], event_type: str, title: str,
    body: str = "", payload: Optional[dict] = None, dedupe_prefix: str,
) -> list[NotificationRecord]:
    """Emite a todos los usuarios con alguno de `roles` activo en la empresa/sucursal."""
    org_ids = [company.id]
    if branch is not None:
        org_ids.append(branch.id)
    user_ids = (
        RoleAssignment.objects
        .filter(role__name__in=roles, org_unit_id__in=org_ids, is_active=True)
        .values_list("user_id", flat=True).distinct()
    )
    out: list[NotificationRecord] = []
    for uid in user_ids:
        out.append(emit_notification(
            company=company, branch=branch, recipient_user_id=uid, event_type=event_type,
            title=title, body=body, payload=payload, dedupe_key=f"{dedupe_prefix}:{uid}",
        ))
    return out


def dispatch_fleet_notifications(*, limit: int = 500) -> dict[str, int]:
    """Consume OutboxEvents FLEET pendientes → rutea → emite. Idempotente por InboxEvent + dedupe_key.

    N-02: solo recorre los eventos AÚN no procesados por este consumidor (excluye los que
    ya tienen InboxEvent PROCESSED) y acota por `limit` → deja de ser O(total) por corrida.
    """
    processed = emitted = 0
    done = InboxEvent.objects.filter(
        consumer=CONSUMER, status=InboxEvent.Status.PROCESSED
    ).values("event_id")
    qs = (
        OutboxEvent.objects.filter(source_module="FLEET")
        .exclude(event_id__in=Subquery(done))
        .order_by("id")[: int(limit)]
    )
    for ob in qs.iterator():
        with transaction.atomic():
            inbox, created = InboxEvent.objects.get_or_create(
                event_id=ob.event_id, consumer=CONSUMER,
                defaults={
                    "source_module": ob.source_module, "event_type": ob.event_type,
                    "payload": ob.payload, "status": InboxEvent.Status.RECEIVED,
                },
            )
            if not created and inbox.status == InboxEvent.Status.PROCESSED:
                continue
            data: dict[str, Any] = {}
            if isinstance(ob.payload, dict):
                data = ob.payload.get("data", ob.payload) if isinstance(ob.payload.get("data"), dict) else ob.payload
            routed = fleet_router.route(ob.event_type, data)
            if routed is not None:
                roles, title, body = routed
                recs = notify_roles(
                    company=ob.company, branch=ob.branch, roles=roles, event_type=ob.event_type,
                    title=title, body=body, payload=data, dedupe_prefix=str(ob.event_id),
                )
                emitted += len(recs)
            inbox.status = InboxEvent.Status.PROCESSED
            inbox.processed_at = timezone.now()
            inbox.save(update_fields=["status", "processed_at"])
            processed += 1
    return {"processed": processed, "emitted": emitted}
