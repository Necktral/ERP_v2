from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import (
    AssetStatus,
    AssetType,
    DocumentType,
    FuelType,
    MaintenanceKind,
    MeterBasis,
    ObdProtocol,
    TriggerBasis,
)


class AssetUpsertSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=160)
    asset_type = serializers.ChoiceField(choices=AssetType.choices)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    plate = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    vin = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    make = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    model = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    year = serializers.IntegerField(required=False, allow_null=True)
    engine_desc = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    fuel_type = serializers.ChoiceField(choices=FuelType.choices, required=False, default=FuelType.DIESEL)
    tank_capacity_l = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal("0.00"))
    meter_basis = serializers.ChoiceField(choices=MeterBasis.choices, required=False, default=MeterBasis.ODOMETER_KM)
    current_odometer_km = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"))
    current_hourmeter = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0.00"))
    has_obd = serializers.BooleanField(required=False, default=False)
    obd_protocol = serializers.ChoiceField(choices=ObdProtocol.choices, required=False, default=ObdProtocol.NONE)
    status = serializers.ChoiceField(choices=AssetStatus.choices, required=False, default=AssetStatus.ACTIVE)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class DriverUpsertSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=160)
    employee_id = serializers.IntegerField(required=False, allow_null=True)
    national_id = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    license_number = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    license_category = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    license_expiry = serializers.DateField(required=False, allow_null=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class AssignDriverSerializer(serializers.Serializer):
    asset_id = serializers.IntegerField(min_value=1)
    driver_id = serializers.IntegerField(min_value=1)


class RecordMeterSerializer(serializers.Serializer):
    asset_id = serializers.IntegerField(min_value=1)
    odometer_km = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    hourmeter = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)


class DocumentSerializer(serializers.Serializer):
    doc_type = serializers.ChoiceField(choices=DocumentType.choices)
    asset_id = serializers.IntegerField(required=False, allow_null=True)
    driver_id = serializers.IntegerField(required=False, allow_null=True)
    number = serializers.CharField(max_length=96, required=False, allow_blank=True, default="")
    issuer = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    issue_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    file_ref = serializers.CharField(max_length=512, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class MaintenanceTypeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=48)
    name = serializers.CharField(max_length=160)
    kind = serializers.ChoiceField(choices=MaintenanceKind.choices, required=False, default=MaintenanceKind.PREVENTIVE)
    trigger_basis = serializers.ChoiceField(choices=TriggerBasis.choices, required=False, default=TriggerBasis.KM)
    default_action = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class PlanSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    asset_class = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class RuleSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(min_value=1)
    maintenance_type_id = serializers.IntegerField(min_value=1)
    trigger_basis = serializers.ChoiceField(choices=TriggerBasis.choices)
    interval_km = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    interval_hours = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    interval_days = serializers.IntegerField(required=False, allow_null=True)
    severity_factor = serializers.DecimalField(max_digits=4, decimal_places=2, required=False, default=Decimal("1.00"))
    recommended_action = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ApplyPlanSerializer(serializers.Serializer):
    asset_id = serializers.IntegerField(min_value=1)
    plan_id = serializers.IntegerField(min_value=1)
