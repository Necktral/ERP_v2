from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import rbac_permission

from modulos.estacion_servicios.models import FuelDispense, FuelSale, FuelShift
from modulos.estacion_servicios.serializers import (
    DispenseCreateIn,
    DispenseOut,
    SaleCancelIn,
    SaleCreateIn,
    SaleOut,
    ShiftCloseIn,
    ShiftOpenIn,
    ShiftOut,
)
from modulos.estacion_servicios.services import (
    cancel_sale,
    close_shift,
    create_sale,
    open_shift,
    record_dispense,
)


class FuelHealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "fuel"})


class FuelShiftOpenView(APIView):
    permission_classes = [rbac_permission("fuel.shift.open")]

    def post(self, request):
        ser = ShiftOpenIn(data=request.data)
        ser.is_valid(raise_exception=True)

        shift = open_shift(
            request=request,
            company=request.company,
            branch=request.branch,
            actor_user=request.user,
            opened_at=ser.validated_data.get("opened_at"),
            note=ser.validated_data.get("note", ""),
        )
        return Response(ShiftOut(shift).data, status=201)


class FuelShiftCloseView(APIView):
    permission_classes = [rbac_permission("fuel.shift.close")]

    def post(self, request, shift_id: int):
        ser = ShiftCloseIn(data=request.data)
        ser.is_valid(raise_exception=True)

        shift = get_object_or_404(FuelShift, pk=shift_id, company=request.company, branch=request.branch)

        shift = close_shift(
            request=request,
            shift=shift,
            actor_user=request.user,
            closed_at=ser.validated_data.get("closed_at"),
            note=ser.validated_data.get("note", ""),
        )
        return Response(ShiftOut(shift).data, status=200)


class FuelDispenseCreateView(APIView):
    permission_classes = [rbac_permission("fuel.dispense.create")]

    def post(self, request):
        ser = DispenseCreateIn(data=request.data)
        ser.is_valid(raise_exception=True)

        shift = get_object_or_404(
            FuelShift,
            pk=ser.validated_data["shift_id"],
            company=request.company,
            branch=request.branch,
        )

        dispense = record_dispense(
            request=request,
            company=request.company,
            branch=request.branch,
            shift=shift,
            actor_user=request.user,
            occurred_at=ser.validated_data.get("occurred_at"),
            product=ser.validated_data["product"],
            liters=ser.validated_data["liters"],
            unit_price=ser.validated_data["unit_price"],
            vehicle_plate=ser.validated_data.get("vehicle_plate", ""),
            vehicle_ref=ser.validated_data.get("vehicle_ref", ""),
            driver_name=ser.validated_data.get("driver_name", ""),
            pump_code=ser.validated_data.get("pump_code", ""),
            nozzle_code=ser.validated_data.get("nozzle_code", ""),
            meter_reading=ser.validated_data.get("meter_reading"),
            external_ref=ser.validated_data.get("external_ref", ""),
            note=ser.validated_data.get("note", ""),
        )
        return Response(DispenseOut(dispense).data, status=201)


class FuelSaleCreateView(APIView):
    permission_classes = [rbac_permission("fuel.sale.create")]

    def post(self, request):
        ser = SaleCreateIn(data=request.data)
        ser.is_valid(raise_exception=True)

        shift = get_object_or_404(
            FuelShift,
            pk=ser.validated_data["shift_id"],
            company=request.company,
            branch=request.branch,
        )

        dispense = get_object_or_404(
            FuelDispense,
            pk=ser.validated_data["dispense_id"],
            company=request.company,
            branch=request.branch,
        )

        sale = create_sale(
            request=request,
            company=request.company,
            branch=request.branch,
            shift=shift,
            dispense=dispense,
            actor_user=request.user,
            sale_type=ser.validated_data["sale_type"],
            payment_method=ser.validated_data["payment_method"],
            customer_name=ser.validated_data.get("customer_name", ""),
            customer_ref=ser.validated_data.get("customer_ref", ""),
            is_fiscal=ser.validated_data.get("is_fiscal", False),
        )

        sale = FuelSale.objects.select_related("dispense").get(pk=sale.id)
        return Response(SaleOut(sale).data, status=201)


class FuelSaleCancelView(APIView):
    permission_classes = [rbac_permission("fuel.sale.void")]

    def post(self, request, sale_id: int):
        ser = SaleCancelIn(data=request.data)
        ser.is_valid(raise_exception=True)

        sale = get_object_or_404(FuelSale, pk=sale_id, company=request.company, branch=request.branch)

        sale = cancel_sale(
            request=request,
            sale=sale,
            actor_user=request.user,
            reason=ser.validated_data.get("reason", ""),
        )

        sale = FuelSale.objects.select_related("dispense").get(pk=sale.id)
        return Response(SaleOut(sale).data, status=200)
