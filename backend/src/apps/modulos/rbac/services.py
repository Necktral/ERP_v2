"""Servicios de administración RBAC (asignación de roles por usuario).

Permite asignar/revocar `RoleAssignment` por scope (company/branch), validando
que el org_unit esté dentro del scope activo del administrador, de forma
idempotente y auditada (`RBAC_ROLE_ASSIGNED`/`RBAC_ROLE_REVOKED`).
"""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit

from .models import Role, RoleAssignment


class _RbacAuditRequest:
    def __init__(self, *, company, branch=None) -> None:
        self.company = company
        self.branch = branch
        self.META: dict[str, Any] = {}
        self.path = ""
        self.method = ""
        self.request_id = ""


def _audit_request(*, request, company, branch=None):
    return request if request is not None else _RbacAuditRequest(company=company, branch=branch)


def assert_org_in_company_scope(*, org_unit: OrgUnit, company: OrgUnit) -> None:
    """El org_unit debe ser la propia company o una BRANCH hija de la company."""
    if org_unit.id == company.id:
        return
    if org_unit.unit_type == OrgUnit.UnitType.BRANCH and org_unit.parent_id == company.id:
        return
    raise ValidationError({"org_unit": "El org_unit está fuera del scope de la empresa activa."})


def _snapshot(ra: RoleAssignment) -> dict[str, Any]:
    return {
        "id": ra.id,
        "user_id": ra.user_id,
        "role_id": ra.role_id,
        "org_unit_id": ra.org_unit_id,
        "origin": ra.origin,
        "is_active": ra.is_active,
    }


@transaction.atomic
def assign_role(
    *,
    user,
    role: Role,
    org_unit: OrgUnit,
    granted_by,
    scope_company: OrgUnit,
    origin: str = RoleAssignment.Origin.MANUAL,
    request=None,
) -> RoleAssignment:
    assert_org_in_company_scope(org_unit=org_unit, company=scope_company)
    # Valida tipo de org_unit (COMPANY/BRANCH) vía clean del modelo.
    RoleAssignment(user=user, role=role, org_unit=org_unit, origin=origin).clean()

    ra, created = RoleAssignment.objects.get_or_create(
        user=user,
        role=role,
        org_unit=org_unit,
        origin=origin,
        defaults={"granted_by": granted_by, "is_active": True},
    )
    if not created and not ra.is_active:
        ra.is_active = True
        ra.granted_by = granted_by
        ra.save(update_fields=["is_active", "granted_by"])

    write_event(
        request=_audit_request(request=request, company=scope_company, branch=None),
        module="RBAC",
        event_type="RBAC_ROLE_ASSIGNED",
        reason_code="RBAC_OK",
        actor_user=granted_by,
        subject_type="ROLE_ASSIGNMENT",
        subject_id=str(ra.id),
        after_snapshot=_snapshot(ra),
        metadata={"company_id": str(scope_company.id), "target_user_id": str(user.id)},
    )
    return ra


@transaction.atomic
def revoke_role_assignment(*, assignment: RoleAssignment, actor, scope_company: OrgUnit, request=None) -> RoleAssignment:
    before = _snapshot(assignment)
    if assignment.is_active:
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])
    write_event(
        request=_audit_request(request=request, company=scope_company, branch=None),
        module="RBAC",
        event_type="RBAC_ROLE_REVOKED",
        reason_code="RBAC_OK",
        actor_user=actor,
        subject_type="ROLE_ASSIGNMENT",
        subject_id=str(assignment.id),
        before_snapshot=before,
        after_snapshot=_snapshot(assignment),
        metadata={"company_id": str(scope_company.id), "target_user_id": str(assignment.user_id)},
    )
    return assignment
