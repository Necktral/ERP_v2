"""Vistas de costos de flota (Ola G): combustible, mantenimiento, gastos y resumen."""
from __future__ import annotations

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.utils.dateparse import parse_date

from apps.modulos.common.permissions import rbac_permission

from .models import FleetExpense, FuelLog, MaintenanceWorkOrder
from .services import FleetError
from .services_costs import (
    asset_cost_summary,
    record_expense,
    record_fuel_log,
    record_work_order,
)


def _company(request):
    return getattr(request, "company", None)


def _err(exc: FleetError) -> Response:
    return Response({"detail": str(exc), "code": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class FuelLogIn(serializers.Serializer):
    liters = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=4)
    meter_reading = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, default=None)
    station_ref = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    driver_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class WorkOrderIn(serializers.Serializer):
    description = serializers.CharField(max_length=255)
    labor_cost = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=0)
    parts_cost = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=0)
    maintenance_type_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    status = serializers.CharField(max_length=12, required=False, default="DONE")
    meter_reading = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, default=None)
    vendor = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ExpenseIn(serializers.Serializer):
    category = serializers.CharField(max_length=12)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    occurred_on = serializers.DateField(required=False, allow_null=True, default=None)
    vendor = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


def _fuel_payload(f: FuelLog) -> dict:
    return {
        "id": f.id, "occurred_at": f.occurred_at.isoformat(), "liters": str(f.liters),
        "unit_cost": str(f.unit_cost), "total_cost": str(f.total_cost),
        "meter_reading": str(f.meter_reading) if f.meter_reading is not None else None,
        "distance_since_last": str(f.distance_since_last) if f.distance_since_last is not None else None,
        "station_ref": f.station_ref, "note": f.note,
    }


def _wo_payload(w: MaintenanceWorkOrder) -> dict:
    return {
        "id": w.id, "status": w.status, "status_label": w.get_status_display(), "description": w.description,
        "opened_at": w.opened_at.isoformat(), "completed_at": w.completed_at.isoformat() if w.completed_at else None,
        "labor_cost": str(w.labor_cost), "parts_cost": str(w.parts_cost), "total_cost": str(w.total_cost),
        "vendor": w.vendor, "note": w.note,
    }


def _exp_payload(e: FleetExpense) -> dict:
    return {
        "id": e.id, "category": e.category, "category_label": e.get_category_display(),
        "amount": str(e.amount), "occurred_on": str(e.occurred_on), "vendor": e.vendor, "note": e.note,
    }


class AssetFuelLogView(APIView):
    def get_permissions(self):
        code = "fleet.cost.read" if self.request.method == "GET" else "fleet.cost.manage"
        return [rbac_permission(code)()]

    def get(self, request, asset_id: int):
        rows = FuelLog.objects.filter(asset_id=asset_id, company=_company(request))[:200]
        return Response({"results": [_fuel_payload(f) for f in rows]}, status=status.HTTP_200_OK)

    def post(self, request, asset_id: int):
        s = FuelLogIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            log = record_fuel_log(request=request, company=_company(request), actor=request.user, asset_id=asset_id, **s.validated_data)
        except FleetError as exc:
            return _err(exc)
        return Response(_fuel_payload(log), status=status.HTTP_201_CREATED)


class AssetMaintenanceOrderView(APIView):
    def get_permissions(self):
        code = "fleet.cost.read" if self.request.method == "GET" else "fleet.cost.manage"
        return [rbac_permission(code)()]

    def get(self, request, asset_id: int):
        rows = MaintenanceWorkOrder.objects.filter(asset_id=asset_id, company=_company(request))[:200]
        return Response({"results": [_wo_payload(w) for w in rows]}, status=status.HTTP_200_OK)

    def post(self, request, asset_id: int):
        s = WorkOrderIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            wo = record_work_order(request=request, company=_company(request), actor=request.user, asset_id=asset_id, **s.validated_data)
        except FleetError as exc:
            return _err(exc)
        return Response(_wo_payload(wo), status=status.HTTP_201_CREATED)


class AssetExpenseView(APIView):
    def get_permissions(self):
        code = "fleet.cost.read" if self.request.method == "GET" else "fleet.cost.manage"
        return [rbac_permission(code)()]

    def get(self, request, asset_id: int):
        rows = FleetExpense.objects.filter(asset_id=asset_id, company=_company(request))[:200]
        return Response({"results": [_exp_payload(e) for e in rows]}, status=status.HTTP_200_OK)

    def post(self, request, asset_id: int):
        s = ExpenseIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            exp = record_expense(request=request, company=_company(request), actor=request.user, asset_id=asset_id, **s.validated_data)
        except FleetError as exc:
            return _err(exc)
        return Response(_exp_payload(exp), status=status.HTTP_201_CREATED)


class AssetCostSummaryView(APIView):
    permission_classes = [rbac_permission("fleet.cost.read")]

    def get(self, request, asset_id: int):
        date_from = parse_date(request.query_params.get("from", "") or "")
        date_to = parse_date(request.query_params.get("to", "") or "")
        try:
            summary = asset_cost_summary(company=_company(request), asset_id=asset_id, date_from=date_from, date_to=date_to)
        except FleetError as exc:
            return _err(exc)
        return Response(summary, status=status.HTTP_200_OK)
