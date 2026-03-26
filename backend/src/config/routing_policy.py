from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RoutingDomainPolicy:
    domain_key: str
    owner_domain: str
    canonical_prefix: str
    include_modules: tuple[str, ...] = ()
    allowed_legacy_prefixes: tuple[str, ...] = ()
    deprecation_mode: str = "none"
    sunset_header: str = ""
    sunset_setting_name: str | None = None
    successor_link: str | None = None


def _normalize_prefix(prefix: str) -> str:
    value = prefix.strip()
    if not value.startswith("/"):
        value = f"/{value}"
    if not value.endswith("/"):
        value = f"{value}/"
    return value


ROUTING_POLICY: tuple[RoutingDomainPolicy, ...] = (
    RoutingDomainPolicy(
        domain_key="fuel",
        owner_domain="estacion_servicios",
        canonical_prefix="/api/fuel/",
        include_modules=("apps.modulos.estacion_servicios.urls",),
        allowed_legacy_prefixes=(
            "/api/backend/fuel/",
            "/api/backend/estacion-servicios/",
        ),
        deprecation_mode="headers",
        sunset_header="Mon, 18 May 2026 00:00:00 GMT",
        successor_link="/api/fuel/",
    ),
    RoutingDomainPolicy(
        domain_key="billing",
        owner_domain="facturacion",
        canonical_prefix="/api/billing/",
        include_modules=("apps.kernels.facturacion.urls",),
        allowed_legacy_prefixes=("/api/legacy/billing/",),
        deprecation_mode="headers",
        sunset_header="Mon, 22 Jun 2026 00:00:00 GMT",
        successor_link="/api/billing/",
    ),
    RoutingDomainPolicy(
        domain_key="accounting_reports_legacy",
        owner_domain="reporting",
        canonical_prefix="/api/reporting/",
        allowed_legacy_prefixes=("/api/accounting/reports/",),
        deprecation_mode="headers",
        sunset_setting_name="REPORTING_LEGACY_ACCOUNTING_REPORTS_SUNSET",
        successor_link="/api/reporting/catalog/",
    ),
)


def iter_routing_policy() -> Iterable[RoutingDomainPolicy]:
    return ROUTING_POLICY


def legacy_header_config(settings_obj: object | None = None) -> dict[str, dict[str, str]]:
    config: dict[str, dict[str, str]] = {}
    for policy in ROUTING_POLICY:
        if policy.deprecation_mode != "headers":
            continue
        successor = (policy.successor_link or policy.canonical_prefix or "").strip() or "/api/"
        sunset = (policy.sunset_header or "").strip()
        if policy.sunset_setting_name and settings_obj is not None:
            sunset = str(getattr(settings_obj, policy.sunset_setting_name, "") or sunset).strip()
        for raw_prefix in policy.allowed_legacy_prefixes:
            prefix = _normalize_prefix(raw_prefix)
            config[prefix] = {
                "sunset": sunset,
                "successor": successor,
                "owner_domain": policy.owner_domain,
                "domain_key": policy.domain_key,
            }
    return config


def routing_prefix_contract() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for policy in ROUTING_POLICY:
        out[policy.domain_key] = {
            "owner_domain": policy.owner_domain,
            "canonical_prefix": _normalize_prefix(policy.canonical_prefix),
            "include_modules": list(policy.include_modules),
            "allowed_legacy_prefixes": [_normalize_prefix(p) for p in policy.allowed_legacy_prefixes],
            "deprecation_mode": policy.deprecation_mode,
            "successor_link": policy.successor_link or policy.canonical_prefix,
            "sunset_header": policy.sunset_header,
            "sunset_setting_name": policy.sunset_setting_name,
        }
    return out
