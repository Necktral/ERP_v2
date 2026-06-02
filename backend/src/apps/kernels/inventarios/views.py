from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset as _paginate
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit

from .models import InventoryItem, ItemLot, LotBalance, StockBalance, StockMovement, Warehouse
from .serializers import (
    InventoryItemOut,
    ItemCreateSerializer,
    ItemLotOut,
    LotBalanceOut,
    LotCreateSerializer,
    MovementAdjustSerializer,
    MovementIssueSerializer,
    MovementReceiveSerializer,
    StockBalanceOut,
    StockMovementOut,
    TransferSerializer,
    WarehouseCreateSerializer,
    WarehouseOut,
)
from .services import InventoryConflictError, create_item, create_lot, create_warehouse, post_adjust, post_issue, post_receive, post_transfer


def _movement_post_response(result) -> dict:
    return {
        "movement_id": result.movement_id,
        "qty_on_hand": str(result.qty_on_hand),
        "avg_cost": str(result.avg_cost),
        "accounting_status": result.accounting_status,
        "accounting_error": result.accounting_error,
        "journal_draft_id": result.accounting_journal_draft_id,
        "journal_entry_id": result.accounting_journal_entry_id,
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "inventory"})


# ---------------------------------------------------------------------------
# Warehouse
# ---------------------------------------------------------------------------

class WarehouseView(APIView):
    """GET → list paginado   POST → crear   (un solo endpoint, backward compatible)"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("inventory.warehouse.create")()]
        return [rbac_permission("inventory.warehouse.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)

        qs = Warehouse.objects.filter(company=company, is_active=True)
        if branch:
            qs = qs.filter(branch=branch)

        wh_type = request.query_params.get("warehouse_type")
        if wh_type:
            qs = qs.filter(warehouse_type=wh_type)

        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs.order_by("name"), limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": WarehouseOut(rows, many=True).data})

    def post(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        s = WarehouseCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        wh = create_warehouse(
            request=request,
            company=company,
            branch=branch,
            actor_user=request.user,
            name=v["name"],
            code=v.get("code", "") or "",
            warehouse_type=v.get("warehouse_type", "GENERAL"),
            location_description=v.get("location_description", "") or "",
            is_default=bool(v.get("is_default", False)),
        )
        return Response(WarehouseOut(wh).data, status=status.HTTP_201_CREATED)


WarehouseListView = WarehouseView
WarehouseCreateView = WarehouseView


# ---------------------------------------------------------------------------
# InventoryItem
# ---------------------------------------------------------------------------

class ItemView(APIView):
    """GET → list paginado   POST → crear   (un solo endpoint, backward compatible)"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("inventory.item.create")()]
        return [rbac_permission("inventory.item.read")()]

    def get(self, request):
        company: OrgUnit = request.company

        qs = InventoryItem.objects.filter(company=company)

        active = request.query_params.get("is_active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() == "true")
        else:
            qs = qs.filter(is_active=True)

        category = request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)

        track_lots = request.query_params.get("track_lots")
        if track_lots is not None:
            qs = qs.filter(track_lots=track_lots.lower() == "true")

        is_controlled = request.query_params.get("is_controlled")
        if is_controlled is not None:
            qs = qs.filter(is_controlled=is_controlled.lower() == "true")

        search = request.query_params.get("search")
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(sku__icontains=search) | Q(name__icontains=search) | Q(barcode__icontains=search)
            )

        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs.order_by("sku"), limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": InventoryItemOut(rows, many=True).data})

    def post(self, request):
        company: OrgUnit = request.company

        s = ItemCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            item = create_item(
                request=request,
                company=company,
                actor_user=request.user,
                **v,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(InventoryItemOut(item).data, status=status.HTTP_201_CREATED)


ItemListView = ItemView
ItemCreateView = ItemView


# ---------------------------------------------------------------------------
# Lots
# ---------------------------------------------------------------------------

class LotListView(APIView):
    permission_classes = [rbac_permission("inventory.lot.read")]

    def get(self, request):
        company: OrgUnit = request.company

        item_id = request.query_params.get("item_id")
        if not item_id:
            return Response({"detail": "item_id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        qs = ItemLot.objects.filter(company=company, item_id=int(item_id))

        lot_status = request.query_params.get("status")
        if lot_status:
            qs = qs.filter(status=lot_status)

        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs.order_by("-created_at"), limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": ItemLotOut(rows, many=True).data})


class LotCreateView(APIView):
    permission_classes = [rbac_permission("inventory.lot.create")]

    def post(self, request):
        company: OrgUnit = request.company

        s = LotCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            lot = create_lot(
                request=request,
                company=company,
                actor_user=request.user,
                item_id=v["item_id"],
                lot_number=v["lot_number"],
                supplier_lot_ref=v.get("supplier_lot_ref", "") or "",
                production_date=v.get("production_date"),
                expiry_date=v.get("expiry_date"),
                notes=v.get("notes", "") or "",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ItemLotOut(lot).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Stock Balance
# ---------------------------------------------------------------------------

class StockSummaryView(APIView):
    permission_classes = [rbac_permission("inventory.balance.read")]

    def get(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)

        qs = StockBalance.objects.filter(company=company).select_related("item", "warehouse")

        if branch:
            qs = qs.filter(branch=branch)

        warehouse_id = request.query_params.get("warehouse_id")
        if warehouse_id:
            qs = qs.filter(warehouse_id=int(warehouse_id))

        item_id = request.query_params.get("item_id")
        if item_id:
            qs = qs.filter(item_id=int(item_id))

        category = request.query_params.get("category")
        if category:
            qs = qs.filter(item__category__iexact=category)

        below_reorder = request.query_params.get("below_reorder")
        if below_reorder and below_reorder.lower() == "true":
            from django.db.models import F
            qs = qs.filter(qty_on_hand__lt=F("item__reorder_point"))

        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs.order_by("item__sku"), limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": StockBalanceOut(rows, many=True).data})


class LotStockView(APIView):
    permission_classes = [rbac_permission("inventory.balance.read")]

    def get(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)

        item_id = request.query_params.get("item_id")
        if not item_id:
            return Response({"detail": "item_id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        qs = LotBalance.objects.filter(company=company, item_id=int(item_id)).select_related("lot")
        if branch:
            qs = qs.filter(branch=branch)

        warehouse_id = request.query_params.get("warehouse_id")
        if warehouse_id:
            qs = qs.filter(warehouse_id=int(warehouse_id))

        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs.order_by("lot__expiry_date"), limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": LotBalanceOut(rows, many=True).data})


# ---------------------------------------------------------------------------
# Kardex / Movements
# ---------------------------------------------------------------------------

class KardexView(APIView):
    permission_classes = [rbac_permission("inventory.movement.read")]

    def get(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)

        item_id = request.query_params.get("item_id")
        if not item_id:
            return Response({"detail": "item_id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        qs = StockMovement.objects.filter(company=company, item_id=int(item_id)).select_related("item", "warehouse", "lot")
        if branch:
            qs = qs.filter(branch=branch)

        warehouse_id = request.query_params.get("warehouse_id")
        if warehouse_id:
            qs = qs.filter(warehouse_id=int(warehouse_id))

        movement_type = request.query_params.get("movement_type")
        if movement_type:
            qs = qs.filter(movement_type=movement_type)

        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs.order_by("-created_at"), limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": StockMovementOut(rows, many=True).data})


# ---------------------------------------------------------------------------
# BalanceView — backward compat (respuesta flat por warehouse+item)
# ---------------------------------------------------------------------------

class BalanceView(APIView):
    permission_classes = [rbac_permission("inventory.balance.read")]

    def get(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        warehouse_id = request.query_params.get("warehouse_id")
        item_id = request.query_params.get("item_id")
        if not warehouse_id or not item_id:
            return Response({"detail": "warehouse_id and item_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        bal = StockBalance.objects.filter(
            company=company, branch=branch,
            warehouse_id=int(warehouse_id), item_id=int(item_id)
        ).first()
        if not bal:
            return Response({"qty_on_hand": "0.0000", "avg_cost": "0.000000"})
        return Response({"qty_on_hand": str(bal.qty_on_hand), "avg_cost": str(bal.avg_cost)})


# ---------------------------------------------------------------------------
# Movement commands (write)
# ---------------------------------------------------------------------------

class ReceiveView(APIView):
    permission_classes = [rbac_permission("inventory.movement.receive")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = MovementReceiveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            r = post_receive(
                request=request,
                actor=request.user,
                warehouse_id=v["warehouse_id"],
                item_id=v["item_id"],
                qty=v["qty"],
                unit_cost=v["unit_cost"],
                lot_id=v.get("lot_id"),
                lot_number=v.get("lot_number", "") or "",
                expiry_date=v.get("expiry_date"),
                movement_uom=v.get("movement_uom", "") or "",
                movement_uom_factor=v.get("movement_uom_factor", "1.000000"),
                idempotency_key=v.get("idempotency_key", "") or "",
                note=v.get("note", "") or "",
                source_module=v.get("source_module", "") or "",
                source_type=v.get("source_type", "") or "",
                source_id=v.get("source_id", "") or "",
            )
        except InventoryConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_movement_post_response(r), status=status.HTTP_201_CREATED)


class IssueView(APIView):
    permission_classes = [rbac_permission("inventory.movement.issue")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = MovementIssueSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            r = post_issue(
                request=request,
                actor=request.user,
                warehouse_id=v["warehouse_id"],
                item_id=v["item_id"],
                qty=v["qty"],
                lot_id=v.get("lot_id"),
                movement_uom=v.get("movement_uom", "") or "",
                movement_uom_factor=v.get("movement_uom_factor", "1.000000"),
                allow_negative=bool(v.get("allow_negative", False)),
                idempotency_key=v.get("idempotency_key", "") or "",
                note=v.get("note", "") or "",
                source_module=v.get("source_module", "") or "",
                source_type=v.get("source_type", "") or "",
                source_id=v.get("source_id", "") or "",
            )
        except InventoryConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_movement_post_response(r), status=status.HTTP_201_CREATED)


class AdjustView(APIView):
    permission_classes = [rbac_permission("inventory.movement.adjust")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = MovementAdjustSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            r = post_adjust(
                request=request,
                actor=request.user,
                warehouse_id=v["warehouse_id"],
                item_id=v["item_id"],
                new_qty_on_hand=v["new_qty_on_hand"],
                idempotency_key=v.get("idempotency_key", "") or "",
                note=v.get("note", "") or "",
            )
        except InventoryConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_movement_post_response(r), status=status.HTTP_201_CREATED)


class TransferView(APIView):
    permission_classes = [rbac_permission("inventory.transfer.create")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = TransferSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            out = post_transfer(
                request=request,
                actor=request.user,
                from_warehouse_id=v["from_warehouse_id"],
                to_warehouse_id=v["to_warehouse_id"],
                item_id=v["item_id"],
                qty=v["qty"],
                lot_id=v.get("lot_id"),
                idempotency_key=v.get("idempotency_key", "") or "",
                note=v.get("note", "") or "",
            )
        except InventoryConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_201_CREATED)
