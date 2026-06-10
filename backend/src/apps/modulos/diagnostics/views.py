from __future__ import annotations

from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission

from .models import AIControl, ErrorEvent, SecurityFinding
from .serializers import (
    AIControlSerializer,
    AIControlUpdateSerializer,
    ErrorEventDetailSerializer,
    ErrorEventSerializer,
    SecurityFindingSerializer,
)


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


class SecurityFindingListView(APIView):
    permission_classes = [rbac_permission("diagnostics.finding.read")]

    def get(self, request):
        qs = SecurityFinding.objects.all()
        for f in ("source_tool", "risk_class", "status"):
            val = request.query_params.get(f)
            if val:
                qs = qs.filter(**{f: val})
        data = SecurityFindingSerializer(qs[:300], many=True).data
        return Response({"results": data}, status=status.HTTP_200_OK)


class SecurityFindingDetailView(APIView):
    permission_classes = [rbac_permission("diagnostics.finding.read")]

    def get(self, request, finding_id):
        obj = get_object_or_404(SecurityFinding, finding_id=finding_id)
        return Response(SecurityFindingSerializer(obj).data, status=status.HTTP_200_OK)


class AIControlView(APIView):
    """Botón de apagado de la IA. GET lee el estado; POST enciende/apaga (en caliente)."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("diagnostics.ai_control.manage")()]
        return [rbac_permission("diagnostics.ai_control.read")()]

    def get(self, request):
        return Response(AIControlSerializer(AIControl.current()).data, status=status.HTTP_200_OK)

    def post(self, request):
        s = AIControlUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        ctrl = AIControl.current()
        ctrl.ai_enabled = bool(v["enabled"])
        ctrl.reason = v.get("reason", "")
        ctrl.updated_by = request.user if request.user.is_authenticated else None
        ctrl.save()
        return Response(AIControlSerializer(ctrl).data, status=status.HTTP_200_OK)
