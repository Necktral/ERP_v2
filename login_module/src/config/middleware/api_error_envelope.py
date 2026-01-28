from __future__ import annotations

import json
from datetime import datetime, timezone


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


def _error_code_for(*, status_code: int, details) -> str:
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
        return "VALIDATION_ERROR" if isinstance(details, (dict, list)) else "BAD_REQUEST"
    if status_code >= 500:
        return "INTERNAL_ERROR"
    return "ERROR"


def _build_error_envelope(*, request, status_code: int, details) -> dict:
    request_id = getattr(request, "request_id", "") or ""
    return {
        "error": {
            "code": _error_code_for(status_code=status_code, details=details),
            "http_status": int(status_code),
            "message": _extract_message(details),
            "details": details,
            "request_id": request_id,
            "timestamp": _utc_timestamp_iso(),
        }
    }


class ApiErrorEnvelopeMiddleware:
    """Normaliza errores JSON al envelope contractual.

    Cubre casos donde el código retorna manualmente:
    - JsonResponse({"detail": ...}, status=4xx)
    - Response({"detail": ...}, status=4xx)

    No toca respuestas no-JSON.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code < 400:
            return response

        path = getattr(request, "path", "") or ""
        if not path.startswith("/api/"):
            return response

        # DRF Response: podemos operar sobre response.data
        if hasattr(response, "data"):
            data = getattr(response, "data", None)
            if isinstance(data, dict) and "error" in data:
                return response
            response.data = _build_error_envelope(request=request, status_code=status_code, details=data)
            if hasattr(response, "render"):
                try:
                    response.render()
                except Exception:
                    pass
            return response

        # Django JsonResponse / HttpResponse JSON: operar sobre content
        content_type = (response.get("Content-Type") or "").lower()
        if "application/json" not in content_type:
            return response

        try:
            raw = response.content.decode("utf-8") if getattr(response, "content", None) else ""
            data = json.loads(raw) if raw else None
        except Exception:
            return response

        if isinstance(data, dict) and "error" in data:
            return response

        envelope = _build_error_envelope(request=request, status_code=status_code, details=data)
        response.content = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        return response
