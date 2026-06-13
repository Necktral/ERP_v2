from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit
from .models import Role, Permission, RoleAssignment, RolePermission
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
        include_permissions = request.query_params.get("include_permissions") == "1"
        qs = Role.objects.all().order_by("name")
        if not include_inactive:
            qs = qs.filter(is_active=True)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        perms_by_role: dict[int, list[dict]] = {}
        if include_permissions:
            role_ids = [r.id for r in rows]
            rp_qs = (
                RolePermission.objects.filter(role_id__in=role_ids, permission__is_active=True)
                .select_related("permission")
                .order_by("permission__code")
            )
            for rp in rp_qs:
                perms_by_role.setdefault(rp.role_id, []).append(
                    {"code": rp.permission.code, "description": rp.permission.description or ""}
                )

        results = []
        for r in rows:
            item = {
                "id": r.id,
                "name": r.name,
                "description": getattr(r, "description", "") or "",
                "is_active": bool(getattr(r, "is_active", True)),
            }
            if include_permissions:
                item["permissions"] = perms_by_role.get(r.id, [])
            results.append(item)

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


class ScopeUsersView(APIView):
    """GET /rbac/users/ — usuarios con membresía activa en la empresa (y sus sucursales),
    con sus roles activos del scope. Base de la pantalla "Usuarios y acceso"."""

    permission_classes = [rbac_permission("rbac.assignments.read")]

    def get(self, request):
        from django.db.models import Q

        from apps.modulos.iam.models import UserMembership

        company: OrgUnit = request.company
        org_ids = _company_scope_org_ids(company)
        user_ids = (
            UserMembership.objects.filter(org_unit_id__in=org_ids, is_active=True)
            .values_list("user_id", flat=True)
            .distinct()
        )
        qs = User.objects.filter(id__in=list(user_ids)).order_by("username")
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(Q(username__icontains=search) | Q(email__icontains=search))

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        rows = list(rows)

        assignments = (
            RoleAssignment.objects.filter(
                org_unit_id__in=org_ids, user_id__in=[u.id for u in rows], is_active=True
            )
            .select_related("role", "org_unit")
            .order_by("role__name")
        )
        roles_by_user: dict[int, list[dict]] = {}
        for ra in assignments:
            roles_by_user.setdefault(ra.user_id, []).append(
                {
                    "assignment_id": ra.id,
                    "role_id": ra.role_id,
                    "role_name": ra.role.name,
                    "org_unit_id": ra.org_unit_id,
                    "org_unit_name": ra.org_unit.name,
                    "org_unit_type": ra.org_unit.unit_type,
                    "origin": ra.origin,
                }
            )

        results = [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email or "",
                "is_active": u.is_active,
                "roles": roles_by_user.get(u.id, []),
            }
            for u in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )
