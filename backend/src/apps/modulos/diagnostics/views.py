from __future__ import annotations

from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission

from .models import ErrorEvent
from .serializers import ErrorEventDetailSerializer, ErrorEventSerializer


class ErrorEventListView(APIView):
    permission_classes = [rbac_permission("diagnostics.error.read")]

    def get(self, request):
        qs = ErrorEvent.objects.all()
        domain_f = request.query_params.get("domain")
        if domain_f:
            qs = qs.filter(domain=domain_f)
        risk_f = request.query_params.get("risk_class")
        if risk_f:
            qs = qs.filter(risk_class=risk_f)
        status_f = request.query_params.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        data = ErrorEventSerializer(qs[:200], many=True).data
        return Response({"results": data}, status=status.HTTP_200_OK)


class ErrorEventDetailView(APIView):
    permission_classes = [rbac_permission("diagnostics.error.read")]

    def get(self, request, error_id):
        obj = get_object_or_404(ErrorEvent, error_id=error_id)
        return Response(ErrorEventDetailSerializer(obj).data, status=status.HTTP_200_OK)
