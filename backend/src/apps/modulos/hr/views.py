from __future__ import annotations

import base64
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.audit.writer import write_event
from apps.modulos.common.api_exceptions import ConflictError
from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.common.throttling import MethodThrottleScopeMixin
from apps.modulos.iam.models import OrgUnit
from apps.modulos.parties.models import Party
from apps.modulos.rbac.models import RoleAssignment

from .models import (
    Employee,
    EmployeeLifecycleEvent,
    EmployeeMemo,
    EmployeePhoto,
    EmployeeRoleMap,
    EmploymentAssignment,
    EmploymentContract,
    JobPosition,
    PositionRoleMap,
)
from .photo_service import remove_employee_photo, set_employee_photo
from .serializers import (
    AssignmentCreateSerializer,
    ContractCreateSerializer,
    ContractUpdateSerializer,
    EmployeeRevokeAccessSerializer,
    EmployeeCreateSerializer,
    EmployeeRehireSerializer,
    EmployeeReinstateSerializer,
    EmployeeSuspendSerializer,
    EmployeeTerminateSerializer,
    MemoCreateSerializer,
    ResetTempPasswordSerializer,
    EmployeeUpdateSerializer,
    PositionCreateSerializer,
    PositionRoleMapUpdateSerializer,
    PositionUpdateSerializer,
    EmployeeProvisionUserSerializer,
)
from .services import (
    annul_contract,
    annul_memo,
    create_contract_draft,
    create_memo,
    end_assignment,
    issue_contract,
    link_employee_to_party,
    provision_user_for_employee,
    reconcile_employee_roles,
    rehire_employee,
    reinstate_employee,
    revoke_employee_access,
    reset_temp_password_for_employee,
    set_employee_role_maps,
    set_position_role_maps,
    suspend_employee,
    terminate_employee,
    unlink_employee_party,
)


class OnboardingSummaryView(APIView):
    """
    GET /hr/onboarding/summary/

    Resumen agregado para el "home de onboarding" (evita 4 llamadas separadas).
    Scope: request.company. Devuelve los contadores de cada paso + el próximo paso
    sugerido (`next_step`) y `complete`. Provisionar es opcional por trabajador,
    pero se usa como último paso del recorrido guiado.
    """

    permission_classes = [rbac_permission("hr.employee.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        company: OrgUnit = request.company

        positions_count = JobPosition.objects.filter(company=company).count()
        positions_with_roles = (
            JobPosition.objects.filter(company=company, role_maps__is_active=True).distinct().count()
        )
        employees_count = Employee.objects.filter(company=company).count()
        employees_active = Employee.objects.filter(
            company=company, employment_status=Employee.EmploymentStatus.ACTIVO
        ).count()
        employees_suspended = Employee.objects.filter(
            company=company, employment_status=Employee.EmploymentStatus.SUSPENDIDO
        ).count()
        employees_terminated = Employee.objects.filter(
            company=company, employment_status=Employee.EmploymentStatus.BAJA
        ).count()
        employees_assigned = (
            Employee.objects.filter(company=company, assignments__is_active=True).distinct().count()
        )
        employees_provisioned = Employee.objects.filter(
            company=company, linked_user__isnull=False
        ).count()

        if positions_count == 0:
            next_step = "POSITIONS"
        elif positions_with_roles == 0:
            next_step = "POSITION_ROLES"
        elif employees_count == 0:
            next_step = "EMPLOYEES"
        elif employees_assigned == 0:
            next_step = "ASSIGNMENTS"
        elif employees_provisioned == 0:
            next_step = "PROVISIONING"
        else:
            next_step = "DONE"

        return Response(
            {
                "positions_count": positions_count,
                "positions_with_roles": positions_with_roles,
                "employees_count": employees_count,
                "employees_active": employees_active,
                "employees_suspended": employees_suspended,
                "employees_terminated": employees_terminated,
                "employees_assigned": employees_assigned,
                "employees_provisioned": employees_provisioned,
                "next_step": next_step,
                "complete": next_step == "DONE",
            },
            status=status.HTTP_200_OK,
        )


class EmployeeAssignmentEndView(APIView):
    """
    Acción idempotente: si la asignación ya está finalizada, responde 200.
    """

    permission_classes = [rbac_permission("hr.assignment.end")]
    throttle_scope = "admin_writes"

    def post(self, request, employee_id: int, assignment_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        assignment = get_object_or_404(EmploymentAssignment, id=assignment_id, employee=emp)

        end_assignment(assignment=assignment, request=request, actor=request.user)
        return Response({"ok": True}, status=status.HTTP_200_OK)


User = get_user_model()


def _django_validation_payload(exc: DjangoValidationError) -> dict:
    if hasattr(exc, "message_dict"):
        return exc.message_dict
    return {"detail": list(exc.messages)}


class PositionListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "POST": "admin_writes",
    }
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("hr.position.create")()]
        return [rbac_permission("hr.position.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = JobPosition.objects.filter(company=company).order_by("name")
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        data = [{"id": p.id, "name": p.name, "code": p.code, "is_active": p.is_active} for p in rows]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        company: OrgUnit = request.company
        serializer = PositionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        v = serializer.validated_data
        pos = JobPosition.objects.create(company=company, name=v["name"], code=v.get("code", ""))
        write_event(
            request=request,
            module="HR",
            event_type="HR_POSITION_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="POSITION",
            subject_id=str(pos.id),
            metadata={"position_name": pos.name},
        )
        return Response({"id": pos.id}, status=status.HTTP_201_CREATED)


class PositionDetailView(APIView):
    permission_classes = [rbac_permission("hr.position.update")]
    throttle_scope = "admin_writes"

    def patch(self, request, position_id: int):
        company: OrgUnit = request.company
        pos = get_object_or_404(JobPosition, id=position_id, company=company)
        serializer = PositionUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        before = {"name": pos.name, "code": pos.code, "is_active": pos.is_active}
        v = serializer.validated_data
        if "name" in v:
            pos.name = v["name"]
        if "code" in v:
            pos.code = v["code"]
        if "is_active" in v:
            pos.is_active = bool(v["is_active"])
        pos.save()
        after = {"name": pos.name, "code": pos.code, "is_active": pos.is_active}
        write_event(
            request=request,
            module="HR",
            event_type="HR_POSITION_UPDATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="POSITION",
            subject_id=str(pos.id),
            before_snapshot=before,
            after_snapshot=after,
        )
        return Response({"ok": True}, status=status.HTTP_200_OK)


class PositionRoleMapUpdateView(APIView):
    throttle_scope = "admin_writes"

    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("hr.position.read")()]
        return [rbac_permission("hr.position.roles.update")()]

    def get(self, request, position_id: int):
        company: OrgUnit = request.company
        pos = get_object_or_404(JobPosition, id=position_id, company=company)
        maps = (
            PositionRoleMap.objects.filter(position=pos, is_active=True)
            .select_related("role")
            .order_by("role__name")
        )
        data = [
            {"role_id": m.role_id, "role_name": m.role.name, "scope_mode": m.scope_mode}
            for m in maps
        ]
        return Response({"results": data}, status=status.HTTP_200_OK)

    def put(self, request, position_id: int):
        company: OrgUnit = request.company
        pos = get_object_or_404(JobPosition, id=position_id, company=company)
        serializer = PositionRoleMapUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        maps = serializer.validated_data.get("maps", [])
        normalized = []
        for m in maps:
            if not isinstance(m, dict):
                return Response({"maps": "Cada item debe ser un objeto"}, status=status.HTTP_400_BAD_REQUEST)
            if "role_id" not in m:
                return Response({"maps": "Falta role_id"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                role_id = int(m["role_id"])
            except Exception:
                return Response({"maps": "role_id inválido"}, status=status.HTTP_400_BAD_REQUEST)

            scope_mode = str(m.get("scope_mode", "BRANCH")).upper().strip()
            if scope_mode not in ("BRANCH", "COMPANY"):
                return Response({"maps": f"scope_mode inválido: {scope_mode}"}, status=status.HTTP_400_BAD_REQUEST)
            normalized.append({"role_id": role_id, "scope_mode": scope_mode})

        # dedupe estable
        seen = set()
        deduped = []
        for x in normalized:
            k = (x["role_id"], x["scope_mode"])
            if k in seen:
                continue
            seen.add(k)
            deduped.append(x)
        set_position_role_maps(position=pos, maps=deduped, request=request, actor=request.user)
        return Response({"ok": True}, status=status.HTTP_200_OK)


class EmployeeListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "POST": "admin_writes",
    }
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("hr.employee.create")()]
        return [rbac_permission("hr.employee.read")()]

    def get(self, request):
        company = request.company
        active_asg_qs = (
            EmploymentAssignment.objects.filter(is_active=True)
            .select_related("position", "branch")
            .order_by("-started_at", "-id")
        )
        base_qs = Employee.objects.filter(company=company).order_by("id")
        limit, offset = get_limit_offset(request)
        total = base_qs.count()
        active_roles_qs = (
            EmployeeRoleMap.objects.filter(is_active=True).select_related("role").order_by("role__name")
        )
        qs = (
            base_qs.select_related("linked_user", "party")
            .prefetch_related(
                Prefetch("assignments", queryset=active_asg_qs, to_attr="active_assignments"),
                Prefetch("role_maps", queryset=active_roles_qs, to_attr="active_role_maps"),
            )
            # Exists y no select_related("photo"): el base64 de la foto no debe
            # viajar en el listado.
            .annotate(has_photo=Exists(EmployeePhoto.objects.filter(employee_id=OuterRef("pk"))))
        )
        rows = qs[offset : offset + limit]
        out = []
        for e in rows:
            actives = getattr(e, "active_assignments", []) or []
            out.append(
                {
                    "id": e.id,
                    "employee_code": e.employee_code or "",
                    "first_name": e.first_name,
                    "last_name": e.last_name or "",
                    "phone": e.phone or "",
                    "email": e.email or "",
                    "cedula": e.cedula or "",
                    "inss_number": e.inss_number or "",
                    "gender": e.gender or "",
                    "salary_type": e.salary_type,
                    "daily_rate_nio": str(e.daily_rate_nio),
                    "monthly_salary_nio": str(e.monthly_salary_nio),
                    "has_photo": bool(getattr(e, "has_photo", False)),
                    "is_active": e.is_active,
                    "employment_status": e.employment_status,
                    "party_id": e.party_id,
                    "party_display_name": e.party.display_name if e.party_id and e.party else None,
                    "party_tax_id": e.party.tax_id if e.party_id and e.party else "",
                    "party_national_id": e.party.national_id if e.party_id and e.party else "",
                    "linked_user_id": e.linked_user_id,
                    "linked_username": (e.linked_user.username if e.linked_user_id and e.linked_user else None),
                    "has_active_assignment": bool(actives),
                    "active_assignments": [
                        {
                            "id": a.id,
                            "position_id": a.position_id,
                            "position_name": a.position.name if a.position_id and a.position else "",
                            "branch_id": a.branch_id,
                            "branch_name": a.branch.name if a.branch_id and a.branch else None,
                            "started_at": a.started_at.isoformat() if a.started_at else None,
                        }
                        for a in actives
                    ],
                    "roles": [
                        {"role_id": rm.role_id, "role_name": rm.role.name}
                        for rm in (getattr(e, "active_role_maps", []) or [])
                    ],
                }
            )
        return Response({"count": total, "limit": limit, "offset": offset, "results": out})

    def post(self, request):
        company: OrgUnit = request.company
        serializer = EmployeeCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        v = serializer.validated_data
        linked_user = None
        if "linked_user_id" in v:
            linked_user = User.objects.filter(id=int(v["linked_user_id"])).first()
            if not linked_user:
                return Response({"linked_user_id": "Usuario no existe"}, status=status.HTTP_400_BAD_REQUEST)
        party = None
        if "party_id" in v:
            party = Party.objects.filter(id=int(v["party_id"]), company=company).first()
            if party is None:
                return Response({"party_id": "Party no existe en esta company."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                emp = Employee.objects.create(
                    company=company,
                    employee_code=v.get("employee_code", ""),
                    first_name=v["first_name"],
                    last_name=v.get("last_name", ""),
                    phone=v.get("phone", ""),
                    email=v.get("email", ""),
                    cedula=v.get("cedula", ""),
                    inss_number=v.get("inss_number", ""),
                    gender=v.get("gender", ""),
                    salary_type=v.get("salary_type", "DAILY"),
                    daily_rate_nio=v.get("daily_rate_nio") or Decimal("0.00"),
                    monthly_salary_nio=v.get("monthly_salary_nio") or Decimal("0.00"),
                    is_active=bool(v.get("is_active", True)),
                    linked_user=linked_user,
                )
                write_event(
                    request=request,
                    module="HR",
                    event_type="HR_EMPLOYEE_CREATED",
                    reason_code="OK",
                    actor_user=request.user,
                    subject_type="EMPLOYEE",
                    subject_id=str(emp.id),
                    metadata={"employee_name": emp.first_name},
                )
                if party is not None:
                    link_employee_to_party(employee=emp, party=party, request=request, actor=request.user)
                if emp.linked_user_id:
                    reconcile_employee_roles(employee=emp, request=request, actor=request.user)
        except DjangoValidationError as exc:
            return Response(_django_validation_payload(exc), status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": emp.id}, status=status.HTTP_201_CREATED)


class EmployeeDetailView(APIView):
    permission_classes = [rbac_permission("hr.employee.update")]
    throttle_scope = "admin_writes"

    def patch(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        serializer = EmployeeUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        before = {
            "employee_code": emp.employee_code,
            "party_id": emp.party_id,
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "phone": emp.phone,
            "email": emp.email,
            "cedula": emp.cedula,
            "inss_number": emp.inss_number,
            "gender": emp.gender,
            "salary_type": emp.salary_type,
            "daily_rate_nio": str(emp.daily_rate_nio),
            "monthly_salary_nio": str(emp.monthly_salary_nio),
            "is_active": emp.is_active,
            "linked_user_id": emp.linked_user_id,
        }
        v = serializer.validated_data
        old_linked_user_id = emp.linked_user_id
        party_requested = "party_id" in v
        party = None
        if party_requested and v["party_id"] is not None:
            party = Party.objects.filter(id=int(v["party_id"]), company=company).first()
            if party is None:
                return Response({"party_id": "Party no existe en esta company."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                for f in [
                    "employee_code", "first_name", "last_name", "phone", "email",
                    "cedula", "inss_number", "gender", "salary_type",
                    "daily_rate_nio", "monthly_salary_nio", "is_active",
                ]:
                    if f in v:
                        setattr(emp, f, v[f])
                if "linked_user_id" in v:
                    new_val = v["linked_user_id"]
                    if new_val is None:
                        emp.linked_user = None
                    else:
                        u = User.objects.filter(id=int(new_val)).first()
                        if not u:
                            return Response({"linked_user_id": "Usuario no existe"}, status=status.HTTP_400_BAD_REQUEST)
                        emp.linked_user = u
                emp.save()
                after = {
                    "employee_code": emp.employee_code,
                    "party_id": emp.party_id,
                    "first_name": emp.first_name,
                    "last_name": emp.last_name,
                    "phone": emp.phone,
                    "email": emp.email,
                    "cedula": emp.cedula,
                    "inss_number": emp.inss_number,
                    "gender": emp.gender,
                    "salary_type": emp.salary_type,
                    "daily_rate_nio": str(emp.daily_rate_nio),
                    "monthly_salary_nio": str(emp.monthly_salary_nio),
                    "is_active": emp.is_active,
                    "linked_user_id": emp.linked_user_id,
                }
                write_event(
                    request=request,
                    module="HR",
                    event_type="HR_EMPLOYEE_UPDATED",
                    reason_code="OK",
                    actor_user=request.user,
                    subject_type="EMPLOYEE",
                    subject_id=str(emp.id),
                    before_snapshot=before,
                    after_snapshot=after,
                )
                if party_requested:
                    if party is None:
                        unlink_employee_party(employee=emp, request=request, actor=request.user)
                    else:
                        link_employee_to_party(employee=emp, party=party, request=request, actor=request.user)
                # si cambió el vínculo, limpiamos roles POSITION del usuario anterior dentro del scope de la company
                if old_linked_user_id and old_linked_user_id != emp.linked_user_id:
                    branch_ids = list(
                        OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).values_list(
                            "id", flat=True
                        )
                    )
                    scoped_ids = [company.id] + branch_ids
                    RoleAssignment.objects.filter(
                        user_id=old_linked_user_id,
                        org_unit_id__in=scoped_ids,
                        origin=RoleAssignment.Origin.POSITION,
                        is_active=True,
                    ).update(is_active=False)
                if emp.linked_user_id:
                    reconcile_employee_roles(employee=emp, request=request, actor=request.user)
        except DjangoValidationError as exc:
            return Response(_django_validation_payload(exc), status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True}, status=status.HTTP_200_OK)



# Vista combinada para listar y crear asignaciones de empleado
class EmployeeAssignmentListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "POST": "admin_writes",
    }
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("hr.assignment.create")()]
        return [rbac_permission("hr.assignment.read")()]

    def get(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        qs = (
            EmploymentAssignment.objects.filter(employee=emp)
            .select_related("position", "branch")
            .order_by("-is_active", "-started_at", "-id")
        )
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        data = []
        for a in rows:
            data.append(
                {
                    "id": a.id,
                    "is_active": a.is_active,
                    "position_id": a.position_id,
                    "position_name": a.position.name if a.position_id and a.position else "",
                    "branch_id": a.branch_id,
                    "branch_name": a.branch.name if a.branch_id and a.branch else None,
                    "started_at": a.started_at.isoformat() if a.started_at else None,
                    "ended_at": a.ended_at.isoformat() if a.ended_at else None,
                }
            )
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": data},
            status=status.HTTP_200_OK,
        )

    def post(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        serializer = AssignmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        v = serializer.validated_data
        position = get_object_or_404(JobPosition, id=int(v["position_id"]), company=company)
        branch = None
        if v.get("branch_id") is not None:
            branch = get_object_or_404(
                OrgUnit,
                id=int(v["branch_id"]),
                parent=company,
                unit_type=OrgUnit.UnitType.BRANCH,
            )
        a = EmploymentAssignment.objects.create(
            employee=emp,
            position=position,
            branch=branch,
            created_by=request.user,
        )
        write_event(
            request=request,
            module="HR",
            event_type="HR_ASSIGNMENT_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="EMPLOYEE",
            subject_id=str(emp.id),
            metadata={"assignment_id": a.id},
        )
        if emp.linked_user_id:
            reconcile_employee_roles(employee=emp, request=request, actor=request.user)
        return Response({"id": a.id}, status=status.HTTP_201_CREATED)


class EmployeeRoleMapView(APIView):
    """
    GET/PUT /hr/employees/<id>/roles/ — roles DIRECTOS del trabajador (modelo
    centrado en la persona). El PUT es reemplazo total y reconcilia.
    """

    throttle_scope = "admin_writes"

    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("hr.employee.read")()]
        return [rbac_permission("hr.employee.update")()]

    def get(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        maps = (
            EmployeeRoleMap.objects.filter(employee=emp, is_active=True)
            .select_related("role")
            .order_by("role__name")
        )
        data = [{"role_id": m.role_id, "role_name": m.role.name} for m in maps]
        return Response({"results": data}, status=status.HTTP_200_OK)

    def put(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        role_ids = request.data.get("role_ids", [])
        if not isinstance(role_ids, list):
            return Response({"role_ids": "Debe ser una lista de IDs."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            normalized = [int(x) for x in role_ids]
        except (TypeError, ValueError):
            return Response({"role_ids": "IDs inválidos."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            set_employee_role_maps(employee=emp, role_ids=normalized, request=request, actor=request.user)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True}, status=status.HTTP_200_OK)


class EmployeeProvisionUserView(APIView):
    permission_classes = [
        rbac_permission("iam.users.create"),
        rbac_permission("hr.employee.update"),
    ]
    throttle_scope = "admin_writes"

    def post(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)

        serializer = EmployeeProvisionUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = provision_user_for_employee(
                employee=emp,
                username=serializer.validated_data["username"],
                email=serializer.validated_data["email"],
                temp_password=serializer.validated_data.get("temp_password"),
                request=request,
                actor=request.user,
            )
            return Response(result, status=status.HTTP_201_CREATED)

        except ValueError as e:
            msg = str(e)
            if "ya tiene un usuario vinculado" in msg:
                raise ConflictError(detail=msg)
            # Both "no active assignment" and username conflict fall here as 400
            raise ValidationError({"detail": msg})


class EmployeeResetTempPasswordView(APIView):
    """
    POST /hr/employees/<id>/reset-temp-password/
    Requiere: iam.users.create + hr.employee.update (mismo estándar que provision)
    """

    permission_classes = [rbac_permission("iam.users.create"), rbac_permission("hr.employee.update")]
    throttle_scope = "admin_writes"

    def post(self, request, employee_id: int):
        company = request.company
        emp = Employee.objects.filter(id=employee_id, company=company).select_related("linked_user").first()
        if not emp:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        ser = ResetTempPasswordSerializer(data=request.data or {})
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            out = reset_temp_password_for_employee(
                employee=emp,
                request=request,
                actor=request.user,
                temp_password=ser.validated_data.get("temp_password") or None,
            )
        except ValueError as e:
            code = str(e)
            if code == "EMPLOYEE_HAS_NO_LINKED_USER":
                return Response({"detail": "Employee has no linked user"}, status=status.HTTP_409_CONFLICT)
            if code == "EMPLOYEE_HAS_NO_ACTIVE_ASSIGNMENT":
                return Response({"detail": "Employee has no active assignment"}, status=status.HTTP_409_CONFLICT)
            return Response({"detail": "Invalid state"}, status=status.HTTP_409_CONFLICT)

        return Response(out, status=status.HTTP_200_OK)


class EmployeeRevokeAccessView(APIView):
    """
    POST /hr/employees/<id>/revoke-access/
    Requiere: iam.users.create + hr.employee.update (mismo estándar que provision/reset)
    """

    permission_classes = [rbac_permission("iam.users.create"), rbac_permission("hr.employee.update")]
    throttle_scope = "admin_writes"

    def post(self, request, employee_id: int):
        company = request.company
        employee = Employee.objects.select_related("linked_user").filter(company=company, id=employee_id).first()
        if employee is None:
            return Response({"detail": "Empleado no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        s = EmployeeRevokeAccessSerializer(data=request.data or {})
        s.is_valid(raise_exception=True)

        try:
            out = revoke_employee_access(
                employee=employee,
                request=request,
                actor=request.user,
                disable_user=bool(s.validated_data.get("disable_user", False)),
            )
        except ValueError as e:
            if str(e) == "EMPLOYEE_HAS_NO_LINKED_USER":
                return Response({"detail": "El empleado no tiene usuario ligado."}, status=status.HTTP_409_CONFLICT)
            return Response({"detail": "Estado inválido."}, status=status.HTTP_409_CONFLICT)

        return Response(out, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Catálogos (choices) para la UI — una sola fuente de verdad
# ---------------------------------------------------------------------------


def _choices(choices_cls) -> list[dict]:
    return [{"value": value, "label": label} for value, label in choices_cls.choices]


class HrCatalogsView(APIView):
    """GET /hr/catalogs/ — choices del ciclo de vida, contratos y memos para la UI."""

    permission_classes = [rbac_permission("hr.employee.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        return Response(
            {
                "baja_reasons": _choices(EmployeeLifecycleEvent.BajaReason),
                "suspension_reasons": _choices(EmployeeLifecycleEvent.SuspensionReason),
                "contract_types": _choices(EmploymentContract.ContractType),
                "salary_periods": _choices(EmploymentContract.SalaryPeriod),
                "memo_types": _choices(EmployeeMemo.MemoType),
                "employment_statuses": _choices(Employee.EmploymentStatus),
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Ciclo de vida laboral
# ---------------------------------------------------------------------------

_LIFECYCLE_ERRORS = {
    "EMPLOYEE_NOT_ACTIVE": "El trabajador no está activo (ya está suspendido o de baja).",
    "EMPLOYEE_NOT_SUSPENDED": "El trabajador no está suspendido.",
    "EMPLOYEE_ALREADY_TERMINATED": "El trabajador ya está dado de baja.",
    "EMPLOYEE_NOT_TERMINATED": "El trabajador no está dado de baja.",
    "INVALID_REASON_CODE": "Motivo inválido.",
}


def _lifecycle_event_payload(ev: EmployeeLifecycleEvent) -> dict:
    return {
        "id": ev.id,
        "event_type": ev.event_type,
        "event_type_label": ev.get_event_type_display(),
        "reason_code": ev.reason_code,
        "reason_detail": ev.reason_detail,
        "effective_date": str(ev.effective_date),
        "end_date": str(ev.end_date) if ev.end_date else None,
        "with_pay": ev.with_pay,
        "access_suspended": ev.access_suspended,
        "created_at": ev.created_at.isoformat(),
        "created_by": ev.created_by.username if ev.created_by_id and ev.created_by else None,
    }


class EmployeeLifecycleListView(APIView):
    permission_classes = [rbac_permission("hr.employee.read")]
    throttle_scope = "heavy_reads"

    def get(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        events = emp.lifecycle_events.select_related("created_by").all()[:200]
        return Response({"results": [_lifecycle_event_payload(e) for e in events]}, status=status.HTTP_200_OK)


class _EmployeeLifecycleActionView(APIView):
    """Base: acción de ciclo de vida con manejo uniforme de errores de estado."""

    permission_classes = [rbac_permission("hr.employee.update")]
    throttle_scope = "admin_writes"

    def _run(self, fn, **kwargs):
        try:
            event = fn(**kwargs)
        except ValueError as e:
            msg = _LIFECYCLE_ERRORS.get(str(e), "Estado inválido.")
            code = status.HTTP_400_BAD_REQUEST if str(e) == "INVALID_REASON_CODE" else status.HTTP_409_CONFLICT
            return Response({"detail": msg, "code": str(e)}, status=code)
        return Response({"ok": True, "event": _lifecycle_event_payload(event)}, status=status.HTTP_200_OK)


class EmployeeSuspendView(_EmployeeLifecycleActionView):
    def post(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        s = EmployeeSuspendSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        return self._run(
            suspend_employee,
            employee=emp,
            reason_code=v["reason_code"],
            reason_detail=v.get("reason_detail", ""),
            effective_date=v["effective_date"],
            end_date=v.get("end_date"),
            with_pay=bool(v.get("with_pay", False)),
            suspend_access=bool(v.get("suspend_access", False)),
            request=request,
            actor=request.user,
        )


class EmployeeReinstateView(_EmployeeLifecycleActionView):
    def post(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        s = EmployeeReinstateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        return self._run(
            reinstate_employee,
            employee=emp,
            reason_detail=v.get("reason_detail", ""),
            effective_date=v["effective_date"],
            request=request,
            actor=request.user,
        )


class EmployeeTerminateView(_EmployeeLifecycleActionView):
    def post(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        s = EmployeeTerminateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        return self._run(
            terminate_employee,
            employee=emp,
            reason_code=v["reason_code"],
            reason_detail=v.get("reason_detail", ""),
            effective_date=v["effective_date"],
            request=request,
            actor=request.user,
        )


class EmployeeRehireView(_EmployeeLifecycleActionView):
    def post(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        s = EmployeeRehireSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        return self._run(
            rehire_employee,
            employee=emp,
            reason_detail=v.get("reason_detail", ""),
            effective_date=v["effective_date"],
            request=request,
            actor=request.user,
        )


# ---------------------------------------------------------------------------
# Contratos laborales
# ---------------------------------------------------------------------------


def _contract_payload(c: EmploymentContract, *, include_body: bool = False) -> dict:
    out = {
        "id": c.id,
        "contract_type": c.contract_type,
        "contract_type_label": c.get_contract_type_display(),
        "status": c.status,
        "position_id": c.position_id,
        "position_name": c.position.name if c.position_id and c.position else "",
        "start_date": str(c.start_date),
        "end_date": str(c.end_date) if c.end_date else None,
        "salary_amount": str(c.salary_amount) if c.salary_amount is not None else None,
        "salary_period": c.salary_period,
        "issued_at": c.issued_at.isoformat() if c.issued_at else None,
        "created_at": c.created_at.isoformat(),
    }
    if include_body:
        out["body"] = c.body
    return out


class EmployeeContractListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {"GET": "heavy_reads", "POST": "admin_writes"}

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("hr.employee.update")()]
        return [rbac_permission("hr.employee.read")()]

    def get(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        contracts = emp.contracts.select_related("position").all()[:200]
        return Response({"results": [_contract_payload(c) for c in contracts]}, status=status.HTTP_200_OK)

    def post(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        s = ContractCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        position = None
        if v.get("position_id") is not None:
            position = get_object_or_404(JobPosition, id=int(v["position_id"]), company=request.company)
        extra = {}
        if v.get("work_description"):
            extra["work_description"] = v["work_description"]
        if v.get("season_description"):
            extra["season_description"] = v["season_description"]
        try:
            contract = create_contract_draft(
                employee=emp,
                contract_type=v["contract_type"],
                start_date=v["start_date"],
                end_date=v.get("end_date"),
                position=position,
                salary_amount=v.get("salary_amount"),
                salary_period=v.get("salary_period") or EmploymentContract.SalaryPeriod.MENSUAL,
                extra_context=extra,
                request=request,
                actor=request.user,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except DjangoValidationError as exc:
            return Response(_django_validation_payload(exc), status=status.HTTP_400_BAD_REQUEST)
        return Response(_contract_payload(contract, include_body=True), status=status.HTTP_201_CREATED)


def _get_company_contract(request, contract_id: int) -> EmploymentContract:
    return get_object_or_404(
        EmploymentContract.objects.select_related("employee", "position"),
        id=contract_id,
        employee__company=request.company,
    )


class ContractDetailView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {"GET": "heavy_reads", "PATCH": "admin_writes"}

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [rbac_permission("hr.employee.update")()]
        return [rbac_permission("hr.employee.read")()]

    def get(self, request, contract_id: int):
        c = _get_company_contract(request, contract_id)
        out = _contract_payload(c, include_body=True)
        out["employee_id"] = c.employee_id
        return Response(out, status=status.HTTP_200_OK)

    def patch(self, request, contract_id: int):
        c = _get_company_contract(request, contract_id)
        if c.status != EmploymentContract.Status.BORRADOR:
            return Response(
                {"detail": "Solo se puede editar un contrato en BORRADOR."},
                status=status.HTTP_409_CONFLICT,
            )
        s = ContractUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if "salary_period" in v and v["salary_period"] not in EmploymentContract.SalaryPeriod.values:
            return Response({"salary_period": "Período inválido."}, status=status.HTTP_400_BAD_REQUEST)
        for f in ["body", "start_date", "end_date", "salary_amount", "salary_period"]:
            if f in v:
                setattr(c, f, v[f])
        try:
            c.full_clean()
        except DjangoValidationError as exc:
            return Response(_django_validation_payload(exc), status=status.HTTP_400_BAD_REQUEST)
        c.save()
        write_event(
            request=request,
            module="HR",
            event_type="HR_CONTRACT_UPDATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="EMPLOYEE",
            subject_id=str(c.employee_id),
            metadata={"contract_id": c.id, "fields": sorted(v.keys())},
        )
        return Response(_contract_payload(c, include_body=True), status=status.HTTP_200_OK)


class ContractIssueView(APIView):
    permission_classes = [rbac_permission("hr.employee.update")]
    throttle_scope = "admin_writes"

    def post(self, request, contract_id: int):
        c = _get_company_contract(request, contract_id)
        try:
            c = issue_contract(contract=c, request=request, actor=request.user)
        except ValueError:
            return Response(
                {"detail": "Solo se puede emitir un contrato en BORRADOR."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(_contract_payload(c, include_body=True), status=status.HTTP_200_OK)


class ContractAnnulView(APIView):
    permission_classes = [rbac_permission("hr.employee.update")]
    throttle_scope = "admin_writes"

    def post(self, request, contract_id: int):
        c = _get_company_contract(request, contract_id)
        reason = str(request.data.get("reason", "") or "")
        c = annul_contract(contract=c, reason=reason, request=request, actor=request.user)
        return Response(_contract_payload(c), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Memorandos / relaciones laborales
# ---------------------------------------------------------------------------


def _memo_payload(m: EmployeeMemo) -> dict:
    return {
        "id": m.id,
        "memo_type": m.memo_type,
        "memo_type_label": m.get_memo_type_display(),
        "status": m.status,
        "subject": m.subject,
        "body": m.body,
        "issued_date": str(m.issued_date),
        "created_at": m.created_at.isoformat(),
        "created_by": m.created_by.username if m.created_by_id and m.created_by else None,
    }


class EmployeeMemoListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {"GET": "heavy_reads", "POST": "admin_writes"}

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("hr.employee.update")()]
        return [rbac_permission("hr.employee.read")()]

    def get(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        memos = emp.memos.select_related("created_by").all()[:200]
        return Response({"results": [_memo_payload(m) for m in memos]}, status=status.HTTP_200_OK)

    def post(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        s = MemoCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            memo = create_memo(
                employee=emp,
                memo_type=v["memo_type"],
                subject=v["subject"],
                body=v.get("body", ""),
                issued_date=v.get("issued_date"),
                request=request,
                actor=request.user,
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_memo_payload(memo), status=status.HTTP_201_CREATED)


class MemoAnnulView(APIView):
    permission_classes = [rbac_permission("hr.employee.update")]
    throttle_scope = "admin_writes"

    def post(self, request, memo_id: int):
        memo = get_object_or_404(
            EmployeeMemo.objects.select_related("employee"),
            id=memo_id,
            employee__company=request.company,
        )
        reason = str(request.data.get("reason", "") or "")
        memo = annul_memo(memo=memo, reason=reason, request=request, actor=request.user)
        return Response(_memo_payload(memo), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Perfil (expediente) del trabajador
# ---------------------------------------------------------------------------


class EmployeeProfileView(APIView):
    """GET /hr/employees/<id>/profile/ — expediente completo en una sola llamada."""

    permission_classes = [rbac_permission("hr.employee.read")]
    throttle_scope = "heavy_reads"

    def get(self, request, employee_id: int):
        emp = get_object_or_404(
            Employee.objects.select_related("linked_user", "party"),
            id=employee_id,
            company=request.company,
        )
        assignments = emp.assignments.select_related("position", "branch").order_by(
            "-is_active", "-started_at", "-id"
        )[:100]
        roles = (
            EmployeeRoleMap.objects.filter(employee=emp, is_active=True)
            .select_related("role")
            .order_by("role__name")
        )
        contracts = emp.contracts.select_related("position").all()[:100]
        memos = emp.memos.select_related("created_by").all()[:100]
        events = emp.lifecycle_events.select_related("created_by").all()[:100]

        return Response(
            {
                "id": emp.id,
                "employee_code": emp.employee_code or "",
                "first_name": emp.first_name,
                "last_name": emp.last_name or "",
                "phone": emp.phone or "",
                "email": emp.email or "",
                "cedula": emp.cedula or "",
                "inss_number": emp.inss_number or "",
                "gender": emp.gender or "",
                "salary_type": emp.salary_type,
                "daily_rate_nio": str(emp.daily_rate_nio),
                "monthly_salary_nio": str(emp.monthly_salary_nio),
                "has_photo": EmployeePhoto.objects.filter(employee=emp).exists(),
                "is_active": emp.is_active,
                "employment_status": emp.employment_status,
                "party_id": emp.party_id,
                "party_national_id": emp.party.national_id if emp.party_id and emp.party else "",
                "linked_user_id": emp.linked_user_id,
                "linked_username": emp.linked_user.username if emp.linked_user_id and emp.linked_user else None,
                "linked_user_active": bool(emp.linked_user.is_active) if emp.linked_user_id and emp.linked_user else None,
                "roles": [{"role_id": r.role_id, "role_name": r.role.name} for r in roles],
                "assignments": [
                    {
                        "id": a.id,
                        "is_active": a.is_active,
                        "position_id": a.position_id,
                        "position_name": a.position.name if a.position_id and a.position else "",
                        "branch_id": a.branch_id,
                        "branch_name": a.branch.name if a.branch_id and a.branch else None,
                        "started_at": a.started_at.isoformat() if a.started_at else None,
                        "ended_at": a.ended_at.isoformat() if a.ended_at else None,
                    }
                    for a in assignments
                ],
                "contracts": [_contract_payload(c) for c in contracts],
                "memos": [_memo_payload(m) for m in memos],
                "lifecycle_events": [_lifecycle_event_payload(e) for e in events],
            },
            status=status.HTTP_200_OK,
        )


class EmployeePhotoView(APIView):
    """Foto del expediente: GET (también para la pantalla de asistencia) · POST subir · DELETE quitar."""

    throttle_scope = "heavy_reads"

    def get_permissions(self):
        if self.request.method == "GET":
            # La pantalla de asistencia (capataz/mandador) también muestra la foto:
            # basta cualquiera de los dos permisos de lectura.
            from rest_framework.permissions import BasePermission

            hr_read = rbac_permission("hr.employee.read")
            field_read = rbac_permission("nomina.field.read")

            class _AnyRead(BasePermission):
                message = "No tienes permisos para realizar esta acción."

                def has_permission(self, request, view) -> bool:
                    return hr_read().has_permission(request, view) or field_read().has_permission(request, view)

            return [_AnyRead()]
        return [rbac_permission("hr.employee.update")()]

    def get(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        photo = EmployeePhoto.objects.filter(employee=emp).only(
            "image_data", "content_type", "updated_at"
        ).first()
        if photo is None:
            return Response({"detail": "Sin foto."}, status=status.HTTP_404_NOT_FOUND)
        resp = HttpResponse(base64.b64decode(photo.image_data), content_type=photo.content_type)
        resp["Cache-Control"] = "private, max-age=300"
        return resp

    def post(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"file": "Adjuntá la foto en el campo 'file'."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            photo = set_employee_photo(
                request=request,
                actor=request.user,
                employee=emp,
                raw=upload.read(),
            )
        except DjangoValidationError as exc:
            return Response(_django_validation_payload(exc), status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"ok": True, "byte_size": photo.byte_size, "width": photo.width, "height": photo.height},
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, employee_id: int):
        emp = get_object_or_404(Employee, id=employee_id, company=request.company)
        removed = remove_employee_photo(request=request, actor=request.user, employee=emp)
        if not removed:
            return Response({"detail": "Sin foto."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"ok": True}, status=status.HTTP_200_OK)
