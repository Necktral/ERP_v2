"""Política de costo versionada (invariante #8) — resolución y versionado.

Resuelve el método de costeo vigente por scope (sucursal con fallback a empresa)
y permite cambiarlo creando una **versión nueva** (la anterior se cierra), de modo
que los movimientos posteados conservan el costeo de su época. El default —cuando
no hay política configurada— es promedio ponderado móvil (comportamiento actual),
por lo que esto NO altera el costeo existente.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event

from .models import CostingMethod, InventoryCostPolicy


def get_active_cost_policy(*, company, branch=None) -> InventoryCostPolicy | None:
    """Política activa: específica de la sucursal o, si no hay, la de empresa."""
    policy = InventoryCostPolicy.objects.filter(company=company, branch=branch, is_active=True).first()
    if policy is None and branch is not None:
        policy = InventoryCostPolicy.objects.filter(company=company, branch__isnull=True, is_active=True).first()
    return policy


def resolve_costing_method(*, company, branch=None) -> str:
    policy = get_active_cost_policy(company=company, branch=branch)
    return policy.method if policy is not None else CostingMethod.WEIGHTED_AVERAGE


def resolve_active_cost_policy_version(*, company, branch=None) -> int:
    """Versión de la política vigente (0 = sin política => default no versionado)."""
    policy = get_active_cost_policy(company=company, branch=branch)
    return policy.version if policy is not None else 0


def _audit_request(*, request, company, branch=None):
    if request is not None:
        return request

    class _Req:
        pass

    req = _Req()
    req.company = company
    req.branch = branch
    req.META = {}
    req.path = ""
    req.method = ""
    req.request_id = ""
    return req


@transaction.atomic
def set_cost_policy(
    *, request=None, actor=None, company, branch=None, method: str, params: dict | None = None, note: str = ""
) -> InventoryCostPolicy:
    """Versionado: cierra la política activa del scope y crea una versión nueva."""
    if method not in CostingMethod.values:
        raise ValueError(f"método de costeo inválido: {method}")

    current = (
        InventoryCostPolicy.objects.select_for_update()
        .filter(company=company, branch=branch, is_active=True)
        .first()
    )
    next_version = 1
    if current is not None:
        current.is_active = False
        current.effective_to = timezone.now()
        current.save(update_fields=["is_active", "effective_to"])
        next_version = int(current.version) + 1

    policy = InventoryCostPolicy.objects.create(
        company=company,
        branch=branch,
        method=method,
        version=next_version,
        params=params or {},
        is_active=True,
        effective_from=timezone.now(),
        note=note or "",
        created_by=actor,
    )

    write_event(
        request=_audit_request(request=request, company=company, branch=branch),
        module="INVENTORY",
        event_type="INVENTORY_COST_POLICY_SET",
        reason_code="INVENTORY_OK",
        actor_user=actor,
        subject_type="INVENTORY_COST_POLICY",
        subject_id=str(policy.id),
        after_snapshot={"method": policy.method, "version": policy.version, "branch_id": branch.id if branch else None},
        metadata={"company_id": str(company.id), "previous_version": str(current.version) if current else "0"},
    )
    return policy
