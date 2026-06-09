"""Permiso DRF de habilitación de módulo por empresa (enforcement).

Convierte el registro `CompanyModule` (advisory) en un gate real: niega el
acceso (403) cuando el módulo no está habilitado para `request.company`.

Compone con `rbac_permission`: una vista gateada declara ambos, p. ej.

    permission_classes = [require_module("payroll"), rbac_permission("nomina.sheet.read")]

`require_module` primero hace que un módulo deshabilitado responda con el
mensaje de módulo (antes que el de permiso). El acceso sigue gobernado por
RBAC; este permiso solo añade la capa "¿la empresa ocupa el módulo?".

Adopción (rollout, por módulo y con su dueño): añadir `require_module(code)`
a las vistas del módulo y ajustar sus tests (las empresas sin override usan el
default del catálogo: core/base ON, verticales OFF).
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

from .module_catalog import is_known
from .services_modules import resolve_company_modules


def _trace(request, key: str, value) -> None:
    """Deja rastro en request y en su _request crudo (paridad con rbac_permission)."""
    for target in (request, getattr(request, "_request", None)):
        if target is None:
            continue
        try:
            setattr(target, key, value)
        except (AttributeError, TypeError):
            pass


def require_module(code: str):
    """Factory DRF: gatea una vista al módulo `code` habilitado en la empresa activa.

    Valida `code` contra el catálogo al definir la vista (falla rápido ante typos).
    """
    if not is_known(code):
        raise ValueError(f"require_module: módulo desconocido '{code}'")

    class _ModuleEnabledPermission(BasePermission):
        message = f"El módulo '{code}' no está habilitado para esta empresa."

        def has_permission(self, request, view) -> bool:
            _trace(request, "required_module", code)

            company = getattr(request, "company", None)
            if company is None:
                return False

            state = resolve_company_modules(company)
            enabled = bool(state.get(code, False))
            if not enabled:
                _trace(request, "required_module_denied", code)
            return enabled

    return _ModuleEnabledPermission
