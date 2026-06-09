"""Adaptadores de envío. Fase A: RecordSender (in-app = el propio registro).

Fase B agrega `FcmSender` (push real) seleccionado por setting; el dominio no cambia.
"""
from __future__ import annotations

from django.utils import timezone

from .models import NotificationRecord, NotificationStatus


class RecordSender:
    """Canal in-app: la notificación ES el `NotificationRecord`; marcar SENT lo entrega."""

    def send(self, record: NotificationRecord) -> bool:
        record.status = NotificationStatus.SENT
        record.sent_at = timezone.now()
        record.save(update_fields=["status", "sent_at"])
        return True


def get_active_sender():
    # Fase B: devolver FcmSender() si settings.NOTIFICATIONS_FCM_ENABLED.
    return RecordSender()
