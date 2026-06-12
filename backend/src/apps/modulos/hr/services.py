"""Servicios de RRHH (precedente).

Precedente:
- La lógica de RRHH puede impactar autorización (RoleAssignment) y por eso debe ser transaccional,
  auditable y limitada por origen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.parties.models import Party, PartyRole
from apps.modulos.parties.services import assign_party_role
from apps.modulos.rbac.models import Role, RoleAssignment

from .contract_templates import render_contract_body
from .models import (
    Employee,
    EmployeeLifecycleEvent,
    EmployeeMemo,
    EmployeeRoleMap,
    EmploymentAssignment,
    EmploymentContract,
    JobPosition,
    PositionRoleMap,
)

User = get_user_model()


def _make_temp_password(user_model=User) -> str:
    # Evita dependencias: usa util estándar ya usado en provisioning
    return get_random_string(length=12)


@dataclass(frozen=True)
class ReconcileResult:
    created: int
    reactivated: int
    deactivated: int


def _company_branches(company: OrgUnit) -> list[int]:
    return list(OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).values_list("id", flat=True))


def _ensure_membership(user, org_unit: OrgUnit) -> None:
    mem, created = UserMembership.objects.get_or_create(user=user, org_unit=org_unit, defaults={"is_active": True})
    if not created and not mem.is_active:
        mem.is_active = True
        mem.left_at = None
        mem.save(update_fields=["is_active", "left_at"])


class _HRCompanyAuditRequest:
    """Contexto liviano para encadenar auditoria HR por company sin request."""

    def __init__(self, *, request, company: OrgUnit) -> None:
        base_req = getattr(request, "_request", request)
        self.company = company
        self.branch = _request_attr(request, base_req, "branch")
        self.ctx = _request_attr(request, base_req, "ctx")
        self.META = _request_attr(request, base_req, "META") or {}
        self.path = _request_attr(request, base_req, "path") or ""
        self.method = _request_attr(request, base_req, "method") or ""
        self.request_id = _request_attr(request, base_req, "request_id") or ""


def _request_attr(request, base_req, name: str):
    if base_req is not None:
        value = getattr(base_req, name, None)
        if value is not None:
            return value
    if request is not None:
        return getattr(request, name, None)
    return None


def _request_company(request):
    if request is None:
        return None
    base_req = getattr(request, "_request", request)
    return _request_attr(request, base_req, "company")


def _same_company(left, right) -> bool:
    return str(getattr(left, "id", left)) == str(getattr(right, "id", right))


def _audit_request_for_company(*, request, company: OrgUnit):
    request_company = _request_company(request)
    if request_company is not None and not _same_company(request_company, company):
        raise ValidationError({"company": "Request company no coincide con Employee.company."})
    if request_company is not None:
        return request
    return _HRCompanyAuditRequest(request=request, company=company)


def _employee_party_snapshot(employee: Employee) -> dict:
    return {
        "employee_id": employee.id,
        "company_id": employee.company_id,
        "party_id": employee.party_id,
        "linked_user_id": employee.linked_user_id,
    }


def _ensure_employee_party_role(*, party: Party, request=None, actor=None) -> None:
    active_exists = (
        PartyRole.objects.select_for_update()
        .filter(party=party, role=PartyRole.Role.EMPLOYEE, is_active=True)
        .exists()
    )
    if not active_exists:
        assign_party_role(party=party, role=PartyRole.Role.EMPLOYEE, request=request, actor=actor)


def link_employee_to_party(*, employee: Employee, party: Party, request=None, actor=None) -> Employee:
    with transaction.atomic():
        employee = Employee.objects.select_for_update().select_related("company").get(pk=employee.pk)
        party = Party.objects.select_for_update().get(pk=party.pk)
        if employee.company_id != party.company_id:
            raise ValidationError({"party": "Party debe pertenecer a la misma company del Employee."})

        audit_request = _audit_request_for_company(request=request, company=employee.company)
        before = _employee_party_snapshot(employee)
        if employee.party_id != party.id:
            employee.party = party
            employee.save(update_fields=["party", "updated_at"])

        _ensure_employee_party_role(party=party, request=request, actor=actor)

        write_event(
            request=audit_request,
            module="HR",
            event_type="HR_EMPLOYEE_PARTY_LINK_CHANGED",
            reason_code="OK",
            actor_user=actor,
            subject_type="EMPLOYEE",
            subject_id=str(employee.id),
            before_snapshot=before,
            after_snapshot=_employee_party_snapshot(employee),
            metadata={
                "company_id": str(employee.company_id),
                "employee_id": str(employee.id),
                "party_id": str(party.id),
                "linked_user_id": str(employee.linked_user_id or ""),
            },
        )
        return employee


def unlink_employee_party(*, employee: Employee, request=None, actor=None) -> Employee:
    with transaction.atomic():
        employee = Employee.objects.select_for_update().select_related("company").get(pk=employee.pk)
        audit_request = _audit_request_for_company(request=request, company=employee.company)
        before = _employee_party_snapshot(employee)
        if employee.party_id is not None:
            employee.party = None
            employee.save(update_fields=["party", "updated_at"])

        write_event(
            request=audit_request,
            module="HR",
            event_type="HR_EMPLOYEE_PARTY_LINK_CHANGED",
            reason_code="OK",
            actor_user=actor,
            subject_type="EMPLOYEE",
            subject_id=str(employee.id),
            before_snapshot=before,
            after_snapshot=_employee_party_snapshot(employee),
            metadata={
                "company_id": str(employee.company_id),
                "employee_id": str(employee.id),
                "previous_party_id": str(before["party_id"] or ""),
                "linked_user_id": str(employee.linked_user_id or ""),
            },
        )
        return employee


def reconcile_employee_roles(*, employee: Employee, request=None, actor=None) -> ReconcileResult:
    """
    Regla: SOLO toca RoleAssignment con origin=POSITION dentro del scope de la company del empleado.
    MANUAL y SYSTEM quedan intactos.

    Precedente de seguridad:
    - No se “expanden” permisos fuera del scope de company+branches.
    - Cambios se realizan dentro de una transacción para evitar estados parciales.
    """
    if employee.linked_user is None:
        return ReconcileResult(created=0, reactivated=0, deactivated=0)

    company = employee.company
    user = employee.linked_user

    branch_ids = _company_branches(company)
    scoped_orgunit_ids = [company.id] + branch_ids

    # 1) Desired grants desde assignments activos + maps activos
    desired: set[tuple[int, int]] = set()  # (role_id, org_unit_id)

    active_assignments = (
        EmploymentAssignment.objects.filter(employee=employee, is_active=True)
        .select_related("position", "branch")
        .all()
    )

    # Pre-cargar maps de puestos involucrados
    pos_ids = {a.position_id for a in active_assignments}
    maps = PositionRoleMap.objects.filter(position_id__in=list(pos_ids), is_active=True).select_related(
        "role", "position"
    )

    maps_by_position: dict[int, list[PositionRoleMap]] = {}
    for m in maps:
        maps_by_position.setdefault(m.position_id, []).append(m)

    for a in active_assignments:
        for m in maps_by_position.get(a.position_id, []):
            if m.scope_mode == PositionRoleMap.ScopeMode.COMPANY:
                desired.add((m.role_id, company.id))
            elif m.scope_mode == PositionRoleMap.ScopeMode.BRANCH:
                if a.branch_id:
                    desired.add((m.role_id, a.branch_id))

    # Roles DIRECTOS del trabajador (modelo centrado en la persona, scope empresa).
    for em_role_id in EmployeeRoleMap.objects.filter(employee=employee, is_active=True).values_list(
        "role_id", flat=True
    ):
        desired.add((em_role_id, company.id))

    # Trabajador dado de BAJA: no se materializa ningún rol (los maps quedan como
    # historial para un eventual reingreso, pero los grants vivos se revocan).
    if employee.employment_status == Employee.EmploymentStatus.BAJA:
        desired.clear()

    created = reactivated = deactivated = 0

    with transaction.atomic():
        existing_qs = RoleAssignment.objects.filter(
            user=user,
            org_unit_id__in=scoped_orgunit_ids,
            origin=RoleAssignment.Origin.POSITION,
        )
        existing = {(ra.role_id, ra.org_unit_id): ra for ra in existing_qs.select_for_update()}

        # create/reactivate desired
        for role_id, org_unit_id in desired:
            ra = existing.get((role_id, org_unit_id))
            if ra is None:
                RoleAssignment.objects.create(
                    user=user,
                    role_id=role_id,
                    org_unit_id=org_unit_id,
                    origin=RoleAssignment.Origin.POSITION,
                    origin_ref=f"employee:{employee.id}",
                    granted_by=actor,
                    is_active=True,
                )
                created += 1
            else:
                if not ra.is_active:
                    ra.is_active = True
                    ra.origin_ref = f"employee:{employee.id}"
                    if actor:
                        ra.granted_by = actor
                    ra.save(update_fields=["is_active", "origin_ref", "granted_by"])
                    reactivated += 1

        # deactivate obsolete POSITION grants
        for (role_id, org_unit_id), ra in existing.items():
            if (role_id, org_unit_id) in desired:
                continue
            if ra.is_active:
                ra.is_active = False
                ra.save(update_fields=["is_active"])
                deactivated += 1

        # memberships: agregar, no remover (robustez)
        #
        # Cambio: NO forzar membership a COMPANY siempre.
        # Base = asignaciones activas (branch o company si assignment sin branch)
        # + org units implicadas por role maps (desired)
        membership_ids: Set[int] = set()

        for a in active_assignments:
            if a.branch_id:
                membership_ids.add(a.branch_id)
            else:
                membership_ids.add(company.id)

        for _, org_unit_id in desired:
            membership_ids.add(org_unit_id)

        if membership_ids:
            org_map = OrgUnit.objects.in_bulk(list(membership_ids))
            for org_unit_id in membership_ids:
                ou = org_map.get(org_unit_id)
                if ou:
                    _ensure_membership(user, ou)

    # audit
    write_event(
        request=request,
        module="HR",
        event_type="HR_RECONCILE_APPLIED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={
            "created": created,
            "reactivated": reactivated,
            "deactivated": deactivated,
        },
    )

    return ReconcileResult(created=created, reactivated=reactivated, deactivated=deactivated)


def end_assignment(*, assignment: EmploymentAssignment, request=None, actor=None) -> None:
    if not assignment.is_active:
        return
    assignment.is_active = False
    assignment.ended_at = timezone.now()
    assignment.save(update_fields=["is_active", "ended_at"])

    write_event(
        request=request,
        module="HR",
        event_type="HR_ASSIGNMENT_ENDED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(assignment.employee_id),
        metadata={"assignment_id": assignment.id},
    )

    reconcile_employee_roles(employee=assignment.employee, request=request, actor=actor)


def set_position_role_maps(*, position: JobPosition, maps: list[dict], request=None, actor=None) -> None:
    """
    maps = [{"role_id": 1, "scope_mode":"BRANCH"}, ...]
    Reemplazo controlado: desactiva los existentes y activa/crea los nuevos.
    """
    with transaction.atomic():
        PositionRoleMap.objects.filter(position=position).update(is_active=False)

        for m in maps:
            role_id = int(m["role_id"])
            scope_mode = str(m.get("scope_mode", PositionRoleMap.ScopeMode.BRANCH)).upper().strip()
            if scope_mode not in PositionRoleMap.ScopeMode.values:
                raise ValueError(f"scope_mode inválido: {scope_mode}")
            if not Role.objects.filter(id=role_id).exists():
                raise ValueError(f"role_id no existe: {role_id}")

            obj, created = PositionRoleMap.objects.get_or_create(
                position=position,
                role_id=role_id,
                scope_mode=scope_mode,
                defaults={"is_active": True},
            )
            if not created and not obj.is_active:
                obj.is_active = True
                obj.save(update_fields=["is_active"])
    write_event(
        request=request,
        module="HR",
        event_type="HR_POSITION_ROLEMAP_UPDATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="POSITION",
        subject_id=str(position.id),
        metadata={"maps_count": len(maps)},
    )

    # Reconciliar empleados afectados (limitado a employees con linked_user)
    employee_ids = (
        EmploymentAssignment.objects.filter(position=position, is_active=True, employee__linked_user__isnull=False)
        .values_list("employee_id", flat=True)
        .distinct()
    )
    for eid in employee_ids:
        reconcile_employee_roles(employee=Employee.objects.get(id=eid), request=request, actor=actor)


def set_employee_role_maps(*, employee: Employee, role_ids: list, request=None, actor=None) -> None:
    """
    Reemplazo controlado de los roles DIRECTOS de un trabajador, luego reconcilia.
    role_ids = [1, 5, 8, ...]
    """
    with transaction.atomic():
        EmployeeRoleMap.objects.filter(employee=employee).update(is_active=False)
        seen: set[int] = set()
        for raw in role_ids:
            role_id = int(raw)
            if role_id in seen:
                continue
            seen.add(role_id)
            if not Role.objects.filter(id=role_id).exists():
                raise ValueError(f"role_id no existe: {role_id}")
            obj, created = EmployeeRoleMap.objects.get_or_create(
                employee=employee, role_id=role_id, defaults={"is_active": True}
            )
            if not created and not obj.is_active:
                obj.is_active = True
                obj.save(update_fields=["is_active"])

    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_ROLEMAP_UPDATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={"roles_count": len(seen)},
    )

    reconcile_employee_roles(employee=employee, request=request, actor=actor)


def provision_user_for_employee(
    *, employee: Employee, username: str, email: str | None, temp_password: str | None = None, request=None, actor=None
) -> dict:
    # Validaciones de negocio
    if employee.linked_user_id is not None:
        raise ValueError("El empleado ya tiene un usuario vinculado.")

    has_assignment = EmploymentAssignment.objects.filter(employee=employee, is_active=True).exists()
    if not has_assignment:
        raise ValueError("El empleado no tiene ninguna asignación activa. No se puede determinar el contexto.")

    if not temp_password:
        temp_password = get_random_string(length=12)

    normalized_email = (email or "").strip() or None

    with transaction.atomic():
        # Crear usuario
        if User.objects.filter(username=username).exists():
            raise ValueError(f"El username '{username}' ya existe.")

        if normalized_email and User.objects.filter(email=normalized_email).exists():
            raise ValueError(f"El email '{normalized_email}' ya existe.")

        user = User.objects.create_user(
            username=username,
            email=normalized_email,
            password=temp_password,
        )
        user.must_change_password = True
        user.is_active = True
        user.save(update_fields=["must_change_password", "is_active"])

        # Linkear
        employee.linked_user = user
        employee.save(update_fields=["linked_user"])

        # Reconciliar roles
        reconcile_employee_roles(employee=employee, request=request, actor=actor)

    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_USER_PROVISIONED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={"created_user_id": user.id, "username": user.username},
    )

    return {"user_id": user.id, "username": user.username, "temp_password": temp_password}


@transaction.atomic
def reset_temp_password_for_employee(
    *,
    employee: Employee,
    request=None,
    actor=None,
    temp_password: Optional[str] = None,
) -> dict:
    """
    Resetea contraseña provisional del usuario ligado a un empleado.
    Reglas:
      - Debe existir linked_user
      - Debe existir al menos 1 asignación activa (coherente con provisioning)
      - Fuerza must_change_password=True
      - Audita sin exponer la contraseña
    """
    if not employee.linked_user_id or not employee.linked_user:
        raise ValueError("EMPLOYEE_HAS_NO_LINKED_USER")

    has_active_assignment = EmploymentAssignment.objects.filter(employee=employee, is_active=True).exists()
    if not has_active_assignment:
        raise ValueError("EMPLOYEE_HAS_NO_ACTIVE_ASSIGNMENT")

    user = employee.linked_user
    pwd = (temp_password or "").strip() or _make_temp_password(User)

    user.set_password(pwd)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])

    # Reconcile por consistencia (si el puesto cambió, o scopes cambiaron)
    reconcile_employee_roles(employee=employee, request=request, actor=actor)

    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_TEMP_PASSWORD_RESET",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={
            "linked_user_id": user.id,
            "linked_username": user.username,
            "manual_password": bool((temp_password or "").strip()),
        },
    )

    return {"user_id": user.id, "username": user.username, "temp_password": pwd}


@transaction.atomic
def revoke_employee_access(
    *,
    employee: Employee,
    request=None,
    actor=None,
    disable_user: bool = False,
) -> dict:
    """
    B = revoke-access:
    - Desactiva RoleAssignments origin=POSITION en scope company + branches
    - Desactiva memberships del linked_user en scope company + branches
    - Opcional: user.is_active=False si el usuario ya no tiene memberships activas en ninguna otra org_unit
    - Audita HR_EMPLOYEE_ACCESS_REVOKED
    """
    if employee.linked_user is None:
        raise ValueError("EMPLOYEE_HAS_NO_LINKED_USER")

    user = employee.linked_user
    company = employee.company

    branch_ids = _company_branches(company)
    scoped_orgunit_ids = [company.id, *branch_ids]

    # 1) RoleAssignments origin=POSITION
    ra_qs = RoleAssignment.objects.filter(
        user=user,
        org_unit_id__in=scoped_orgunit_ids,
        origin=RoleAssignment.Origin.POSITION,
        is_active=True,
    )
    ra_deactivated = ra_qs.update(is_active=False)

    # 2) Memberships (company + branches)
    mem_qs = UserMembership.objects.filter(
        user=user,
        org_unit_id__in=scoped_orgunit_ids,
        is_active=True,
    )
    mem_deactivated = mem_qs.update(is_active=False, left_at=timezone.now())

    # 3) Opcional: user.is_active=False (solo si no queda activo en otro lado)
    user_disabled = False
    if disable_user:
        still_has_active_memberships = UserMembership.objects.filter(user=user, is_active=True).exists()
        if not still_has_active_memberships and user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
            user_disabled = True

    # 4) Auditoría
    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_ACCESS_REVOKED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={
            "company_id": company.id,
            "employee_id": employee.id,
            "linked_user_id": user.id,
            "role_assignments_deactivated": ra_deactivated,
            "memberships_deactivated": mem_deactivated,
            "user_disabled": user_disabled,
            "disable_user_requested": bool(disable_user),
        },
    )

    return {
        "ok": True,
        "employee_id": employee.id,
        "linked_user_id": user.id,
        "role_assignments_deactivated": ra_deactivated,
        "memberships_deactivated": mem_deactivated,
        "user_disabled": user_disabled,
    }


# ---------------------------------------------------------------------------
# Ciclo de vida laboral: suspensión / reintegro / baja / reingreso
# ---------------------------------------------------------------------------

def _employee_status_snapshot(employee: Employee) -> dict:
    return {
        "employment_status": employee.employment_status,
        "is_active": employee.is_active,
        "linked_user_id": employee.linked_user_id,
    }


@transaction.atomic
def suspend_employee(
    *,
    employee: Employee,
    reason_code: str,
    reason_detail: str = "",
    effective_date,
    end_date=None,
    with_pay: bool = False,
    suspend_access: bool = False,
    request=None,
    actor=None,
) -> EmployeeLifecycleEvent:
    """Suspende al trabajador (disciplinaria, médica, permiso sin goce, etc.).

    No toca sus roles: si se pide suspend_access, se bloquea el LOGIN del usuario
    vinculado (user.is_active=False) y el reintegro lo restituye.
    """
    employee = Employee.objects.select_for_update(of=("self",)).select_related("company", "linked_user").get(pk=employee.pk)
    if employee.employment_status != Employee.EmploymentStatus.ACTIVO:
        raise ValueError("EMPLOYEE_NOT_ACTIVE")
    if reason_code not in EmployeeLifecycleEvent.SuspensionReason.values:
        raise ValueError("INVALID_REASON_CODE")

    before = _employee_status_snapshot(employee)
    access_suspended = False
    linked_user = employee.linked_user
    if suspend_access and linked_user is not None and linked_user.is_active:
        linked_user.is_active = False
        linked_user.save(update_fields=["is_active"])
        access_suspended = True

    employee.employment_status = Employee.EmploymentStatus.SUSPENDIDO
    employee.save(update_fields=["employment_status", "updated_at"])

    event = EmployeeLifecycleEvent.objects.create(
        employee=employee,
        event_type=EmployeeLifecycleEvent.EventType.SUSPENSION,
        reason_code=reason_code,
        reason_detail=reason_detail or "",
        effective_date=effective_date,
        end_date=end_date,
        with_pay=bool(with_pay),
        access_suspended=access_suspended,
        created_by=actor,
    )

    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_SUSPENDED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        before_snapshot=before,
        after_snapshot=_employee_status_snapshot(employee),
        metadata={
            "lifecycle_event_id": event.id,
            "reason_code": reason_code,
            "with_pay": bool(with_pay),
            "access_suspended": access_suspended,
            "effective_date": str(effective_date),
            "end_date": str(end_date) if end_date else "",
        },
    )
    return event


@transaction.atomic
def reinstate_employee(*, employee: Employee, reason_detail: str = "", effective_date, request=None, actor=None) -> EmployeeLifecycleEvent:
    """Reintegra a un trabajador suspendido. Si la suspensión bloqueó el login, lo restituye."""
    employee = Employee.objects.select_for_update(of=("self",)).select_related("company", "linked_user").get(pk=employee.pk)
    if employee.employment_status != Employee.EmploymentStatus.SUSPENDIDO:
        raise ValueError("EMPLOYEE_NOT_SUSPENDED")

    before = _employee_status_snapshot(employee)

    last_suspension = (
        EmployeeLifecycleEvent.objects.filter(
            employee=employee, event_type=EmployeeLifecycleEvent.EventType.SUSPENSION
        )
        .order_by("-created_at", "-id")
        .first()
    )
    access_restored = False
    linked_user = employee.linked_user
    if last_suspension and last_suspension.access_suspended and linked_user is not None:
        if not linked_user.is_active:
            linked_user.is_active = True
            linked_user.save(update_fields=["is_active"])
            access_restored = True

    employee.employment_status = Employee.EmploymentStatus.ACTIVO
    employee.save(update_fields=["employment_status", "updated_at"])

    event = EmployeeLifecycleEvent.objects.create(
        employee=employee,
        event_type=EmployeeLifecycleEvent.EventType.REINTEGRO,
        reason_code="FIN_SUSPENSION",
        reason_detail=reason_detail or "",
        effective_date=effective_date,
        created_by=actor,
    )

    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_REINSTATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        before_snapshot=before,
        after_snapshot=_employee_status_snapshot(employee),
        metadata={
            "lifecycle_event_id": event.id,
            "access_restored": access_restored,
            "effective_date": str(effective_date),
        },
    )
    return event


@transaction.atomic
def terminate_employee(
    *,
    employee: Employee,
    reason_code: str,
    reason_detail: str = "",
    effective_date,
    request=None,
    actor=None,
) -> EmployeeLifecycleEvent:
    """Baja del trabajador (renuncia, despido, fin de contrato, etc.).

    Efectos: termina asignaciones activas, revoca acceso (roles POSITION +
    memberships, deshabilita el usuario si no pertenece a otra empresa),
    finaliza contratos EMITIDOS vigentes y deja al empleado en estado BAJA.
    Los EmployeeRoleMap quedan como historial para un eventual reingreso.
    """
    employee = Employee.objects.select_for_update(of=("self",)).select_related("company", "linked_user").get(pk=employee.pk)
    if employee.employment_status == Employee.EmploymentStatus.BAJA:
        raise ValueError("EMPLOYEE_ALREADY_TERMINATED")
    if reason_code not in EmployeeLifecycleEvent.BajaReason.values:
        raise ValueError("INVALID_REASON_CODE")

    before = _employee_status_snapshot(employee)

    now = timezone.now()
    assignments_ended = EmploymentAssignment.objects.filter(employee=employee, is_active=True).update(
        is_active=False, ended_at=now
    )
    contracts_closed = EmploymentContract.objects.filter(
        employee=employee, status=EmploymentContract.Status.EMITIDO
    ).update(status=EmploymentContract.Status.FINALIZADO)

    employee.employment_status = Employee.EmploymentStatus.BAJA
    employee.is_active = False
    employee.save(update_fields=["employment_status", "is_active", "updated_at"])

    access = None
    if employee.linked_user_id:
        access = revoke_employee_access(
            employee=employee, request=request, actor=actor, disable_user=True
        )

    event = EmployeeLifecycleEvent.objects.create(
        employee=employee,
        event_type=EmployeeLifecycleEvent.EventType.BAJA,
        reason_code=reason_code,
        reason_detail=reason_detail or "",
        effective_date=effective_date,
        created_by=actor,
    )

    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_TERMINATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        before_snapshot=before,
        after_snapshot=_employee_status_snapshot(employee),
        metadata={
            "lifecycle_event_id": event.id,
            "reason_code": reason_code,
            "effective_date": str(effective_date),
            "assignments_ended": assignments_ended,
            "contracts_closed": contracts_closed,
            "access_revoked": bool(access),
        },
    )
    return event


@transaction.atomic
def rehire_employee(*, employee: Employee, reason_detail: str = "", effective_date, request=None, actor=None) -> EmployeeLifecycleEvent:
    """Reingreso de un trabajador dado de baja (recontratación / nueva temporada).

    Reactiva la ficha. El acceso al sistema NO se restituye automático: se gestiona
    aparte (provisionar / reset de clave) para que sea una decisión explícita.
    """
    employee = Employee.objects.select_for_update(of=("self",)).select_related("company", "linked_user").get(pk=employee.pk)
    if employee.employment_status != Employee.EmploymentStatus.BAJA:
        raise ValueError("EMPLOYEE_NOT_TERMINATED")

    before = _employee_status_snapshot(employee)
    employee.employment_status = Employee.EmploymentStatus.ACTIVO
    employee.is_active = True
    employee.save(update_fields=["employment_status", "is_active", "updated_at"])

    event = EmployeeLifecycleEvent.objects.create(
        employee=employee,
        event_type=EmployeeLifecycleEvent.EventType.REINGRESO,
        reason_code="RECONTRATACION",
        reason_detail=reason_detail or "",
        effective_date=effective_date,
        created_by=actor,
    )

    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_REHIRED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        before_snapshot=before,
        after_snapshot=_employee_status_snapshot(employee),
        metadata={"lifecycle_event_id": event.id, "effective_date": str(effective_date)},
    )
    return event


# ---------------------------------------------------------------------------
# Contratos laborales (plantilla por caso + texto editable)
# ---------------------------------------------------------------------------

_SPANISH_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _spanish_date(d) -> str:
    if not d:
        return ""
    return f"{d.day} de {_SPANISH_MONTHS[d.month - 1]} de {d.year}"


def _contract_render_context(*, employee: Employee, contract: EmploymentContract, extra: dict | None = None) -> dict:
    from apps.modulos.org.models import CompanyProfile

    profile = CompanyProfile.objects.filter(company=employee.company).first()
    company_legal = (profile.legal_name if profile else "") or employee.company.name
    salary_text = ""
    if contract.salary_amount is not None:
        salary_text = f"{contract.salary_amount:,.2f}"
    period_labels: dict[str, str] = {
        EmploymentContract.SalaryPeriod.MENSUAL: "de forma mensual",
        EmploymentContract.SalaryPeriod.QUINCENAL: "de forma quincenal",
        EmploymentContract.SalaryPeriod.SEMANAL: "de forma semanal",
        EmploymentContract.SalaryPeriod.DIARIO: "por día laborado",
        EmploymentContract.SalaryPeriod.POR_OBRA: "según obra o producción entregada",
    }
    party = employee.party if employee.party_id else None
    ctx = {
        "contract_type_label": contract.get_contract_type_display().upper(),
        "company_legal_name": company_legal,
        "company_tax_id": (profile.tax_id if profile else ""),
        "company_address": (profile.address if profile else ""),
        "company_city": "",
        "employer_rep": "",
        "employee_name": f"{employee.first_name} {employee.last_name}".strip(),
        "employee_code": employee.employee_code or "",
        "employee_national_id": (party.national_id if party else ""),
        "position_name": contract.position.name if contract.position is not None else "",
        "start_date": _spanish_date(contract.start_date),
        "end_date": _spanish_date(contract.end_date),
        "salary_text": salary_text,
        "salary_period_label": period_labels.get(contract.salary_period, ""),
        "signing_date": _spanish_date(timezone.localdate()),
    }
    if extra:
        ctx.update({k: v for k, v in extra.items() if v})
    return ctx


@transaction.atomic
def create_contract_draft(
    *,
    employee: Employee,
    contract_type: str,
    start_date,
    end_date=None,
    position: JobPosition | None = None,
    salary_amount=None,
    salary_period: str = EmploymentContract.SalaryPeriod.MENSUAL,
    extra_context: dict | None = None,
    request=None,
    actor=None,
) -> EmploymentContract:
    """Crea el BORRADOR del contrato con el texto redactado desde plantilla."""
    if contract_type not in EmploymentContract.ContractType.values:
        raise ValueError("INVALID_CONTRACT_TYPE")
    if salary_period not in EmploymentContract.SalaryPeriod.values:
        raise ValueError("INVALID_SALARY_PERIOD")

    contract = EmploymentContract(
        employee=employee,
        contract_type=contract_type,
        position=position,
        start_date=start_date,
        end_date=end_date,
        salary_amount=salary_amount,
        salary_period=salary_period,
        created_by=actor,
    )
    contract.full_clean()
    contract.body = render_contract_body(
        contract_type=contract_type,
        context=_contract_render_context(employee=employee, contract=contract, extra=extra_context),
    )
    contract.save()

    write_event(
        request=request,
        module="HR",
        event_type="HR_CONTRACT_CREATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={
            "contract_id": contract.id,
            "contract_type": contract_type,
            "start_date": str(start_date),
            "end_date": str(end_date) if end_date else "",
        },
    )
    return contract


@transaction.atomic
def issue_contract(*, contract: EmploymentContract, request=None, actor=None) -> EmploymentContract:
    """BORRADOR → EMITIDO. El texto queda congelado."""
    contract = EmploymentContract.objects.select_for_update().get(pk=contract.pk)
    if contract.status != EmploymentContract.Status.BORRADOR:
        raise ValueError("CONTRACT_NOT_DRAFT")
    contract.status = EmploymentContract.Status.EMITIDO
    contract.issued_at = timezone.now()
    contract.save(update_fields=["status", "issued_at", "updated_at"])

    write_event(
        request=request,
        module="HR",
        event_type="HR_CONTRACT_ISSUED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(contract.employee_id),
        metadata={"contract_id": contract.id, "contract_type": contract.contract_type},
    )
    return contract


@transaction.atomic
def annul_contract(*, contract: EmploymentContract, reason: str = "", request=None, actor=None) -> EmploymentContract:
    contract = EmploymentContract.objects.select_for_update().get(pk=contract.pk)
    if contract.status == EmploymentContract.Status.ANULADO:
        return contract
    before = contract.status
    contract.status = EmploymentContract.Status.ANULADO
    contract.save(update_fields=["status", "updated_at"])

    write_event(
        request=request,
        module="HR",
        event_type="HR_CONTRACT_ANNULLED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(contract.employee_id),
        metadata={"contract_id": contract.id, "previous_status": before, "reason": reason or ""},
    )
    return contract


# ---------------------------------------------------------------------------
# Memorandos / relaciones laborales
# ---------------------------------------------------------------------------

@transaction.atomic
def create_memo(
    *,
    employee: Employee,
    memo_type: str,
    subject: str,
    body: str = "",
    issued_date=None,
    request=None,
    actor=None,
) -> EmployeeMemo:
    if memo_type not in EmployeeMemo.MemoType.values:
        raise ValueError("INVALID_MEMO_TYPE")
    if not (subject or "").strip():
        raise ValueError("MEMO_SUBJECT_REQUIRED")

    memo = EmployeeMemo.objects.create(
        employee=employee,
        memo_type=memo_type,
        subject=subject.strip(),
        body=body or "",
        issued_date=issued_date or timezone.localdate(),
        created_by=actor,
    )

    write_event(
        request=request,
        module="HR",
        event_type="HR_MEMO_CREATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={"memo_id": memo.id, "memo_type": memo_type, "subject": memo.subject},
    )
    return memo


@transaction.atomic
def annul_memo(*, memo: EmployeeMemo, reason: str = "", request=None, actor=None) -> EmployeeMemo:
    memo = EmployeeMemo.objects.select_for_update().get(pk=memo.pk)
    if memo.status == EmployeeMemo.Status.ANULADO:
        return memo
    memo.status = EmployeeMemo.Status.ANULADO
    memo.save(update_fields=["status"])

    write_event(
        request=request,
        module="HR",
        event_type="HR_MEMO_ANNULLED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(memo.employee_id),
        metadata={"memo_id": memo.id, "reason": reason or ""},
    )
    return memo
