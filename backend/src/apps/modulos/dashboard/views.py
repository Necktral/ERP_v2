from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission

from .serializers import EmbedTokenIn, RedeemEmbedTokenIn
from .services import (
    DashboardAuthError,
    DashboardConflictError,
    DashboardPermissionDenied,
    DashboardValidationError,
    create_embed_token_for_request,
    list_workspaces_for_request,
    redeem_embed_token,
)


class WorkspaceListView(APIView):
    permission_classes = [rbac_permission("report.dashboard.read")]

    def get(self, request):
        try:
            rows = list_workspaces_for_request(request=request)
        except DashboardValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DashboardAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"count": len(rows), "results": rows}, status=status.HTTP_200_OK)


class EmbedTokenView(APIView):
    permission_classes = [rbac_permission("report.dashboard.read")]

    def post(self, request):
        serializer = EmbedTokenIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            out = create_embed_token_for_request(
                request=request,
                workspace_key=str(payload["workspace_key"]),
                branch_id=payload.get("branch_id"),
                require_compose=bool(payload.get("require_compose", False)),
            )
        except DashboardPermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DashboardValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DashboardAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(out, status=status.HTTP_200_OK)


class EmbedTokenRedeemView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        serializer = RedeemEmbedTokenIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            out = redeem_embed_token(token_str=str(serializer.validated_data["token"]))
        except DashboardConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DashboardValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DashboardAuthError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(out, status=status.HTTP_200_OK)
