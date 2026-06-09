from __future__ import annotations

from datetime import date

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission

from .services import group_cartera_position, record_intercompany_charge


class IntercompanyChargeView(APIView):
    """Registra una operación intercompany (A cobra/suministra a B) con todas sus patas."""

    permission_classes = [rbac_permission("accounting.intercompany.write")]
    throttle_scope = "admin_writes"

    def post(self, request):
        d = request.data
        for key in ("source_company_id", "target_company_id", "amount", "reference_code"):
            if d.get(key) in (None, ""):
                return Response({key: "Requerido"}, status=status.HTTP_400_BAD_REQUEST)
        eff = d.get("effective_date")
        try:
            effective_date = date.fromisoformat(eff) if eff else None
        except (TypeError, ValueError):
            return Response({"effective_date": "Fecha inválida (ISO)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = record_intercompany_charge(
                source_company_id=int(d["source_company_id"]),
                target_company_id=int(d["target_company_id"]),
                amount=d["amount"],
                reference_code=str(d["reference_code"]),
                concept=str(d.get("concept", "")),
                effective_date=effective_date,
                currency=str(d.get("currency", "NIO")),
                actor=request.user,
            )
        except ValueError as exc:
            code = str(exc)
            http = status.HTTP_403_FORBIDDEN if code == "INTERCOMPANY_NOT_AUTHORIZED" else status.HTTP_400_BAD_REQUEST
            return Response({"detail": code}, status=http)
        return Response(result, status=status.HTTP_201_CREATED)


class GroupCarteraView(APIView):
    """Posición de cartera del grupo por empresa, separando intercompany."""

    permission_classes = [rbac_permission("audit.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        raw = request.query_params.get("company_ids", "")
        try:
            company_ids = [int(x) for x in raw.split(",") if x.strip()]
        except ValueError:
            return Response({"company_ids": "Lista de IDs inválida."}, status=status.HTTP_400_BAD_REQUEST)
        if not company_ids:
            return Response({"company_ids": "Requerido (csv de company ids)."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(group_cartera_position(company_ids=company_ids), status=status.HTTP_200_OK)
