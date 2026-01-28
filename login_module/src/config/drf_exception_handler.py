from __future__ import annotations

from datetime import datetime, timezone

from django.conf import settings
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, Throttled
from rest_framework.views import exception_handler as drf_exception_handler

from apps.audit.writer import write_event


def _actor_user(request):
    if request is None:
        return None
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def _subject_for_request(request):
    actor = _actor_user(request)
    if actor is not None:
        return ("USER", str(actor.id), actor)
    # Sin usuario autenticado: tratamos como contexto de sesión
    return ("SESSION", "", None)


def _utc_timestamp_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _extract_message(details) -> str:
    if isinstance(details, dict):
        detail = details.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail
        return "Solicitud inválida."
    if isinstance(details, list):
        return "Solicitud inválida."
    if isinstance(details, str) and details.strip():
        return details
    return "Solicitud inválida."


def _error_code_for(*, exc, status_code: int | None, details) -> str:
    if status_code == 401:
        return "POLICY_SCOPE_DENIED"
    if status_code == 403:
        return "POLICY_PERMISSION_DENIED"
    if status_code == 404:
        return "NOT_FOUND"
    if status_code == 409:
        return "CONFLICT"
    if status_code == 429:
        return "RATE_LIMITED"
    if status_code == 400:
        # DRF ValidationError suele serializar a dict/list
        return "VALIDATION_ERROR" if isinstance(details, (dict, list)) else "BAD_REQUEST"
    if status_code and status_code >= 500:
        return "INTERNAL_ERROR"
    return "ERROR"


def _build_error_envelope(*, request, status_code: int, exc, details) -> dict:
    request_id = getattr(request, "request_id", None) if request is not None else None
    return {
        "error": {
            "code": _error_code_for(exc=exc, status_code=status_code, details=details),
            "http_status": int(status_code),
            "message": _extract_message(details),
            "details": details,
            "request_id": request_id or "",
            "timestamp": _utc_timestamp_iso(),
        }
    }


def custom_exception_handler(exc, context):
    """
    Ruta A (contractual EAU):
    - 401/403/429 -> AuditEvent AUTH_ACCESS_DENIED con reason_code estándar
    - Incluye required_permission si la view lo inyecta en request.required_permission
    """
    response = drf_exception_handler(exc, context)
    request = (context or {}).get("request")

    # Fallback prod-safe para excepciones no manejadas por DRF
    if response is None:
        if settings.DEBUG:
            return None
        envelope = _build_error_envelope(request=request, status_code=500, exc=exc, details={"detail": "Error interno."})
        return Response(envelope, status=500)

    status_code = getattr(response, "status_code", None)

    # Solo auditamos estados de denegación (authz/authn/rate-limit)
    if status_code not in (401, 403, 429):
        # Igual normalizamos el formato de error
        if isinstance(getattr(response, "data", None), dict) and "error" in response.data:
            return response

        details = getattr(response, "data", None)
        if status_code is not None and int(status_code) >= 400:
            response.data = _build_error_envelope(
                request=request,
                status_code=int(status_code),
                exc=exc,
                details=details,
            )
        return response

    # Mapping contractual
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        reason_code = "POLICY_SCOPE_DENIED"
    elif isinstance(exc, PermissionDenied):
        reason_code = "POLICY_PERMISSION_DENIED"
    elif isinstance(exc, Throttled):
        reason_code = "RATE_LIMITED"
    else:
        # Fallback por status
        reason_code = "RATE_LIMITED" if status_code == 429 else "POLICY_SCOPE_DENIED"

    # Detalle (sin filtrar secretos; DRF detail suele ser seguro)
    try:
        detail = getattr(exc, "detail", None)
        detail = str(detail) if detail is not None else ""
    except Exception:
        detail = ""

    required_perm = getattr(request, "required_permission", "") if request else ""

    subject_type, subject_id, actor = _subject_for_request(request)

    metadata = {
        "status_code": status_code,
        "detail": detail,
    }
    if required_perm:
        metadata["required_permission"] = required_perm

    write_event(
        request=request,
        event_type="AUTH_ACCESS_DENIED",
        reason_code=reason_code,
        actor_user=actor,
        subject_type=subject_type,
        subject_id=subject_id,
        metadata=metadata,
    )
    if request is not None:
        setattr(request, "_audit_access_denied_written", True)

    # Envelope contractual
    if isinstance(getattr(response, "data", None), dict) and "error" in response.data:
        return response

    details = getattr(response, "data", None)
    if status_code is not None and int(status_code) >= 400:
        response.data = _build_error_envelope(
            request=request,
            status_code=int(status_code),
            exc=exc,
            details=details,
        )

    return response
