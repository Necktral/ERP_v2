"""Servicios de la capa de Actividad/Tiempo.

Operaciones idempotentes y transaccionales para dispositivos, sesiones de uso,
telemetría de actividad y marcas de tiempo trabajado.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.modulos.common.domain_errors import DomainError

from .models import ActivityEvent, DeviceRegistry, UserSession, WorkSession


class WorkSessionAlreadyOpenError(DomainError):
    default_code = "WORK_SESSION_ALREADY_OPEN"


# --- Dispositivos -----------------------------------------------------------

def register_or_touch_device(
    *, user, fingerprint: str, label: str = "", platform: str = "", now=None
) -> DeviceRegistry:
    now = now or timezone.now()
    device, created = DeviceRegistry.objects.get_or_create(
        user=user,
        fingerprint=fingerprint,
        defaults={
            "label": label,
            "platform": platform or DeviceRegistry._meta.get_field("platform").default,
            "first_seen_at": now,
            "last_seen_at": now,
        },
    )
    if not created:
        update_fields = ["last_seen_at"]
        device.last_seen_at = now
        if label and device.label != label:
            device.label = label
            update_fields.append("label")
        if platform and device.platform != platform:
            device.platform = platform
            update_fields.append("platform")
        device.save(update_fields=update_fields)
    return device


def revoke_device(*, device: DeviceRegistry, now=None) -> DeviceRegistry:
    if device.revoked_at is None:
        device.revoked_at = now or timezone.now()
        device.save(update_fields=["revoked_at"])
    return device


# --- Sesiones de uso --------------------------------------------------------

def start_user_session(
    *,
    user,
    ip=None,
    user_agent: str = "",
    device: DeviceRegistry | None = None,
    company_id: int | None = None,
    branch_id: int | None = None,
    refresh_jti: str = "",
    now=None,
) -> UserSession:
    now = now or timezone.now()
    return UserSession.objects.create(
        user=user,
        device=device,
        ip=ip,
        user_agent=user_agent or "",
        company_id=company_id,
        branch_id=branch_id,
        refresh_jti=refresh_jti or "",
        started_at=now,
        last_seen_at=now,
    )


def touch_user_session(*, session: UserSession, now=None) -> UserSession:
    session.last_seen_at = now or timezone.now()
    session.save(update_fields=["last_seen_at"])
    return session


def end_user_session(*, session: UserSession, reason: str = UserSession.EndReason.LOGOUT, now=None) -> UserSession:
    if session.ended_at is None:
        session.ended_at = now or timezone.now()
        session.end_reason = reason
        session.save(update_fields=["ended_at", "end_reason"])
    return session


# --- Telemetría de actividad ------------------------------------------------

def record_activity(
    *,
    user=None,
    session: UserSession | None = None,
    device: DeviceRegistry | None = None,
    company_id: int | None = None,
    branch_id: int | None = None,
    route: str = "",
    method: str = "",
    status_code: int = 0,
    duration_ms: int = 0,
    request_id: str = "",
    now=None,
) -> ActivityEvent:
    return ActivityEvent.objects.create(
        user=user,
        session=session,
        device=device,
        company_id=company_id,
        branch_id=branch_id,
        route=(route or "")[:255],
        method=(method or "")[:16],
        status_code=int(status_code or 0),
        duration_ms=max(0, int(duration_ms or 0)),
        request_id=(request_id or "")[:64],
        occurred_at=now or timezone.now(),
    )


# --- Tiempo trabajado -------------------------------------------------------

@transaction.atomic
def clock_in(*, user, company, branch=None, source: str = WorkSession.Source.WEB, note: str = "", now=None) -> WorkSession:
    open_exists = (
        WorkSession.objects.select_for_update()
        .filter(user=user, company=company, clock_out__isnull=True)
        .exists()
    )
    if open_exists:
        raise WorkSessionAlreadyOpenError(
            "El usuario ya tiene una sesión de trabajo abierta en esta empresa.",
            context={"user_id": getattr(user, "id", None), "company_id": getattr(company, "id", None)},
        )
    return WorkSession.objects.create(
        user=user, company=company, branch=branch, source=source, note=note or "", clock_in=now or timezone.now()
    )


def clock_out(*, work_session: WorkSession, now=None) -> WorkSession:
    if work_session.clock_out is None:
        work_session.clock_out = now or timezone.now()
        work_session.save(update_fields=["clock_out"])
    return work_session
