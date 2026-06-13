"""Vistas del presupuesto de finca (Ola G)."""
from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission

from .services_budget import (
    FincaBudgetError,
    approve_budget,
    archive_budget,
    budget_payload,
    budget_vs_actual,
    create_budget,
    get_budget,
    list_budgets,
    upsert_lines,
)

_ERR_STATUS = {
    "FINCA_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "BUDGET_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "LABOR_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "PLOT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "BUDGET_NOT_DRAFT": status.HTTP_409_CONFLICT,
    "SOD_SELF_APPROVAL": status.HTTP_409_CONFLICT,
}


def _err(exc: FincaBudgetError) -> Response:
    code = str(exc)
    return Response({"detail": code, "code": code}, status=_ERR_STATUS.get(code, status.HTTP_422_UNPROCESSABLE_ENTITY))


class BudgetCreateIn(serializers.Serializer):
    finca_id = serializers.IntegerField()
    season_label = serializers.CharField(max_length=80)
    name = serializers.CharField(max_length=160)


class BudgetLineIn(serializers.Serializer):
    labor_id = serializers.IntegerField()
    plot_id = serializers.IntegerField()
    planned_jornales = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    planned_rate = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    planned_insumos_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=0)


class BudgetLinesIn(serializers.Serializer):
    lines = BudgetLineIn(many=True)


class FincaBudgetListCreateView(APIView):
    def get_permissions(self):
        code = "finca.budget.manage" if self.request.method == "POST" else "finca.budget.read"
        return [rbac_permission(code)()]

    def get(self, request):
        finca_id = request.query_params.get("finca_id")
        budgets = list_budgets(request.company, finca_id=int(finca_id) if finca_id else None)
        return Response({"results": [budget_payload(b) for b in budgets]}, status=status.HTTP_200_OK)

    def post(self, request):
        s = BudgetCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            budget = create_budget(company=request.company, actor=request.user, request=request, **s.validated_data)
        except FincaBudgetError as exc:
            return _err(exc)
        return Response(budget_payload(budget), status=status.HTTP_201_CREATED)


class FincaBudgetDetailView(APIView):
    permission_classes = [rbac_permission("finca.budget.read")]

    def get(self, request, budget_id: int):
        try:
            budget = get_budget(request.company, budget_id)
        except FincaBudgetError as exc:
            return _err(exc)
        return Response(budget_payload(budget, include_lines=True), status=status.HTTP_200_OK)


class FincaBudgetLinesView(APIView):
    permission_classes = [rbac_permission("finca.budget.manage")]

    def put(self, request, budget_id: int):
        s = BudgetLinesIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            budget = upsert_lines(
                company=request.company, actor=request.user, budget_id=budget_id,
                lines=s.validated_data["lines"], request=request,
            )
        except FincaBudgetError as exc:
            return _err(exc)
        return Response(budget_payload(budget, include_lines=True), status=status.HTTP_200_OK)


class FincaBudgetApproveView(APIView):
    permission_classes = [rbac_permission("finca.budget.manage")]

    def post(self, request, budget_id: int):
        try:
            budget = approve_budget(company=request.company, actor=request.user, budget_id=budget_id, request=request)
        except FincaBudgetError as exc:
            return _err(exc)
        return Response(budget_payload(budget), status=status.HTTP_200_OK)


class FincaBudgetArchiveView(APIView):
    permission_classes = [rbac_permission("finca.budget.manage")]

    def post(self, request, budget_id: int):
        try:
            budget = archive_budget(company=request.company, actor=request.user, budget_id=budget_id, request=request)
        except FincaBudgetError as exc:
            return _err(exc)
        return Response(budget_payload(budget), status=status.HTTP_200_OK)


class FincaBudgetVsActualView(APIView):
    permission_classes = [rbac_permission("finca.budget.read")]

    def get(self, request, budget_id: int):
        try:
            data = budget_vs_actual(request.company, budget_id)
        except FincaBudgetError as exc:
            return _err(exc)
        return Response(data, status=status.HTTP_200_OK)
