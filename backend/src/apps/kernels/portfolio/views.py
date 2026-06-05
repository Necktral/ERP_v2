"""
Portfolio Kernel Views
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.modulos.common.permissions import rbac_permission

from .models import (
    Receivable,
    Payable,
    Credit,
    PaymentAllocation,
    InterestAccrual,
    PortfolioSettings,
)
from .serializers import (
    ReceivableSerializer,
    PayableSerializer,
    CreditSerializer,
    PaymentAllocationSerializer,
    InterestAccrualSerializer,
    PortfolioSettingsSerializer,
)
from . import services


_READ_ACTIONS = frozenset({"list", "retrieve"})


def _rbac_perms(view, *, read: str, write: str, extra=None):
    """Mapea la acción DRF del `view` a su permiso RBAC y devuelve la lista de permisos.

    Cierra el hueco rbac=0 en portfolio: las operaciones sensibles (adjust/writeoff/
    disburse de CxC/CxP/crédito) exigen permiso propio, no solo autenticación.
    """
    extra_map = extra or {}
    action = getattr(view, "action", None)
    if action in extra_map:
        perm = extra_map[action]
    elif action in _READ_ACTIONS:
        perm = read
    else:
        perm = write
    return [rbac_permission(perm)()]


class ReceivableViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Receivables (CxC)
    """
    serializer_class = ReceivableSerializer

    def get_permissions(self):
        return _rbac_perms(
            self, read="portfolio.receivable.read", write="portfolio.receivable.write",
            extra={"adjust": "portfolio.receivable.adjust", "writeoff": "portfolio.receivable.writeoff"},
        )

    filterset_fields = ["status", "party", "aging_bucket", "currency"]
    search_fields = ["invoice_number", "party__name"]
    ordering_fields = ["issue_date", "due_date", "outstanding_amount"]
    ordering = ["-issue_date"]

    def get_queryset(self):
        return Receivable.objects.filter(company=self.request.company).select_related("party", "company", "branch")

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        """Adjust receivable amount"""
        receivable = self.get_object()
        adjustment_amount = request.data.get("adjustment_amount")
        reason = request.data.get("reason", "")

        try:
            adjusted = services.adjust_receivable(
                receivable=receivable,
                adjustment_amount=adjustment_amount,
                reason=reason,
                adjusted_by=request.user,
            )
            return Response(self.get_serializer(adjusted).data)
        except services.PortfolioDomainError as e:
            return Response(
                {"error": e.code, "message": e.message, "details": e.details},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=["post"])
    def writeoff(self, request, pk=None):
        """Write off receivable"""
        receivable = self.get_object()
        reason = request.data.get("reason", "")

        try:
            written_off = services.write_off_receivable(
                receivable=receivable,
                reason=reason,
                approved_by=request.user,
            )
            return Response(self.get_serializer(written_off).data)
        except services.PortfolioDomainError as e:
            return Response(
                {"error": e.code, "message": e.message},
                status=status.HTTP_400_BAD_REQUEST
            )


class PayableViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Payables (CxP)
    """
    serializer_class = PayableSerializer

    def get_permissions(self):
        return _rbac_perms(self, read="portfolio.payable.read", write="portfolio.payable.write")

    filterset_fields = ["status", "party", "payment_priority", "currency"]
    search_fields = ["supplier_invoice_number", "party__name"]
    ordering_fields = ["issue_date", "due_date", "outstanding_amount"]
    ordering = ["-issue_date"]

    def get_queryset(self):
        return Payable.objects.filter(company=self.request.company).select_related("party", "company", "branch")


class CreditViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Credits
    """
    serializer_class = CreditSerializer

    def get_permissions(self):
        return _rbac_perms(
            self, read="portfolio.credit.read", write="portfolio.credit.write",
            extra={"disburse": "portfolio.credit.disburse"},
        )

    filterset_fields = ["credit_status", "credit_type", "borrower_party", "lender_party"]
    search_fields = ["contract_number", "borrower_party__name", "lender_party__name"]
    ordering_fields = ["approval_date", "disbursement_date", "maturity_date"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return Credit.objects.filter(company=self.request.company).select_related(
            "lender_party", "borrower_party", "guarantor_party", "company", "branch"
        )

    @action(detail=True, methods=["post"])
    def disburse(self, request, pk=None):
        """Disburse credit"""
        credit = self.get_object()
        disbursed_amount = request.data.get("disbursed_amount")
        disbursement_date = request.data.get("disbursement_date")

        try:
            disbursed = services.disburse_credit(
                credit=credit,
                disbursed_amount=disbursed_amount,
                disbursement_date=disbursement_date,
                disbursed_by=request.user,
            )
            return Response(self.get_serializer(disbursed).data)
        except services.PortfolioDomainError as e:
            return Response(
                {"error": e.code, "message": e.message},
                status=status.HTTP_400_BAD_REQUEST
            )


class PaymentAllocationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Payment Allocations
    """
    serializer_class = PaymentAllocationSerializer

    def get_permissions(self):
        return _rbac_perms(self, read="portfolio.allocation.read", write="portfolio.allocation.write")

    filterset_fields = ["status", "payment_intent", "allocation_date"]
    ordering = ["-allocation_date", "-created_at"]

    def get_queryset(self):
        return PaymentAllocation.objects.filter(company=self.request.company).select_related("payment_intent", "company")


class InterestAccrualViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Interest Accruals (read-only)
    """
    serializer_class = InterestAccrualSerializer

    def get_permissions(self):
        return _rbac_perms(self, read="portfolio.interest.read", write="portfolio.interest.read")

    filterset_fields = ["credit", "accrual_date", "is_capitalized"]
    ordering = ["-accrual_date"]

    def get_queryset(self):
        # Filter by credit's company
        return InterestAccrual.objects.filter(
            credit__company=self.request.company
        ).select_related("credit")


class PortfolioSettingsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Portfolio Settings (per company)
    """
    serializer_class = PortfolioSettingsSerializer

    def get_permissions(self):
        return _rbac_perms(self, read="portfolio.settings.read", write="portfolio.settings.write")


    def get_queryset(self):
        return PortfolioSettings.objects.filter(company=self.request.company)
