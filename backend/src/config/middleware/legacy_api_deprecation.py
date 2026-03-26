from __future__ import annotations

from django.conf import settings

from config.routing_policy import legacy_header_config


class LegacyApiDeprecationMiddleware:
    """Inject deprecation headers for legacy public API prefixes."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.legacy_config = legacy_header_config(settings)

    def __call__(self, request):
        path = getattr(request, "path", "") or ""
        matched_prefix = next((prefix for prefix in self.legacy_config if path.startswith(prefix)), None)
        if matched_prefix:
            setattr(request, "_legacy_api_prefix", matched_prefix)
        response = self.get_response(request)
        if matched_prefix:
            if "Deprecation" not in response:
                response["Deprecation"] = "true"
            if "Sunset" not in response:
                cfg = self.legacy_config.get(matched_prefix, {})
                sunset = str(cfg.get("sunset") or "Mon, 22 Jun 2026 00:00:00 GMT").strip()
                response["Sunset"] = sunset
            if "Link" not in response:
                cfg = self.legacy_config.get(matched_prefix, {})
                successor = str(cfg.get("successor") or "/api/backend/")
                response["Link"] = f'<{successor}>; rel="successor-version"'
        return response
