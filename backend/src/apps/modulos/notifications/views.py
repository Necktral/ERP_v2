from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission

from .serializers import DeviceTokenSerializer
from .services import register_device_token


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "notifications"}, status=status.HTTP_200_OK)


class DeviceTokenView(APIView):
    permission_classes = [rbac_permission("notifications.device.register")]

    def post(self, request):
        company = getattr(request, "company", None)
        if company is None:
            return Response({"detail": "X-Company-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = DeviceTokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        tok = register_device_token(
            user=request.user, company=company, platform=v["platform"], token=v["token"]
        )
        return Response(
            {"id": tok.id, "platform": tok.platform, "is_active": tok.is_active},
            status=status.HTTP_200_OK,
        )
