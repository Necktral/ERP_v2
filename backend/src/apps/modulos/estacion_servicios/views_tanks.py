"""Vistas de tanques (Ola G). Reusa permisos existentes: fuel.tank.read/receive/adjust
y fuel.config.update (crear/editar tanque es config de estación)."""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission

from .models import FuelTank
from .tank_service import (
    adjust_tank,
    create_tank,
    list_tanks,
    receive_fuel,
    tank_movements,
    update_tank,
)


def _tank_payload(t: FuelTank) -> dict:
    capacity = Decimal(t.capacity_l or 0)
    level = Decimal(t.current_volume_l or 0)
    pct = float((level / capacity * 100)) if capacity > 0 else None
    return {
        "id": t.id,
        "branch_id": t.branch_id,
        "code": t.code,
        "product": t.product,
        "product_label": t.get_product_display(),
        "capacity_l": str(t.capacity_l),
        "current_volume_l": str(t.current_volume_l),
        "low_level_l": str(t.low_level_l),
        "pct": round(pct, 1) if pct is not None else None,
        "is_low": bool(Decimal(t.low_level_l or 0) > 0 and level <= Decimal(t.low_level_l)),
        "is_active": t.is_active,
    }


def _movement_payload(m) -> dict:
    return {
        "id": m.id,
        "kind": m.kind,
        "kind_label": m.get_kind_display(),
        "liters": str(m.liters),
        "unit_cost": str(m.unit_cost) if m.unit_cost is not None else None,
        "occurred_at": m.occurred_at.isoformat(),
        "supplier_name": m.supplier_name,
        "document_ref": m.document_ref,
        "note": m.note,
    }


class TankCreateIn(serializers.Serializer):
    code = serializers.CharField(max_length=32)
    product = serializers.CharField(max_length=16)
    capacity_l = serializers.DecimalField(max_digits=12, decimal_places=2)
    low_level_l = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0"))


class TankUpdateIn(serializers.Serializer):
    capacity_l = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    low_level_l = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    is_active = serializers.BooleanField(required=False)


class TankReceiveIn(serializers.Serializer):
    liters = serializers.DecimalField(max_digits=14, decimal_places=4)
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=4, required=False, allow_null=True, default=None)
    supplier_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    document_ref = serializers.CharField(max_length=96, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class TankAdjustIn(serializers.Serializer):
    liters = serializers.DecimalField(max_digits=14, decimal_places=4)
    reason = serializers.CharField(max_length=255)


class FuelTankListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("fuel.config.update")()]
        return [rbac_permission("fuel.tank.read")()]

    def get(self, request):
        tanks = list_tanks(company=request.company, branch=request.branch)
        return Response({"results": [_tank_payload(t) for t in tanks]}, status=status.HTTP_200_OK)

    def post(self, request):
        if request.branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=status.HTTP_400_BAD_REQUEST)
        ser = TankCreateIn(data=request.data)
        ser.is_valid(raise_exception=True)
        tank = create_tank(
            request=request, company=request.company, branch=request.branch, actor=request.user,
            **ser.validated_data,
        )
        return Response(_tank_payload(tank), status=status.HTTP_201_CREATED)


class FuelTankDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "PATCH":
            return [rbac_permission("fuel.config.update")()]
        return [rbac_permission("fuel.tank.read")()]

    def _get(self, request, tank_id):
        return FuelTank.objects.filter(id=tank_id, company=request.company).first()

    def get(self, request, tank_id: int):
        tank = self._get(request, tank_id)
        if tank is None:
            return Response({"detail": "Tanque no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        out = _tank_payload(tank)
        out["movements"] = [_movement_payload(m) for m in tank_movements(tank)]
        return Response(out, status=status.HTTP_200_OK)

    def patch(self, request, tank_id: int):
        ser = TankUpdateIn(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        tank = update_tank(request=request, company=request.company, actor=request.user, tank_id=tank_id, **ser.validated_data)
        return Response(_tank_payload(tank), status=status.HTTP_200_OK)


class FuelTankReceiveView(APIView):
    permission_classes = [rbac_permission("fuel.tank.receive")]

    def post(self, request, tank_id: int):
        ser = TankReceiveIn(data=request.data)
        ser.is_valid(raise_exception=True)
        receive_fuel(request=request, company=request.company, actor=request.user, tank_id=tank_id, **ser.validated_data)
        tank = FuelTank.objects.filter(id=tank_id, company=request.company).first()
        return Response(_tank_payload(tank), status=status.HTTP_200_OK)


class FuelTankAdjustView(APIView):
    permission_classes = [rbac_permission("fuel.tank.adjust")]

    def post(self, request, tank_id: int):
        ser = TankAdjustIn(data=request.data)
        ser.is_valid(raise_exception=True)
        adjust_tank(request=request, company=request.company, actor=request.user, tank_id=tank_id, **ser.validated_data)
        tank = FuelTank.objects.filter(id=tank_id, company=request.company).first()
        return Response(_tank_payload(tank), status=status.HTTP_200_OK)
