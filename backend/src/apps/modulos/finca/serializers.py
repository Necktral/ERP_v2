from __future__ import annotations

from rest_framework import serializers

from .models import FincaProfile, Labor, Plot, WorkOrder


class FincaProfileOut(serializers.ModelSerializer):
    finca_id = serializers.IntegerField(source="finca.id", read_only=True)

    class Meta:
        model = FincaProfile
        fields = [
            "finca_id",
            "department",
            "municipio",
            "zona",
            "area_manzanas",
            "is_headquarters",
            "gps_lat",
            "gps_lng",
            "notes",
        ]


class FincaProfileIn(serializers.Serializer):
    department = serializers.CharField(required=False, allow_blank=True)
    municipio = serializers.CharField(required=False, allow_blank=True)
    zona = serializers.CharField(required=False, allow_blank=True)
    area_manzanas = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    is_headquarters = serializers.BooleanField(required=False)
    gps_lat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    gps_lng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class PlotOut(serializers.ModelSerializer):
    class Meta:
        model = Plot
        fields = [
            "id", "finca_id", "code", "name", "area_manzanas", "crop", "variety", "planting_year", "is_active"
        ]


class PlotCreateIn(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    area_manzanas = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    crop = serializers.CharField(max_length=40, required=False, default="CAFE")
    variety = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    planting_year = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)


class PlotUpdateIn(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    area_manzanas = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    variety = serializers.CharField(max_length=120, required=False, allow_blank=True)
    planting_year = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)


class LaborOut(serializers.ModelSerializer):
    is_global = serializers.SerializerMethodField()

    class Meta:
        model = Labor
        fields = [
            "id", "company_id", "is_global", "code", "name", "category", "unit",
            "is_piecework", "expected_yield", "default_rate", "is_active",
        ]

    def get_is_global(self, obj) -> bool:
        return obj.company_id is None


class LaborCreateIn(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=160)
    category = serializers.ChoiceField(choices=[c[0] for c in Labor._meta.get_field("category").choices])
    unit = serializers.ChoiceField(choices=[c[0] for c in Labor._meta.get_field("unit").choices])
    is_piecework = serializers.BooleanField(required=False, default=False)
    expected_yield = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    default_rate = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)


class WorkOrderOut(serializers.ModelSerializer):
    class Meta:
        model = WorkOrder
        fields = [
            "id", "finca_id", "plot_id", "labor_id", "season_label", "planned_date", "done_date",
            "supervisor_id", "status", "target_quantity", "actual_quantity", "jornales", "notes", "external_ref",
        ]


class WorkOrderCreateIn(serializers.Serializer):
    plot_id = serializers.IntegerField()
    labor_id = serializers.IntegerField()
    season_label = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    planned_date = serializers.DateField(required=False, allow_null=True)
    done_date = serializers.DateField(required=False, allow_null=True)
    supervisor_id = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=[c[0] for c in WorkOrder.Status.choices], required=False, default=WorkOrder.Status.PLANNED
    )
    target_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    actual_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    jornales = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    external_ref = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class WorkOrderUpdateIn(serializers.Serializer):
    status = serializers.ChoiceField(choices=[c[0] for c in WorkOrder.Status.choices], required=False)
    done_date = serializers.DateField(required=False, allow_null=True)
    target_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    actual_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    jornales = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    season_label = serializers.CharField(max_length=80, required=False, allow_blank=True)


class InsumoIn(serializers.Serializer):
    item_code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    item_name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit = serializers.CharField(max_length=24, required=False, allow_blank=True, default="")
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class IssueInsumoIn(serializers.Serializer):
    """Consumo de insumo desde stock real (#2): descuenta inventario vía post_issue."""

    warehouse_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
    idempotency_key = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class FincaCostPostIn(serializers.Serializer):
    """Disparo del asiento de reclasificación del costo real de una finca (#1)."""

    finca_id = serializers.IntegerField()
    season = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to = serializers.DateField(required=False, allow_null=True)
