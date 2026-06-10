"""Seed idempotente de puestos agrícolas (HR) por empresa — v0.1.

Concatena el catálogo de puestos con el seed RBAC **sin mezclar dominios**: RBAC es global
(roles/permisos); los puestos (`JobPosition`) son **por empresa**. Este seed crea los puestos y
los mapea (`PositionRoleMap`) a roles RBAC **ya existentes** (sembrados por `seed_rbac_v01`). No
crea empleados, ni nómina, ni eventos económicos. Idempotente: no borra ni duplica.

**Habilitar/deshabilitar:** los puestos nacen **activos**; `disable_codes`/`enable_codes` fuerzan el
`is_active`. En re-corridas, el `is_active` de un puesto **NO se pisa** salvo que un flag lo nombre
explícitamente (respeta el toggle manual del operador). `only_codes` restringe el alcance.

**Multi-cargo:** este seed no lo gestiona — ya lo resuelve `reconcile_employee_roles` haciendo la
unión de los roles de todas las asignaciones activas de un empleado.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from django.db import transaction

from apps.modulos.iam.models import OrgUnit
from apps.modulos.rbac.models import Role

from .models import JobPosition, PositionRoleMap

_BRANCH = PositionRoleMap.ScopeMode.BRANCH
_COMPANY = PositionRoleMap.ScopeMode.COMPANY


@dataclass(frozen=True)
class PositionSpec:
    code: str
    name: str
    role: str = ""  # nombre del rol RBAC; "" = el puesto NO otorga acceso al sistema
    scope: str = _BRANCH  # solo aplica si role != ""


# Catálogo CONGELADO de puestos agrícolas v0.1. Nombres canónicos (tilde en display); códigos
# ASCII estables. Cambiar esta lista es una decisión de diseño, no un parámetro de runtime.
POSITION_CATALOG: tuple[PositionSpec, ...] = (
    PositionSpec("FNC-N1-010", "Gerente Agrícola", "finca_mandador", _COMPANY),
    PositionSpec("FNC-N2-010", "Administrador de Finca", "finca_mandador", _BRANCH),
    PositionSpec("FNC-N2-020", "Mandador", "finca_mandador", _BRANCH),
    PositionSpec("FNC-N2-030", "Capataz", "finca_capataz", _BRANCH),
    PositionSpec("FNC-N3-010", "Técnico Agrónomo", "finca_capataz", _BRANCH),
    PositionSpec("FNC-N3-020", "Encargado de Insumos Agrícolas", "warehouse_operator", _BRANCH),
    PositionSpec("FNC-N4-010", "Operador de Maquinaria Agrícola", "fleet_driver", _BRANCH),
    PositionSpec("FNC-N4-020", "Aplicador de Agroquímicos"),
    PositionSpec("FNC-N5-010", "Trabajador de Campo Permanente"),
    PositionSpec("FNC-N5-020", "Jornalero (trabajos al día)"),
    PositionSpec("FNC-N5-030", "Cortador de Café"),
    PositionSpec("FNC-N5-040", "Ayudante de Campo"),
)


@dataclass(frozen=True)
class SeedPositionsResult:
    created: int
    updated: int
    disabled: int
    activated: int
    maps_created: int
    skipped: int


def _clean_set(codes: Iterable[str]) -> set[str]:
    return {c.strip() for c in codes if c and c.strip()}


def seed_hr_positions_v01(
    company: OrgUnit,
    *,
    disable_codes: Iterable[str] = (),
    enable_codes: Iterable[str] = (),
    only_codes: Iterable[str] = (),
) -> SeedPositionsResult:
    """Crea/actualiza los puestos del catálogo para `company`. Idempotente.

    Lanza `ValueError` (claro) si un puesto en alcance referencia un rol RBAC inexistente.
    """
    disable = _clean_set(disable_codes)
    enable = _clean_set(enable_codes)
    only = _clean_set(only_codes)

    overlap = disable & enable
    if overlap:
        raise ValueError(f"Códigos en --disable y --enable a la vez: {sorted(overlap)}")

    in_scope = [s for s in POSITION_CATALOG if not only or s.code in only]
    skipped = len(POSITION_CATALOG) - len(in_scope)

    # Pre-validación: todos los roles de los puestos en alcance deben existir (fail clear).
    needed_roles = {s.role for s in in_scope if s.role}
    roles = {r.name: r for r in Role.objects.filter(name__in=list(needed_roles))}
    missing = sorted(needed_roles - set(roles))
    if missing:
        raise ValueError(
            "Roles RBAC inexistentes para el seed de puestos "
            "(corré seed_rbac_v01 primero): " + ", ".join(missing)
        )

    created = updated = disabled = activated = maps_created = 0

    with transaction.atomic():
        for spec in in_scope:
            forced_disable = spec.code in disable
            forced_enable = spec.code in enable

            position, was_created = JobPosition.objects.get_or_create(
                company=company,
                name=spec.name,
                defaults={"code": spec.code, "is_active": not forced_disable},
            )
            if was_created:
                created += 1
                if forced_disable:
                    disabled += 1
            else:
                fields: list[str] = []
                if position.code != spec.code:
                    position.code = spec.code
                    fields.append("code")
                # is_active SOLO cambia si un flag nombra el código (respeta el toggle manual).
                if forced_disable and position.is_active:
                    position.is_active = False
                    fields.append("is_active")
                    disabled += 1
                elif forced_enable and not position.is_active:
                    position.is_active = True
                    fields.append("is_active")
                    activated += 1
                if fields:
                    position.save(update_fields=[*fields, "updated_at"])
                    updated += 1

            # Mapeo a rol RBAC (aditivo: no borra otros maps manuales). Sin rol => sin acceso.
            if spec.role:
                _, map_created = PositionRoleMap.objects.get_or_create(
                    position=position,
                    role=roles[spec.role],
                    scope_mode=spec.scope,
                    defaults={"is_active": True},
                )
                if map_created:
                    maps_created += 1

    return SeedPositionsResult(
        created=created,
        updated=updated,
        disabled=disabled,
        activated=activated,
        maps_created=maps_created,
        skipped=skipped,
    )
