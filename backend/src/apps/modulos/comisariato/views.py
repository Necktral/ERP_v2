from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.kernels.nomina.models import PayrollSheet
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit
from apps.modulos.parties.models import Party

from .models import CustomerCreditAccount
from .payroll_link import apply_store_credit_deductions
from .serializers import AccountUpsertSerializer, ApplyStoreCreditSerializer, SaleSerializer
from .services import (
    ComisariatoError,
    available_credit,
    get_or_create_account,
    outstanding_balance,
    sell_on_credit,
)


def _account_payload(account: CustomerCreditAccount) -> dict:
    avail = available_credit(account)
    return {
        "id": account.id,
        "company_id": account.company_id,
        "party_id": account.party_id,
        "party_display_name": account.party.display_name,
        "segment": account.segment,
        "credit_limit": str(account.credit_limit),
        "outstanding": str(outstanding_balance(company=account.company, party=account.party)),
        "available": str(avail) if avail is not None else None,
        "collecting_company_id": account.collecting_company_id,
        "is_active": account.is_active,
        "notes": account.notes,
    }


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "comisariato"}, status=status.HTTP_200_OK)


class AccountUpsertView(APIView):
    permission_classes = [rbac_permission("comisariato.account.manage")]

    def post(self, request):
        company = getattr(request, "company", None)
        if company is None:
            return Response({"detail": "X-Company-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = AccountUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        party = Party.objects.filter(id=v["party_id"], company=company).first()
        if party is None:
            return Response({"detail": "party no existe en esta empresa"}, status=status.HTTP_400_BAD_REQUEST)
        collecting = None
        if v.get("collecting_company_id"):
            collecting = OrgUnit.objects.filter(
                id=v["collecting_company_id"], unit_type=OrgUnit.UnitType.COMPANY
            ).first()
            if collecting is None:
                return Response({"detail": "collecting_company inválida"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            account = get_or_create_account(
                request=request, actor=request.user, company=company, party=party,
                segment=v["segment"], credit_limit=v["credit_limit"], collecting_company=collecting,
                is_active=v["is_active"], notes=v.get("notes") or "",
            )
        except ComisariatoError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_account_payload(account), status=status.HTTP_200_OK)


class AccountDetailView(APIView):
    permission_classes = [rbac_permission("comisariato.read")]

    def get(self, request, account_id: int):
        company = getattr(request, "company", None)
        account = CustomerCreditAccount.objects.filter(id=account_id, company=company).first()
        if account is None:
            return Response({"detail": "cuenta no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_account_payload(account), status=status.HTTP_200_OK)


class SaleView(APIView):
    permission_classes = [rbac_permission("comisariato.sell")]

    def post(self, request):
        company = getattr(request, "company", None)
        if company is None or getattr(request, "branch", None) is None:
            return Response(
                {"detail": "X-Company-Id y X-Branch-Id requeridos"}, status=status.HTTP_400_BAD_REQUEST
            )
        s = SaleSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        account = CustomerCreditAccount.objects.filter(id=v["account_id"], company=company).first()
        if account is None:
            return Response({"detail": "cuenta no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = sell_on_credit(
                request=request, actor=request.user, account=account,
                warehouse_id=v["warehouse_id"], lines=v["lines"], reference_code=v["reference_code"],
                currency=v.get("currency") or "NIO", is_fiscal=v["is_fiscal"],
            )
        except ComisariatoError as exc:
            code = str(exc)
            http = status.HTTP_422_UNPROCESSABLE_ENTITY if code == "COMISARIATO_CREDIT_LIMIT_EXCEEDED" else status.HTTP_400_BAD_REQUEST
            return Response({"detail": code}, status=http)
        return Response(result, status=status.HTTP_201_CREATED)


class ApplyStoreCreditView(APIView):
    permission_classes = [rbac_permission("comisariato.payroll.apply")]

    def post(self, request, sheet_id: int):
        s = ApplyStoreCreditSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        sheet = PayrollSheet.objects.filter(id=sheet_id).first()
        if sheet is None:
            return Response({"detail": "planilla no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        comisariato_company = OrgUnit.objects.filter(
            id=v["comisariato_company_id"], unit_type=OrgUnit.UnitType.COMPANY
        ).first()
        if comisariato_company is None:
            return Response({"detail": "comisariato_company inválida"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = apply_store_credit_deductions(
                request=request, actor=request.user, sheet=sheet,
                comisariato_company=comisariato_company, per_period_cap=v.get("per_period_cap"),
            )
        except ComisariatoError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)
