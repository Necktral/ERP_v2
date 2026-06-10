from __future__ import annotations

from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit

from .models import ScannedDocument
from .serializers import (
    ScannedDocumentReviewSerializer,
    ScannedDocumentSerializer,
    ScannedDocumentUploadSerializer,
)
from .services import create_scanned_document, review_document

_COMPANY_REQUIRED = Response(
    {"detail": "X-Company-Id requerido"}, status=status.HTTP_400_BAD_REQUEST
)


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request):
        return Response({"ok": True, "module": "documents"}, status=status.HTTP_200_OK)


class ScannedDocumentUploadView(APIView):
    permission_classes = [rbac_permission("documents.scan.create")]

    def post(self, request):
        company = getattr(request, "company", None)
        if company is None:
            return _COMPANY_REQUIRED
        s = ScannedDocumentUploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        branch = None
        branch_id = v.get("branch_id")
        if branch_id:
            branch = OrgUnit.objects.filter(
                id=branch_id, unit_type=OrgUnit.UnitType.BRANCH
            ).first()
        doc = create_scanned_document(
            company=company,
            branch=branch,
            doc_type=v["doc_type"],
            raw_bytes=v["image_base64"],
            content_type=v.get("content_type", ""),
            uploaded_by=request.user,
        )
        return Response(ScannedDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class ScannedDocumentListView(APIView):
    permission_classes = [rbac_permission("documents.scan.read")]

    def get(self, request):
        company = getattr(request, "company", None)
        if company is None:
            return _COMPANY_REQUIRED
        qs = ScannedDocument.objects.filter(company=company)
        status_f = request.query_params.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        doc_type_f = request.query_params.get("doc_type")
        if doc_type_f:
            qs = qs.filter(doc_type=doc_type_f)
        data = ScannedDocumentSerializer(qs[:200], many=True).data
        return Response({"results": data}, status=status.HTTP_200_OK)


class ScannedDocumentDetailView(APIView):
    permission_classes = [rbac_permission("documents.scan.read")]

    def get(self, request, pk: int):
        company = getattr(request, "company", None)
        if company is None:
            return _COMPANY_REQUIRED
        doc = get_object_or_404(ScannedDocument, pk=pk, company=company)
        return Response(ScannedDocumentSerializer(doc).data, status=status.HTTP_200_OK)


class ScannedDocumentReviewView(APIView):
    permission_classes = [rbac_permission("documents.scan.review")]

    def post(self, request, pk: int):
        company = getattr(request, "company", None)
        if company is None:
            return _COMPANY_REQUIRED
        doc = get_object_or_404(ScannedDocument, pk=pk, company=company)
        s = ScannedDocumentReviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        doc = review_document(
            doc=doc,
            reviewed_by=request.user,
            extracted_fields=v.get("extracted_fields"),
            doc_type=v.get("doc_type"),
        )
        return Response(ScannedDocumentSerializer(doc).data, status=status.HTTP_200_OK)
