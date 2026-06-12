from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit

from .models import PurchaseDocument
from .serializers import PurchaseDocCreateSerializer, PurchaseDocVoidSerializer
from .services import (
    ProcurementError,
    ProcurementNotFoundError,
    create_purchase_draft,
    post_purchase_document,
    void_purchase_document,
)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "procurement"}, status=status.HTTP_200_OK)


class PurchaseDocCreateView(APIView):
    permission_classes = [rbac_permission("procurement.doc.create")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = PurchaseDocCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            result = create_purchase_draft(
                request=request,
                actor=request.user,
                doc_type=v["doc_type"],
                series=v.get("series") or "P",
                currency=v.get("currency") or "NIO",
                supplier_name=v.get("supplier_name") or "",
                supplier_ref=v.get("supplier_ref") or "",
                external_ref=v.get("external_ref") or "",
                supplier_party_id=v.get("supplier_party_id"),
                subtotal=v["subtotal"],
                tax_total=v.get("tax_total") or 0,
                total=v["total"],
                notes=v.get("notes") or "",
                metadata_json=v.get("metadata_json") or {},
                idempotency_key=v.get("idempotency_key") or "",
            )
        except ProcurementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"id": int(result.doc_id)}, status=status.HTTP_201_CREATED)


class PurchaseDocListView(APIView):
    """Listado paginado de documentos de compra de la sucursal activa.

    Filtros: status, doc_type, q (proveedor/referencias/número), date_from/date_to.
    """

    permission_classes = [rbac_permission("procurement.doc.read")]

    def get(self, request):
        company: OrgUnit = request.company
        qs = (
            PurchaseDocument.objects.filter(company=company)
            .select_related("supplier_party")
            .order_by("-created_at")
        )
        branch: OrgUnit | None = getattr(request, "branch", None)
        if branch:
            qs = qs.filter(branch=branch)

        status_filter = (request.query_params.get("status") or "").strip().upper()
        if status_filter:
            qs = qs.filter(status=status_filter)
        doc_type = (request.query_params.get("doc_type") or "").strip().upper()
        if doc_type:
            qs = qs.filter(doc_type=doc_type)
        q = (request.query_params.get("q") or "").strip()
        if q:
            filtro = (
                Q(supplier_name__icontains=q)
                | Q(supplier_ref__icontains=q)
                | Q(external_ref__icontains=q)
                | Q(supplier_party__display_name__icontains=q)
            )
            if q.isdigit():
                filtro |= Q(number=int(q))
            qs = qs.filter(filtro)
        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "id": int(d.id),
                "doc_type": d.doc_type,
                "status": d.status,
                "series": d.series,
                "number": int(d.number),
                "currency": d.currency,
                "supplier_name": d.supplier_name,
                "supplier_party_id": d.supplier_party_id,
                "supplier_party_display_name": d.supplier_party.display_name if d.supplier_party else "",
                "subtotal": str(d.subtotal),
                "tax_total": str(d.tax_total),
                "total": str(d.total),
                "created_at": d.created_at,
                "posted_at": d.posted_at,
                "voided_at": d.voided_at,
            }
            for d in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class PurchaseDocDetailView(APIView):
    permission_classes = [rbac_permission("procurement.doc.read")]

    def get(self, request, doc_id: int):
        company: OrgUnit = request.company
        branch: OrgUnit = request.branch
        doc = get_object_or_404(PurchaseDocument, id=doc_id, company=company, branch=branch)
        supplier_party = doc.supplier_party
        return Response(
            {
                "id": int(doc.id),
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "number": int(doc.number),
                "currency": doc.currency,
                "supplier_name": doc.supplier_name,
                "supplier_ref": doc.supplier_ref,
                "supplier_party_id": doc.supplier_party_id,
                "supplier_party_display_name": supplier_party.display_name if supplier_party is not None else "",
                "external_ref": doc.external_ref,
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "posted_at": doc.posted_at,
                "voided_at": doc.voided_at,
                "void_reason": doc.void_reason,
                "notes": doc.notes,
                "metadata_json": doc.metadata_json or {},
            },
            status=status.HTTP_200_OK,
        )


class PurchaseDocPostView(APIView):
    permission_classes = [rbac_permission("procurement.doc.post")]

    def post(self, request, doc_id: int):
        try:
            out = post_purchase_document(request=request, actor=request.user, doc_id=int(doc_id))
        except ProcurementNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ProcurementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class PurchaseDocVoidView(APIView):
    permission_classes = [rbac_permission("procurement.doc.void")]

    def post(self, request, doc_id: int):
        s = PurchaseDocVoidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            out = void_purchase_document(
                request=request,
                actor=request.user,
                doc_id=int(doc_id),
                reason=s.validated_data.get("reason") or "VOID",
            )
        except ProcurementNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ProcurementError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)


class PurchaseDocListCreateView(PurchaseDocListView, PurchaseDocCreateView):
    """GET lista (procurement.doc.read) + POST crea borrador (procurement.doc.create)."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("procurement.doc.create")()]
        return [rbac_permission("procurement.doc.read")()]
