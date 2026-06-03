from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit
from .models import Role, Permission, RoleAssignment
from .selectors import get_effective_permissions_for_scope
from .serializers import AssignmentCreateIn
from .services import assign_role, revoke_role_assignment

User = get_user_model()

# --- Listado de roles y permisos (read-only, protegidos) ---


class RoleListView(APIView):
    """
    GET /api/rbac/roles/?include_inactive=1
    """

    permission_classes = [rbac_permission("rbac.roles.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        include_inactive = request.query_params.get("include_inactive") == "1"
        qs = Role.objects.all().order_by("name")
        if not include_inactive:
            qs = qs.filter(is_active=True)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        results = [
            {
                "id": r.id,
                "name": r.name,
                "description": getattr(r, "description", "") or "",
                "is_active": bool(getattr(r, "is_active", True)),
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class PermissionListView(APIView):
    """
    GET /api/rbac/permissions/?include_inactive=1
    """

    permission_classes = [rbac_permission("rbac.permissions.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        include_inactive = request.query_params.get("include_inactive") == "1"
        qs = Permission.objects.all().order_by("code")
        if not include_inactive:
            qs = qs.filter(is_active=True)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        results = [
            {
                "id": p.id,
                "code": p.code,
                "description": getattr(p, "description", "") or "",
                "is_active": bool(getattr(p, "is_active", True)),
            }
            for p in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


# --- Demo contractual ---
class InventoryReadDemoView(APIView):
    """
    Endpoint demo para validar 403 contractual con required_permission.
    Luego puedes mover este patrón a endpoints reales.
    """

    permission_classes = [rbac_permission("inventory.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        return Response({"ok": True, "required_permission": "inventory.read"})


# --- Administración de asignaciones de rol por usuario (SoD-friendly) ---


def _company_scope_org_ids(company: OrgUnit) -> list[int]:
    branch_ids = list(
        OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).values_list("id", flat=True)
    )
    return [company.id, *branch_ids]


class AssignmentListCreateView(APIView):
    """GET lista asignaciones del scope; POST asigna un rol a un usuario."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("rbac.assignments.update")()]
        return [rbac_permission("rbac.assignments.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = RoleAssignment.objects.filter(org_unit_id__in=_company_scope_org_ids(company)).order_by("-id")
        user_id = request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)
        if request.query_params.get("active") == "1":
            qs = qs.filter(is_active=True)
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "id": ra.id,
                "user_id": ra.user_id,
                "role_id": ra.role_id,
                "org_unit_id": ra.org_unit_id,
                "origin": ra.origin,
                "is_active": ra.is_active,
            }
            for ra in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results}, status=status.HTTP_200_OK
        )

    def post(self, request):
        company: OrgUnit = request.company
        s = AssignmentCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        target_user = get_object_or_404(User, id=v["user_id"])
        role = get_object_or_404(Role, id=v["role_id"])
        org_unit = get_object_or_404(OrgUnit, id=v["org_unit_id"])

        ra = assign_role(
            user=target_user,
            role=role,
            org_unit=org_unit,
            granted_by=request.user,
            scope_company=company,
            origin=v.get("origin") or RoleAssignment.Origin.MANUAL,
            request=request,
        )
        return Response({"id": ra.id, "is_active": ra.is_active}, status=status.HTTP_201_CREATED)


class AssignmentRevokeView(APIView):
    permission_classes = [rbac_permission("rbac.assignments.update")]

    def post(self, request, assignment_id: int):
        company: OrgUnit = request.company
        ra = get_object_or_404(
            RoleAssignment, id=assignment_id, org_unit_id__in=_company_scope_org_ids(company)
        )
        revoke_role_assignment(assignment=ra, actor=request.user, scope_company=company, request=request)
        return Response({"id": ra.id, "is_active": ra.is_active}, status=status.HTTP_200_OK)


class UserEffectivePermissionsView(APIView):
    """Preview de permisos efectivos de un usuario en el scope activo."""

    permission_classes = [rbac_permission("rbac.assignments.read")]

    def get(self, request, user_id: int):
        company: OrgUnit = request.company
        branch = getattr(request, "branch", None)
        target_user = get_object_or_404(User, id=user_id)
        perms = sorted(get_effective_permissions_for_scope(target_user, company=company, branch=branch))
        return Response({"user_id": target_user.id, "permissions": perms}, status=status.HTTP_200_OK)
