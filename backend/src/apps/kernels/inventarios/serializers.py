from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import InventoryItem, ItemLot, LotBalance, StockBalance, StockMovement, UoM, Warehouse, WarehouseType


# ---------------------------------------------------------------------------
# Input serializers (commands)
# ---------------------------------------------------------------------------

class WarehouseCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    code = serializers.CharField(max_length=24, required=False, allow_blank=True)
    warehouse_type = serializers.ChoiceField(choices=WarehouseType.choices, required=False, default=WarehouseType.GENERAL)
    location_description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_default = serializers.BooleanField(required=False, default=False)


class ItemCreateSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    category = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    barcode = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    uom = serializers.ChoiceField(choices=UoM.choices, required=False, default=UoM.UNIT)
    purchase_uom = serializers.ChoiceField(choices=UoM.choices, required=False, allow_blank=True, default="")
    purchase_uom_factor = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default=Decimal("1.000000"))
    sale_uom = serializers.ChoiceField(choices=UoM.choices, required=False, allow_blank=True, default="")
    sale_uom_factor = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default=Decimal("1.000000"))
    reorder_point = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, default=Decimal("0.0000"))
    min_stock_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, default=Decimal("0.0000"))
    max_stock_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True, default=None)
    track_lots = serializers.BooleanField(required=False, default=False)
    track_expiry = serializers.BooleanField(required=False, default=False)
    shelf_life_days = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=1)
    storage_condition = serializers.CharField(max_length=16, required=False, default="AMBIENT")
    is_controlled = serializers.BooleanField(required=False, default=False)


class LotCreateSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    lot_number = serializers.CharField(max_length=80)
    supplier_lot_ref = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    production_date = serializers.DateField(required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class MovementReceiveSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=6)
    lot_id = serializers.IntegerField(required=False, allow_null=True)
    lot_number = serializers.CharField(max_length=80, required=False, allow_blank=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    movement_uom = serializers.ChoiceField(choices=UoM.choices, required=False, allow_blank=True, default="")
    movement_uom_factor = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default=Decimal("1.000000"))
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)
    source_module = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    source_type = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    source_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class MovementIssueSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    lot_id = serializers.IntegerField(required=False, allow_null=True)
    movement_uom = serializers.ChoiceField(choices=UoM.choices, required=False, allow_blank=True, default="")
    movement_uom_factor = serializers.DecimalField(max_digits=14, decimal_places=6, required=False, default=Decimal("1.000000"))
    allow_negative = serializers.BooleanField(required=False, default=False)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)
    source_module = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    source_type = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    source_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class MovementAdjustSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    new_qty_on_hand = serializers.DecimalField(max_digits=18, decimal_places=4)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class TransferSerializer(serializers.Serializer):
    from_warehouse_id = serializers.IntegerField()
    to_warehouse_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    lot_id = serializers.IntegerField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# Output serializers (read)
# ---------------------------------------------------------------------------

class WarehouseOut(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = [
            "id", "name", "code", "warehouse_type", "location_description",
            "is_active", "is_default", "created_at", "updated_at",
        ]


class InventoryItemOut(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = [
            "id", "sku", "name", "description", "category", "barcode",
            "uom", "purchase_uom", "purchase_uom_factor",
            "sale_uom", "sale_uom_factor",
            "reorder_point", "min_stock_qty", "max_stock_qty",
            "track_lots", "track_expiry", "shelf_life_days",
            "storage_condition", "is_controlled",
            "is_active", "created_at", "updated_at",
        ]


class ItemLotOut(serializers.ModelSerializer):
    is_expired = serializers.BooleanField(read_only=True)
    days_to_expiry = serializers.IntegerField(read_only=True)

    class Meta:
        model = ItemLot
        fields = [
            "id", "lot_number", "supplier_lot_ref",
            "production_date", "expiry_date",
            "status", "quarantine_reason",
            "qty_received", "notes",
            "is_expired", "days_to_expiry",
            "created_at", "updated_at",
        ]


class StockBalanceOut(serializers.ModelSerializer):
    item_sku = serializers.CharField(source="item.sku", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    item_uom = serializers.CharField(source="item.uom", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    qty_available = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = StockBalance
        fields = [
            "id", "item", "item_sku", "item_name", "item_uom",
            "warehouse", "warehouse_name",
            "qty_on_hand", "qty_reserved", "qty_available", "avg_cost",
            "updated_at",
        ]


class LotBalanceOut(serializers.ModelSerializer):
    lot_number = serializers.CharField(source="lot.lot_number", read_only=True)
    expiry_date = serializers.DateField(source="lot.expiry_date", read_only=True)
    lot_status = serializers.CharField(source="lot.status", read_only=True)

    class Meta:
        model = LotBalance
        fields = [
            "id", "lot", "lot_number", "expiry_date", "lot_status",
            "qty_on_hand", "avg_cost", "updated_at",
        ]


class StockMovementOut(serializers.ModelSerializer):
    item_sku = serializers.CharField(source="item.sku", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    lot_number = serializers.CharField(source="lot.lot_number", read_only=True, allow_null=True)

    class Meta:
        model = StockMovement
        fields = [
            "id", "movement_type",
            "item", "item_sku", "warehouse", "warehouse_name",
            "qty_delta", "unit_cost", "total_cost",
            "movement_uom", "movement_uom_factor",
            "lot", "lot_number", "expiry_date",
            "source_module", "source_type", "source_id",
            "note", "idempotency_key",
            "accounting_status", "accounting_error",
            "created_at",
        ]
