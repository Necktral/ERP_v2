from __future__ import annotations

import uuid
from decimal import Decimal
from typing import ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Unidades de Medida
# ---------------------------------------------------------------------------

class UoM(models.TextChoices):
    # Conteo
    UNIT = "UNIT", "Unidad"
    DOZEN = "DOZEN", "Docena"
    PACK = "PACK", "Paquete"
    BOX = "BOX", "Caja"
    # Masa
    GRAM = "GRAM", "Gramo"
    KILOGRAM = "KILOGRAM", "Kilogramo"
    POUND = "POUND", "Libra"
    QUINTAL = "QUINTAL", "Quintal (100 lb)"
    TON = "TON", "Tonelada Métrica"
    # Volumen
    MILLILITER = "MILLILITER", "Mililitro"
    LITER = "LITER", "Litro"
    GALLON = "GALLON", "Galón"
    BARREL = "BARREL", "Barril"
    # Longitud / Área
    METER = "METER", "Metro"
    SQUARE_METER = "SQUARE_METER", "Metro Cuadrado"
    MANZANA = "MANZANA", "Manzana"
    # Tiempo
    HOUR = "HOUR", "Hora"
    DAY = "DAY", "Día"
    # Café
    GOLD_QUINTAL = "GOLD_QUINTAL", "Quintal Oro"
    WET_QUINTAL = "WET_QUINTAL", "Quintal Húmedo"
    DRY_QUINTAL = "DRY_QUINTAL", "Quintal Seco"


class StorageCondition(models.TextChoices):
    AMBIENT = "AMBIENT", "Ambiente"
    REFRIGERATED = "REFRIGERATED", "Refrigerado"
    FROZEN = "FROZEN", "Congelado"
    HAZMAT = "HAZMAT", "Material Peligroso"
    DRY = "DRY", "Seco / Ventilado"


class WarehouseType(models.TextChoices):
    GENERAL = "GENERAL", "General"
    AGROCHEMICAL = "AGROCHEMICAL", "Agroquímicos"
    COLD_STORAGE = "COLD_STORAGE", "Cámara Fría"
    FINISHED_GOODS = "FINISHED_GOODS", "Producto Terminado"
    RAW_MATERIALS = "RAW_MATERIALS", "Materia Prima"
    TOOLS = "TOOLS", "Herramientas y Equipos"
    FUEL = "FUEL", "Combustibles"
    TRANSIT = "TRANSIT", "En Tránsito"
    COFFEE = "COFFEE", "Café"


# ---------------------------------------------------------------------------
# Warehouse
# ---------------------------------------------------------------------------

class Warehouse(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_warehouses_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_warehouses_branch")

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=24, blank=True, default="")
    warehouse_type = models.CharField(
        max_length=20, choices=WarehouseType.choices, default=WarehouseType.GENERAL
    )
    location_description = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "inventarios"
        indexes = [
            models.Index(fields=["company", "branch", "is_active", "name"], name="ix_invwh_c_b_an"),
            models.Index(fields=["company", "branch", "code"], name="ix_invwh_c_b_code"),
            models.Index(fields=["company", "branch", "warehouse_type"], name="ix_invwh_c_b_type"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "branch", "code"],
                condition=~models.Q(code=""),
                name="uniq_inv_wh_code_pb",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})" if self.code else self.name


# ---------------------------------------------------------------------------
# InventoryItem
# ---------------------------------------------------------------------------

class InventoryItem(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_items_company")
    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    category = models.CharField(max_length=80, blank=True, default="")
    barcode = models.CharField(max_length=64, blank=True, default="")

    # Unidad de medida base (kardex siempre en esta unidad)
    uom = models.CharField(max_length=16, choices=UoM.choices, default=UoM.UNIT)

    # UoM de compra — se convierte a base_uom al recibir
    purchase_uom = models.CharField(max_length=16, choices=UoM.choices, blank=True, default="")
    purchase_uom_factor = models.DecimalField(
        max_digits=14, decimal_places=6, default=Decimal("1.000000"),
        help_text="Cuántas unidades base equivalen a 1 unidad de compra"
    )

    # UoM de venta / despacho
    sale_uom = models.CharField(max_length=16, choices=UoM.choices, blank=True, default="")
    sale_uom_factor = models.DecimalField(
        max_digits=14, decimal_places=6, default=Decimal("1.000000"),
        help_text="Cuántas unidades base equivalen a 1 unidad de venta"
    )

    # Niveles de stock
    reorder_point = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    min_stock_qty = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    max_stock_qty = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True,
        help_text="Capacidad máxima; null = sin límite"
    )

    # Configuración de trazabilidad
    track_lots = models.BooleanField(default=False, help_text="Requiere número de lote en cada movimiento")
    track_expiry = models.BooleanField(default=False, help_text="Registra fecha de vencimiento por lote")
    shelf_life_days = models.PositiveIntegerField(
        null=True, blank=True, help_text="Vida útil en días desde producción"
    )

    # Almacenamiento
    storage_condition = models.CharField(
        max_length=16, choices=StorageCondition.choices, default=StorageCondition.AMBIENT
    )
    is_controlled = models.BooleanField(
        default=False, help_text="Agroquímico u otro insumo que requiere registro especial"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="inv_items_created"
    )

    class Meta:
        app_label = "inventarios"
        indexes = [
            models.Index(fields=["company", "is_active", "sku"], name="ix_invitm_c_as"),
            models.Index(fields=["company", "is_active", "name"], name="ix_invitm_c_an"),
            models.Index(fields=["company", "category", "is_active"], name="ix_invitm_c_cat"),
            models.Index(fields=["company", "barcode"], name="ix_invitm_c_bc"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "sku"], name="uniq_inv_sku_pc"),
            models.UniqueConstraint(
                fields=["company", "barcode"],
                condition=~models.Q(barcode=""),
                name="uniq_inv_barcode_pc",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku} - {self.name}"

    def clean(self) -> None:
        super().clean()
        if self.purchase_uom_factor is not None and self.purchase_uom_factor <= 0:
            raise ValidationError({"purchase_uom_factor": "Debe ser mayor a cero."})
        if self.sale_uom_factor is not None and self.sale_uom_factor <= 0:
            raise ValidationError({"sale_uom_factor": "Debe ser mayor a cero."})
        if self.track_expiry and not self.track_lots:
            raise ValidationError({"track_expiry": "track_expiry requiere track_lots = True."})


# ---------------------------------------------------------------------------
# ItemLot — Lote / Partida
# ---------------------------------------------------------------------------

class LotStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Activo"
    QUARANTINE = "QUARANTINE", "Cuarentena"
    EXPIRED = "EXPIRED", "Vencido"
    RECALLED = "RECALLED", "Recall / Devuelto"
    EXHAUSTED = "EXHAUSTED", "Agotado"


class ItemLot(models.Model):
    """Lote o partida de un ítem. Solo se usa cuando item.track_lots = True."""

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_lots_company")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="lots")

    lot_number = models.CharField(max_length=80, db_index=True)
    supplier_lot_ref = models.CharField(max_length=80, blank=True, default="")

    production_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)

    status = models.CharField(max_length=16, choices=LotStatus.choices, default=LotStatus.ACTIVE, db_index=True)
    quarantine_reason = models.CharField(max_length=255, blank=True, default="")

    qty_received = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    notes = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="inv_lots_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "inventarios"
        constraints = [
            models.UniqueConstraint(fields=["company", "item", "lot_number"], name="uniq_inv_lot_item_number"),
        ]
        indexes = [
            models.Index(fields=["company", "item", "status"], name="ix_invlot_c_i_st"),
            models.Index(fields=["expiry_date", "status"], name="ix_invlot_exp_st"),
        ]

    def __str__(self) -> str:
        return f"Lote {self.lot_number} / {self.item.sku}"

    def clean(self) -> None:
        super().clean()
        if self.production_date and self.expiry_date and self.expiry_date < self.production_date:
            raise ValidationError({"expiry_date": "Vencimiento no puede ser anterior a la fecha de producción."})

    @property
    def is_expired(self) -> bool:
        if not self.expiry_date:
            return False
        return self.expiry_date < timezone.localdate()

    @property
    def days_to_expiry(self) -> int | None:
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.localdate()).days


# ---------------------------------------------------------------------------
# StockBalance — Balance agregado por (company, branch, warehouse, item)
# ---------------------------------------------------------------------------

class StockBalance(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_bal_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_bal_branch")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="balances")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="balances")

    qty_on_hand = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    qty_reserved = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.0000"),
        help_text="Cantidad reservada por órdenes pendientes"
    )
    avg_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "inventarios"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "branch", "warehouse", "item"],
                name="uniq_inv_bal_scope",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "warehouse", "item"], name="ix_invbal_scope"),
            models.Index(fields=["company", "item"], name="ix_invbal_c_item"),
        ]

    @property
    def qty_available(self) -> Decimal:
        return self.qty_on_hand - self.qty_reserved

    def __str__(self) -> str:
        return f"{self.item.sku} @ {self.warehouse.name}: {self.qty_on_hand}"


# ---------------------------------------------------------------------------
# LotBalance — Balance por lote (solo ítems con track_lots=True)
# ---------------------------------------------------------------------------

class LotBalance(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_lotbal_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_lotbal_branch")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="lot_balances")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="lot_balances")
    lot = models.ForeignKey(ItemLot, on_delete=models.PROTECT, related_name="balances")

    qty_on_hand = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    avg_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "inventarios"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "branch", "warehouse", "item", "lot"],
                name="uniq_inv_lotbal_scope",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "warehouse", "item", "lot"], name="ix_invlotbal_scope"),
            models.Index(fields=["lot", "qty_on_hand"], name="ix_invlotbal_lot_qty"),
        ]

    def __str__(self) -> str:
        return f"{self.item.sku} Lote:{self.lot.lot_number} @ {self.warehouse.name}: {self.qty_on_hand}"


# ---------------------------------------------------------------------------
# MovementType
# ---------------------------------------------------------------------------

class MovementType(models.TextChoices):
    RECEIVE = "RECEIVE", "Recepción"
    ISSUE = "ISSUE", "Despacho"
    ADJUST = "ADJUST", "Ajuste"
    TRANSFER_OUT = "TRANSFER_OUT", "Transferencia Salida"
    TRANSFER_IN = "TRANSFER_IN", "Transferencia Entrada"
    RETURN = "RETURN", "Devolución a Proveedor"
    SHRINKAGE = "SHRINKAGE", "Merma / Pérdida"
    PRODUCTION_IN = "PRODUCTION_IN", "Entrada de Producción"
    PRODUCTION_OUT = "PRODUCTION_OUT", "Salida a Producción"
    PHYSICAL_COUNT = "PHYSICAL_COUNT", "Conteo Físico"


# ---------------------------------------------------------------------------
# StockMovement — Kardex
# ---------------------------------------------------------------------------

class StockMovement(models.Model):
    class AccountingStatus(models.TextChoices):
        DISABLED = "DISABLED", "Disabled"
        UNSUPPORTED = "UNSUPPORTED", "Unsupported"
        PENDING_RULESET = "PENDING_RULESET", "Pending ruleset"
        PENDING_RULE = "PENDING_RULE", "Pending rule"
        DRAFT_EXCEPTION = "DRAFT_EXCEPTION", "Draft exception"
        DRAFT_VALIDATED = "DRAFT_VALIDATED", "Draft validated"
        POSTED = "POSTED", "Posted"

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_mov_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inv_mov_branch")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="movements")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="movements")

    movement_type = models.CharField(max_length=16, choices=MovementType.choices, db_index=True)
    qty_delta = models.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    total_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    # UoM en que se realizó el movimiento (puede diferir del uom base del ítem)
    movement_uom = models.CharField(max_length=16, choices=UoM.choices, blank=True, default="")
    movement_uom_factor = models.DecimalField(
        max_digits=14, decimal_places=6, default=Decimal("1.000000"),
        help_text="Factor de conversión aplicado al recibir/despachar en UoM distinta"
    )

    # Lote (solo cuando item.track_lots = True)
    lot = models.ForeignKey(
        ItemLot, null=True, blank=True, on_delete=models.PROTECT, related_name="movements"
    )
    expiry_date = models.DateField(
        null=True, blank=True, db_index=True,
        help_text="Vencimiento del lote en este movimiento (desnormalizado para queries)"
    )

    # Referencia al origen para trazabilidad
    source_module = models.CharField(max_length=32, blank=True, default="")
    source_type = models.CharField(max_length=64, blank=True, default="")
    source_id = models.CharField(max_length=64, blank=True, default="")

    note = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=96, blank=True, default="")

    # Reversa de primera clase (invariante #1: no borrar histórico, solo reversas).
    reversal_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversals"
    )
    reversed_at = models.DateTimeField(null=True, blank=True)

    accounting_status = models.CharField(
        max_length=24, choices=AccountingStatus.choices, blank=True, default=""
    )
    accounting_error = models.CharField(max_length=255, blank=True, default="")
    accounting_economic_event = models.ForeignKey(
        "accounting.EconomicEvent", null=True, blank=True,
        on_delete=models.PROTECT, related_name="inventory_movements",
    )
    accounting_journal_draft = models.ForeignKey(
        "accounting.JournalDraft", null=True, blank=True,
        on_delete=models.PROTECT, related_name="inventory_movements",
    )
    accounting_journal_entry = models.ForeignKey(
        "accounting.JournalEntry", null=True, blank=True,
        on_delete=models.PROTECT, related_name="inventory_movements",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "inventarios"
        indexes = [
            models.Index(fields=["company", "branch", "created_at"], name="ix_invmov_c_b_ca"),
            models.Index(fields=["company", "branch", "item", "created_at"], name="ix_invmov_item_ca"),
            models.Index(fields=["company", "branch", "warehouse", "created_at"], name="ix_invmov_wh_ca"),
            models.Index(fields=["company", "idempotency_key"], name="ix_invmov_idem"),
            models.Index(fields=["company", "branch", "accounting_status", "created_at"], name="ix_invmov_acc_st"),
            models.Index(fields=["company", "branch", "movement_type", "created_at"], name="ix_invmov_type_ca"),
            models.Index(fields=["lot", "created_at"], name="ix_invmov_lot_ca"),
            models.Index(fields=["expiry_date", "movement_type"], name="ix_invmov_exp_type"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_invmov_idem",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.movement_type} {self.item.sku} qty={self.qty_delta}"


# ---------------------------------------------------------------------------
# Remisiones (despacho + recepción/cotejo con evidencia)
# ---------------------------------------------------------------------------


class RemisionOriginType(models.TextChoices):
    PURCHASE = "PURCHASE", "Compra a proveedor"
    INTERNAL_TRANSFER = "INTERNAL_TRANSFER", "Traslado inter-sucursal"


class RemisionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    DISPATCHED = "DISPATCHED", "Despachada"
    RECEIVED = "RECEIVED", "Recibida"
    CANCELLED = "CANCELLED", "Cancelada"


class Remision(models.Model):
    """Documento de remisión: el punto A despacha mercancía hacia la bodega del
    punto B, donde el bodeguero la recibe y coteja contra el físico. Al recibir,
    los artículos entran a inventario (post_receive). Soporta origen genérico
    (compra a proveedor o traslado interno) y evidencia fotográfica."""

    remision_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="remisiones_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="remisiones_branch")

    origin_type = models.CharField(max_length=24, choices=RemisionOriginType.choices)
    # Referencia genérica al documento fuente (factura de compra/venta).
    source_module = models.CharField(max_length=32, blank=True, default="")
    source_type = models.CharField(max_length=64, blank=True, default="")
    source_id = models.CharField(max_length=64, blank=True, default="")

    origin_warehouse = models.ForeignKey(
        Warehouse, null=True, blank=True, on_delete=models.PROTECT, related_name="remisiones_origin"
    )
    dest_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="remisiones_dest")

    status = models.CharField(max_length=16, choices=RemisionStatus.choices, default=RemisionStatus.DRAFT, db_index=True)
    has_discrepancy = models.BooleanField(default=False)
    note = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=96, blank=True, default="")

    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="remisiones_dispatched"
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="remisiones_received"
    )
    received_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="remisiones_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    _ALLOWED_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        RemisionStatus.DRAFT: {RemisionStatus.DISPATCHED, RemisionStatus.CANCELLED},
        RemisionStatus.DISPATCHED: {RemisionStatus.RECEIVED, RemisionStatus.CANCELLED},
        RemisionStatus.RECEIVED: set(),
        RemisionStatus.CANCELLED: set(),
    }

    class Meta:
        app_label = "inventarios"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_remision_idem",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "status", "created_at"], name="ix_remision_scope"),
            models.Index(fields=["company", "dest_warehouse", "status"], name="ix_remision_dest"),
        ]

    def can_transition_to(self, target_status: str) -> bool:
        if target_status == self.status:
            return True
        return target_status in self._ALLOWED_TRANSITIONS.get(self.status, set())

    def __str__(self) -> str:
        return f"Remision {self.remision_id} [{self.status}]"


class RemisionLine(models.Model):
    remision = models.ForeignKey(Remision, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="remision_lines")
    description = models.CharField(max_length=200, blank=True, default="")

    qty_dispatched = models.DecimalField(max_digits=18, decimal_places=4)
    qty_received = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0.0000"))
    unit_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    received_movement = models.ForeignKey(
        StockMovement, null=True, blank=True, on_delete=models.SET_NULL, related_name="remision_lines"
    )
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        app_label = "inventarios"
        indexes = [models.Index(fields=["remision", "item"], name="ix_remisionline_remi_item")]

    @property
    def discrepancy(self) -> Decimal:
        return Decimal(self.qty_received) - Decimal(self.qty_dispatched)

    def __str__(self) -> str:
        return f"{self.item.sku}: disp={self.qty_dispatched} recv={self.qty_received}"


class RemisionPhoto(models.Model):
    """Evidencia fotográfica adjunta por el gerente de compras (por referencia)."""

    remision = models.ForeignKey(Remision, on_delete=models.CASCADE, related_name="photos")
    storage_ref = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    mime_type = models.CharField(max_length=64, blank=True, default="image/jpeg")
    caption = models.CharField(max_length=255, blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="remision_photos"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "inventarios"
        indexes = [models.Index(fields=["remision", "created_at"], name="ix_remisionphoto_remi")]

    def __str__(self) -> str:
        return f"Photo {self.storage_ref} @ remision {self.remision_id}"


# ---------------------------------------------------------------------------
# Política de costo versionada y estable por ciclo (invariante #8)
# ---------------------------------------------------------------------------


class CostingMethod(models.TextChoices):
    WEIGHTED_AVERAGE = "WEIGHTED_AVERAGE", "Promedio ponderado (móvil)"
    STANDARD = "STANDARD", "Costo estándar"
    FIFO = "FIFO", "PEPS (primeras entradas)"


class InventoryCostPolicy(models.Model):
    """Política de costo **versionada** por scope (empresa o sucursal).

    Invariante #8 / anti-patrón #4: el costo no se muta sin versionado. Cada
    cambio de método cierra la versión activa (effective_to) y crea una versión
    nueva inmutable, de modo que los movimientos ya posteados conservan el método
    bajo el que se costearon (estabilidad por ciclo, reproducibilidad #11).
    `branch` NULL = política a nivel empresa (fallback de las sucursales).
    """

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="cost_policies_company")
    branch = models.ForeignKey(
        "iam.OrgUnit", null=True, blank=True, on_delete=models.PROTECT, related_name="cost_policies_branch"
    )

    method = models.CharField(max_length=24, choices=CostingMethod.choices, default=CostingMethod.WEIGHTED_AVERAGE)
    version = models.PositiveIntegerField(default=1)
    params = models.JSONField(default=dict, blank=True)

    is_active = models.BooleanField(default=True)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_to = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="cost_policies_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "inventarios"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "branch", "version"], name="uq_cost_policy_scope_version"
            ),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "is_active"], name="ix_cost_policy_active"),
            models.Index(fields=["company", "branch", "effective_from"], name="ix_cost_policy_eff"),
        ]

    def __str__(self) -> str:
        scope = f"company={self.company_id}" + (f" branch={self.branch_id}" if self.branch_id else "")
        return f"CostPolicy[{scope}] v{self.version} {self.method} active={self.is_active}"
