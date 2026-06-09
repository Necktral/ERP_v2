"""Adaptadores de envío de notificaciones.

- `RecordSender` (Fase A): canal in-app; la notificación ES el `NotificationRecord`.
- `FcmSender` (Fase B): además del registro in-app, hace push a los `DeviceToken` activos
  del destinatario vía FCM (HTTP). Best-effort: una falla de push NO desentrega el in-app.
  Tokens inválidos (UNREGISTERED/404) se desactivan automáticamente.

Usa la stdlib (`urllib`) para no agregar dependencias al backend. `get_active_sender()` elige
según `settings.NOTIFICATIONS_FCM_ENABLED` (default False): Fase A corre con RecordSender; al
configurar FCM se activa el push sin tocar el código que emite.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

from .models import DeviceToken, NotificationRecord, NotificationStatus

logger = logging.getLogger(__name__)

_INVALID_TOKEN_MARKERS = ("UNREGISTERED", "NOTREGISTERED", "INVALID_ARGUMENT", "INVALIDREGISTRATION")


def _mark_sent(record: NotificationRecord) -> None:
    record.status = NotificationStatus.SENT
    record.sent_at = timezone.now()
    record.save(update_fields=["status", "sent_at"])


class RecordSender:
    """Canal in-app: marcar SENT entrega la notificación (el registro es la notificación)."""

    def send(self, record: NotificationRecord) -> bool:
        _mark_sent(record)
        return True


class FcmSender:
    """In-app + push FCM best-effort a los dispositivos activos del destinatario."""

    def send(self, record: NotificationRecord) -> bool:
        _mark_sent(record)  # el in-app siempre se entrega
        try:
            push_to_user(
                user_id=record.recipient_user_id, title=record.title,
                body=record.body, data=record.payload_json or {},
            )
        except Exception:  # noqa: BLE001 — el push nunca desentrega el in-app
            logger.exception("fcm_push_failed", extra={"notification_id": record.id})
        return True


def _fcm_post(*, token: str, title: str, body: str, data: dict) -> tuple[int, str]:
    """POST a FCM. Devuelve (status_code, body_text). Aislado para test (mockeable)."""
    endpoint = getattr(settings, "NOTIFICATIONS_FCM_ENDPOINT", "")
    server_key = getattr(settings, "NOTIFICATIONS_FCM_SERVER_KEY", "")
    timeout = getattr(settings, "NOTIFICATIONS_FCM_TIMEOUT", 10)
    payload = json.dumps({
        "to": token,
        "notification": {"title": title, "body": body},
        "data": {k: str(v) for k, v in (data or {}).items()},
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=payload, method="POST",
        headers={"Authorization": f"key={server_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — endpoint de settings
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, (e.read() or b"").decode("utf-8", errors="ignore")


def _looks_invalid(status: int, text: str) -> bool:
    if status in (400, 404):
        return True
    return any(marker in (text or "").upper() for marker in _INVALID_TOKEN_MARKERS)


def push_to_user(*, user_id: int, title: str, body: str, data: dict) -> dict[str, int]:
    """Envía push a cada DeviceToken activo del usuario; desactiva los inválidos."""
    sent = deactivated = 0
    for tok in DeviceToken.objects.filter(user_id=user_id, is_active=True):
        try:
            status, text = _fcm_post(token=tok.token, title=title, body=body, data=data)
        except (urllib.error.URLError, OSError):
            logger.warning("fcm_request_error", extra={"token_id": tok.id})
            continue
        if _looks_invalid(status, text):
            tok.is_active = False
            tok.save(update_fields=["is_active"])
            deactivated += 1
        else:
            sent += 1
    return {"sent": sent, "deactivated": deactivated}


def get_active_sender():
    if getattr(settings, "NOTIFICATIONS_FCM_ENABLED", False):
        return FcmSender()
    return RecordSender()
