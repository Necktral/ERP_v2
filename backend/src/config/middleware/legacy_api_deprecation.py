from __future__ import annotations

from django.conf import settings


class LegacyApiDeprecationMiddleware:
    """Inject deprecation headers for legacy public API prefixes."""

    LEGACY_CONFIG = {
        "/api/fuel/": {
            "sunset": "Mon, 18 May 2026 00:00:00 GMT",
            "successor": "/api/backend/estacion-servicios/",
        },
        "/api/accounting/reports/": {
            "sunset": "",  # resolved from settings at runtime
            "successor": "/api/reporting/catalog/",
        },
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = getattr(request, "path", "") or ""
        matched_prefix = next((prefix for prefix in self.LEGACY_CONFIG if path.startswith(prefix)), None)
        if matched_prefix:
            setattr(request, "_legacy_api_prefix", matched_prefix)
        response = self.get_response(request)
        if matched_prefix:
            if "Deprecation" not in response:
                response["Deprecation"] = "true"
            if "Sunset" not in response:
                cfg = self.LEGACY_CONFIG.get(matched_prefix, {})
                sunset = str(cfg.get("sunset") or "").strip()
                if matched_prefix == "/api/accounting/reports/":
                    sunset = str(
                        getattr(settings, "REPORTING_LEGACY_ACCOUNTING_REPORTS_SUNSET", "")
                        or sunset
                        or "Mon, 22 Jun 2026 00:00:00 GMT"
                    ).strip()
                response["Sunset"] = sunset
            if "Link" not in response:
                cfg = self.LEGACY_CONFIG.get(matched_prefix, {})
                successor = str(cfg.get("successor") or "/api/backend/")
                response["Link"] = f'<{successor}>; rel="successor-version"'
        return response
