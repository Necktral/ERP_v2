from __future__ import annotations

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit
from apps.modulos.rbac.models import RoleAssignment

from .models import ControlFinding
from .serializers import ControlFindingOut, FindingResolveIn, ScanIn, SegregationRuleOut
from .services import (
    active_rules_for,
    evaluate_user_segregation,
    resolve_finding,
    run_detectors,
)

User = get_user_model()


class SegregationRuleListView(APIView):
    """Catálogo de reglas SoD aplicables a la empresa (globales + propias)."""

    permission_classes = [rbac_permission("controls.sod.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        company: OrgUnit = request.company
        rules = active_rules_for(company)
        return Response({"results": SegregationRuleOut(rules, many=True).data}, status=status.HTTP_200_OK)


class SegregationViolationsView(APIView):
    """Evaluación viva de violaciones por concesión (un usuario posee ambos perms)."""

    permission_classes = [rbac_permission("controls.sod.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        company: OrgUnit = request.company
        branch_ids = list(
            OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).values_list("id", flat=True)
        )
        scope_ids = [company.id, *branch_ids]
        user_ids = (
            RoleAssignment.objects.filter(org_unit_id__in=scope_ids, is_active=True)
            .values_list("user_id", flat=True)
            .distinct()
        )
        out = []
        for user in User.objects.filter(id__in=list(user_ids)).order_by("id"):
            for rule in evaluate_user_segregation(user, company):
                out.append(
                    {
                        "user_id": user.id,
                        "username": getattr(user, "username", ""),
                        "rule_code": rule.code,
                        "permission_a": rule.permission_a,
                        "permission_b": rule.permission_b,
                        "severity": rule.severity,
                    }
                )
        return Response({"results": out}, status=status.HTTP_200_OK)


class ControlScanView(APIView):
    """Corre los detectores (concesión + ejercicio) y materializa hallazgos."""

    permission_classes = [rbac_permission("controls.findings.manage")]
    throttle_scope = "admin_writes"

    def post(self, request):
        company: OrgUnit = request.company
        s = ScanIn(data=request.data or {})
        s.is_valid(raise_exception=True)
        created = run_detectors(
            company,
            window_days=s.validated_data["window_days"],
            request=request,
            actor=request.user,
        )
        return Response(
            {"created": len(created), "findings": ControlFindingOut(created, many=True).data},
            status=status.HTTP_200_OK,
        )


class ControlFindingListView(APIView):
    """Lista de hallazgos de la empresa (filtrable por status/control_code)."""

    permission_classes = [rbac_permission("controls.findings.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        company: OrgUnit = request.company
        qs = ControlFinding.objects.filter(company=company).order_by("-detected_at", "-id")
        status_f = (request.query_params.get("status") or "").strip().upper()
        if status_f:
            qs = qs.filter(status=status_f)
        code_f = (request.query_params.get("control_code") or "").strip().upper()
        if code_f:
            qs = qs.filter(control_code=code_f)
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": ControlFindingOut(rows, many=True).data},
            status=status.HTTP_200_OK,
        )


class ControlFindingResolveView(APIView):
    """Transiciona un hallazgo (ACK/RESOLVED/DISMISSED)."""

    permission_classes = [rbac_permission("controls.findings.manage")]
    throttle_scope = "admin_writes"

    def post(self, request, finding_id: int):
        company: OrgUnit = request.company
        finding = get_object_or_404(ControlFinding, id=finding_id, company=company)
        s = FindingResolveIn(data=request.data or {})
        s.is_valid(raise_exception=True)
        try:
            updated = resolve_finding(
                finding,
                actor=request.user,
                status=s.validated_data["status"],
                note=s.validated_data.get("note", ""),
                request=request,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ControlFindingOut(updated).data, status=status.HTTP_200_OK)
