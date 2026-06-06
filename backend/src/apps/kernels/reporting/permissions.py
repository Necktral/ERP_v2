from __future__ import annotations

from collections.abc import Iterable

from django.conf import settings

from apps.modulos.rbac.selectors import get_effective_permissions_for_scope

from .exceptions import DatasetPermissionDenied, DatasetScopeError


def resolve_effective_permissions(*, user, company, branch, effective_permissions_override: Iterable[str] | None = None) -> set[str]:
    if effective_permissions_override is not None:
        return {str(code).strip() for code in list(effective_permissions_override) if str(code).strip()}
    if user is None or not getattr(user, "is_authenticated", False):
        raise DatasetPermissionDenied("Usuario no autenticado.")
    if company is None:
        raise DatasetScopeError("Contexto inválido: company requerida.")

    include_global = bool(getattr(settings, "RBAC_INCLUDE_GLOBAL_USERROLES", False))
    return set(
        get_effective_permissions_for_scope(
            user,
            company=company,
            branch=branch,
            include_global=include_global,
        )
    )


def ensure_permissions(
    *,
    user,
    company,
    branch,
    required_permissions: Iterable[str],
    effective_permissions_override: Iterable[str] | None = None,
) -> None:
    effective = resolve_effective_permissions(
        user=user,
        company=company,
        branch=branch,
        effective_permissions_override=effective_permissions_override,
    )
    required = {str(code).strip() for code in required_permissions if str(code).strip()}
    if "*" in effective:
        return
    missing = sorted(code for code in required if code not in effective)
    if missing:
        raise DatasetPermissionDenied(f"Permisos requeridos no satisfechos: {', '.join(missing)}")
