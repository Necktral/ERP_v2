from __future__ import annotations

from rest_framework import serializers

from modulos.estacion_servicios.models import (
    FuelDispense,
    FuelPaymentMethod,
    FuelProduct,
    FuelSale,
    FuelSaleType,
    FuelShift,
)


class ShiftOpenIn(serializers.Serializer):
    opened_at = serializers.DateTimeField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class ShiftOut(serializers.ModelSerializer):
    class Meta:
        model = FuelShift
        fields = ["id", "status", "opened_at", "closed_at", "note"]


class ShiftCloseIn(serializers.Serializer):
    closed_at = serializers.DateTimeField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class DispenseCreateIn(serializers.Serializer):
    shift_id = serializers.IntegerField()
    occurred_at = serializers.DateTimeField(required=False)

    product = serializers.ChoiceField(choices=FuelProduct.choices)

    liters = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=4)

    vehicle_plate = serializers.CharField(required=False, allow_blank=True, max_length=32)
    vehicle_ref = serializers.CharField(required=False, allow_blank=True, max_length=64)
    driver_name = serializers.CharField(required=False, allow_blank=True, max_length=120)

    pump_code = serializers.CharField(required=False, allow_blank=True, max_length=32)
    nozzle_code = serializers.CharField(required=False, allow_blank=True, max_length=32)
    meter_reading = serializers.DecimalField(max_digits=14, decimal_places=3, required=False, allow_null=True)

    external_ref = serializers.CharField(required=False, allow_blank=True, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class DispenseOut(serializers.ModelSerializer):
    class Meta:
        model = FuelDispense
        fields = [
            "id",
            "occurred_at",
            "product",
            "liters",
            "unit_price",
            "amount",
            "vehicle_plate",
            "vehicle_ref",
            "driver_name",
            "pump_code",
            "nozzle_code",
            "meter_reading",
            "external_ref",
            "note",
        ]


class SaleCreateIn(serializers.Serializer):
    shift_id = serializers.IntegerField()
    dispense_id = serializers.IntegerField()

    sale_type = serializers.ChoiceField(choices=FuelSaleType.choices)
    payment_method = serializers.ChoiceField(choices=FuelPaymentMethod.choices)

    customer_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    customer_ref = serializers.CharField(required=False, allow_blank=True, max_length=64)

    is_fiscal = serializers.BooleanField(required=False)


class SaleCancelIn(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class SaleOut(serializers.ModelSerializer):
    dispense = DispenseOut()

    class Meta:
        model = FuelSale
        fields = [
            "id",
            "status",
            "sale_type",
            "payment_method",
            "customer_name",
            "customer_ref",
            "total_amount",
            "is_fiscal",
            "created_at",
            "dispense",
            "cancelled_at",
            "cancel_reason",
        ]
