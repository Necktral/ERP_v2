from __future__ import annotations

from rest_framework.throttling import ScopedRateThrottle


class DeviceScopedRateThrottle(ScopedRateThrottle):
    """Throttle por device_id si existe, fallback a IP."""

    def get_cache_key(self, request, view):
        scope = getattr(view, "throttle_scope", None)
        if not scope:
            return None

        device_id = (request.META.get("HTTP_X_DEVICE_ID") or "").strip()
        ident = device_id or self.get_ident(request)
        if not ident:
            return None

        return self.cache_format % {"scope": scope, "ident": ident}
