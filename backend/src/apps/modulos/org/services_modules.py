"""Lógica de habilitación de módulos por empresa.

Resuelve el estado efectivo (catálogo ⊕ overrides) y aplica cambios self-service
con validación de invariantes (códigos conocidos, no togglear core, integridad del
grafo de dependencias) y traza de auditoría.
"""

from __future__ import annotations

from typing import Iterable, TypedDict

from django.db import transaction

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit

from .models import CompanyModule
from .module_catalog import core_codes, default_state, get_catalog, get_spec, is_known


class ModuleDependencyError(Exception):
    """Conflicto en el grafo de dependencias (mapea a HTTP 409)."""


class ModuleChange(TypedDict):
    code: str
    is_enabled: bool


def resolve_company_modules(company: OrgUnit) -> dict[str, bool]:
    """Estado efectivo de módulos de la empresa: defaults del catálogo ⊕ overrides.

    Los módulos core son siempre ``True``. La ausencia de fila ``CompanyModule``
    deja el ``default_enabled`` del catálogo.
    """
    state = default_state()
    overrides = CompanyModule.objects.filter(company=company).values_list("module_code", "is_enabled")
    for code, enabled in overrides:
        if code in state and code not in core_codes():
            state[code] = bool(enabled)
    for code in core_codes():
        state[code] = True
    return state


def enabled_codes(company: OrgUnit) -> list[str]:
    """Lista de códigos habilitados, en orden de presentación del catálogo."""
    state = resolve_company_modules(company)
    return [spec.code for spec in get_catalog() if state.get(spec.code)]


def allowed_module_codes(permissions: Iterable[str]) -> list[str]:
    """Códigos de módulo "permitidos" por RBAC, en el espacio del catálogo.

    Deriva de ``MODULE_CATALOG.permission_prefixes`` (anticipa el follow-up DRY que
    reemplaza ``accounts._MODULE_PERMISSION_PREFIXES``). Permite cruzar con
    ``enabled_codes`` en un mismo espacio de claves para obtener los efectivos.
    """
    perms = set(permissions)
    out: list[str] = []
    for spec in get_catalog():
        if any(p.startswith(prefix) for prefix in spec.permission_prefixes for p in perms):
            out.append(spec.code)
    return out


def _validate_dependency_integrity(target: dict[str, bool]) -> None:
    """Verifica el grafo de dependencias sobre el estado resultante.

    - Un módulo habilitado exige todas sus dependencias habilitadas.
    - No se puede deshabilitar un módulo del que depende otro habilitado.
    """
    for code, is_on in target.items():
        spec = get_spec(code)
        if not spec:
            continue
        if is_on:
            for dep in spec.depends_on:
                if not target.get(dep, False):
                    raise ModuleDependencyError(
                        f"'{code}' requiere '{dep}' habilitado."
                    )
        else:
            for other_code, other_on in target.items():
                if not other_on:
                    continue
                other_spec = get_spec(other_code)
                if other_spec and code in other_spec.depends_on:
                    raise ModuleDependencyError(
                        f"No se puede deshabilitar '{code}': '{other_code}' depende de él."
                    )


@transaction.atomic
def set_company_modules(
    *,
    company: OrgUnit,
    changes: Iterable[ModuleChange],
    request,
    actor,
) -> dict[str, bool]:
    """Aplica un batch de cambios de habilitación.

    Valida códigos (``ValueError`` → 400) y dependencias
    (``ModuleDependencyError`` → 409), hace upsert idempotente, escribe un único
    evento de auditoría ``ORG_MODULES_UPDATED`` y retorna el estado resuelto.
    """
    before = resolve_company_modules(company)

    normalized: dict[str, bool] = {}
    for change in changes:
        code = str(change.get("code", "")).strip()
        if not is_known(code):
            raise ValueError(f"Módulo desconocido: {code}")
        if code in core_codes():
            raise ValueError(f"El módulo core '{code}' no es configurable.")
        normalized[code] = bool(change["is_enabled"])

    if not normalized:
        return before

    target = dict(before)
    target.update(normalized)
    _validate_dependency_integrity(target)

    for code, is_enabled in normalized.items():
        row, _created = CompanyModule.objects.get_or_create(
            company=company,
            module_code=code,
            defaults={"is_enabled": is_enabled, "updated_by": actor},
        )
        if row.is_enabled != is_enabled or row.updated_by_id != getattr(actor, "id", None):
            row.is_enabled = is_enabled
            row.updated_by = actor
            row.save(update_fields=["is_enabled", "updated_by", "updated_at"])

    after = resolve_company_modules(company)

    write_event(
        request=request,
        module="ORG",
        event_type="ORG_MODULES_UPDATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="COMPANY_MODULE",
        subject_id=str(company.id),
        before_snapshot=before,
        after_snapshot=after,
        metadata={"changes": normalized},
    )
    return after
