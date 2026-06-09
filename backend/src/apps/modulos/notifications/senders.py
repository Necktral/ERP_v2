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
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import DeviceToken, NotificationRecord, NotificationStatus

logger = logging.getLogger(__name__)

_INVALID_TOKEN_MARKERS = ("UNREGISTERED", "NOTREGISTERED", "INVALID_ARGUMENT", "INVALIDREGISTRATION")

# N-01: la API legacy de FCM (/fcm/send, "Authorization: key=") fue descontinuada por
# Google. Se usa FCM HTTP v1 (/v1/projects/{id}/messages:send) con un bearer OAuth2
# acuñado desde la service account (JWT RS256 → token endpoint). Cache del token en módulo.
_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
_fcm_token_cache: dict[str, Any] = {"access_token": "", "exp": 0.0}


def _fcm_service_account() -> dict:
    """Service account FCM desde settings (dict o ruta JSON)."""
    sa = getattr(settings, "NOTIFICATIONS_FCM_SERVICE_ACCOUNT", None)
    if isinstance(sa, dict):
        return sa
    if isinstance(sa, str) and sa:
        with open(sa, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _fcm_access_token() -> str:
    """Bearer OAuth2 para FCM v1 (cacheado hasta ~5 min antes de expirar)."""
    now = time.time()
    cached = _fcm_token_cache
    if cached["access_token"] and float(cached["exp"]) - 300 > now:
        return str(cached["access_token"])

    import jwt  # PyJWT (RS256 con cryptography); disponibles en el backend.

    sa = _fcm_service_account()
    client_email = sa.get("client_email", "")
    private_key = sa.get("private_key", "")
    if not client_email or not private_key:
        raise RuntimeError("NOTIFICATIONS_FCM_SERVICE_ACCOUNT incompleta (client_email/private_key).")

    iat = int(now)
    assertion = jwt.encode(
        {
            "iss": client_email,
            "scope": _FCM_SCOPE,
            "aud": _GOOGLE_TOKEN_URI,
            "iat": iat,
            "exp": iat + 3600,
        },
        private_key,
        algorithm="RS256",
    )
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode("utf-8")
    req = urllib.request.Request(
        _GOOGLE_TOKEN_URI, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # FCM: endpoint HTTPS fijo de Google; esquema no controlable por el usuario.
    with urllib.request.urlopen(req, timeout=getattr(settings, "NOTIFICATIONS_FCM_TIMEOUT", 10)) as resp:  # noqa: S310  # nosec B310
        tok = json.loads(resp.read().decode("utf-8"))
    access_token = tok.get("access_token", "")
    _fcm_token_cache["access_token"] = access_token
    _fcm_token_cache["exp"] = now + float(tok.get("expires_in", 3600))
    return access_token


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
    """POST a FCM HTTP v1. Devuelve (status_code, body_text). Aislado para test (mockeable)."""
    project_id = getattr(settings, "NOTIFICATIONS_FCM_PROJECT_ID", "") or _fcm_service_account().get("project_id", "")
    timeout = getattr(settings, "NOTIFICATIONS_FCM_TIMEOUT", 10)
    endpoint = (
        getattr(settings, "NOTIFICATIONS_FCM_ENDPOINT", "")
        or f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    )
    access_token = _fcm_access_token()
    payload = json.dumps({
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": {k: str(v) for k, v in (data or {}).items()},
        }
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=payload, method="POST",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    )
    try:
        # FCM: endpoint HTTPS de settings; esquema no controlable por el usuario.
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310
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
