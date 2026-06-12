"""API del módulo financiamiento. Todo requiere empresa activa (X-Company-Id) y
permiso ``financing.*``; los errores de negocio del vertical responden 422 con
``error.code`` estable (patrón del módulo ventas)."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.kernels.inventarios.models import InventoryItem, Warehouse
from apps.kernels.payments.services import PaymentsDomainError
from apps.kernels.portfolio.services import PortfolioDomainError
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.parties.models import Party

from . import services
from .models import (
    CoffeeQualityGrade,
    CoffeeReception,
    CreditApplication,
    ExchangeRate,
    FinancingLoan,
    Liquidation,
    PriceFixation,
    ProducerProfile,
)
from .serializers import (
    ApplicationCreateSerializer,
    ApplicationSerializer,
    DisburseSerializer,
    ExchangeRateSerializer,
    FixationCreateSerializer,
    FixationSerializer,
    LiquidationCreateSerializer,
    LiquidationSerializer,
    LoanPaymentSerializer,
    LoanSerializer,
    ProducerCreateSerializer,
    ProducerSerializer,
    QualityCreateSerializer,
    QualityGradeSerializer,
    RateUpsertSerializer,
    ReceptionCreateSerializer,
    ReceptionSerializer,
    RejectSerializer,
    SettingsUpdateSerializer,
)
from .services import FinancingError


def _company_or_400(request):
    company = getattr(request, "company", None)
    if company is None:
        return None, Response(
            {"detail": "X-Company-Id requerido"}, status=status.HTTP_400_BAD_REQUEST
        )
    return company, None


def _business_error(exc: FinancingError) -> Response:
    return Response(
        {"error": {"code": exc.code, "message": exc.message}},
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


def _kernel_error(exc: Exception) -> Response:
    return Response(
        {"error": {"code": getattr(exc, "args", ["KERNEL_ERROR"])[0], "message": str(exc)}},
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "financiamiento"})


class ProducerListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("financing.producer.write")()]
        return [rbac_permission("financing.producer.read")()]

    def get(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        qs = ProducerProfile.objects.filter(company=company).select_related("party").order_by("acopio_code")
        return Response({"results": ProducerSerializer(qs[:500], many=True).data})

    def post(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        s = ProducerCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        party = get_object_or_404(Party, pk=s.validated_data["party_id"], company=company)
        try:
            producer = services.create_producer(
                company=company, party=party,
                acopio_code=s.validated_data["acopio_code"],
                certifications=s.validated_data["certifications"],
                notes=s.validated_data["notes"], actor=request.user,
            )
        except FinancingError as exc:
            return _business_error(exc)
        return Response(ProducerSerializer(producer).data, status=status.HTTP_201_CREATED)


class ProducerDepositView(APIView):
    permission_classes = [rbac_permission("financing.reception.read")]

    def get(self, request, producer_id: int):
        company, err = _company_or_400(request)
        if err:
            return err
        producer = get_object_or_404(ProducerProfile, pk=producer_id, company=company)
        return Response(services.producer_deposit_balance(producer=producer))


class ExchangeRateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("financing.rate.manage")()]
        return [rbac_permission("financing.loan.read")()]

    def get(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        qs = ExchangeRate.objects.filter(company=company).order_by("-rate_date")[:60]
        return Response({"results": ExchangeRateSerializer(qs, many=True).data})

    def post(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        s = RateUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            row = services.set_exchange_rate(
                company=company, rate_date=s.validated_data["rate_date"],
                rate=s.validated_data["rate"], actor=request.user,
            )
        except FinancingError as exc:
            return _business_error(exc)
        return Response(ExchangeRateSerializer(row).data, status=status.HTTP_201_CREATED)


class QualityListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("financing.settings.manage")()]
        return [rbac_permission("financing.reception.read")()]

    def get(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        qs = CoffeeQualityGrade.objects.filter(company=company, is_active=True).order_by("code")
        return Response({"results": QualityGradeSerializer(qs, many=True).data})

    def post(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        s = QualityCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        grade = services.create_quality_grade(company=company, **s.validated_data)
        return Response(QualityGradeSerializer(grade).data, status=status.HTTP_201_CREATED)


class ApplicationListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("financing.application.create")()]
        return [rbac_permission("financing.application.read")()]

    def get(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        qs = CreditApplication.objects.filter(company=company).select_related("producer__party")
        status_f = request.query_params.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return Response({"results": ApplicationSerializer(qs.order_by("-id")[:300], many=True).data})

    def post(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        s = ApplicationCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        producer = get_object_or_404(ProducerProfile, pk=data.pop("producer_id"), company=company)
        try:
            app = services.create_application(
                company=company, producer=producer, actor=request.user, **data
            )
        except FinancingError as exc:
            return _business_error(exc)
        return Response(ApplicationSerializer(app).data, status=status.HTTP_201_CREATED)


def _get_application(request, application_id: int) -> CreditApplication:
    return get_object_or_404(CreditApplication, pk=application_id, company=request.company)


class ApplicationSubmitView(APIView):
    permission_classes = [rbac_permission("financing.application.create")]

    def post(self, request, application_id: int):
        company, err = _company_or_400(request)
        if err:
            return err
        try:
            app = services.submit_application(application=_get_application(request, application_id))
        except FinancingError as exc:
            return _business_error(exc)
        return Response(ApplicationSerializer(app).data)


class ApplicationApproveView(APIView):
    permission_classes = [rbac_permission("financing.application.approve")]

    def post(self, request, application_id: int):
        company, err = _company_or_400(request)
        if err:
            return err
        try:
            app = services.approve_application(
                application=_get_application(request, application_id), actor=request.user, request=request,
            )
        except FinancingError as exc:
            return _business_error(exc)
        return Response(ApplicationSerializer(app).data)


class ApplicationRejectView(APIView):
    permission_classes = [rbac_permission("financing.application.approve")]

    def post(self, request, application_id: int):
        company, err = _company_or_400(request)
        if err:
            return err
        s = RejectSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            app = services.reject_application(
                application=_get_application(request, application_id), actor=request.user,
                reason=s.validated_data["reason"],
            )
        except FinancingError as exc:
            return _business_error(exc)
        return Response(ApplicationSerializer(app).data)


class ApplicationDisburseView(APIView):
    permission_classes = [rbac_permission("financing.application.disburse")]

    def post(self, request, application_id: int):
        company, err = _company_or_400(request)
        if err:
            return err
        if getattr(request, "branch", None) is None:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = DisburseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            loan = services.disburse_loan(
                request=request, actor=request.user,
                application=_get_application(request, application_id),
                disbursement_date=s.validated_data.get("disbursement_date"),
                reference=s.validated_data["reference"],
            )
        except FinancingError as exc:
            return _business_error(exc)
        except PortfolioDomainError as exc:
            return _kernel_error(exc)
        return Response(LoanSerializer(loan).data, status=status.HTTP_201_CREATED)


class LoanListView(APIView):
    permission_classes = [rbac_permission("financing.loan.read")]

    def get(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        qs = FinancingLoan.objects.filter(company=company).select_related("producer__party")
        status_f = request.query_params.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return Response({"results": LoanSerializer(qs.order_by("-id")[:300], many=True).data})


class LoanStatementView(APIView):
    permission_classes = [rbac_permission("financing.loan.read")]

    def get(self, request, loan_id: int):
        company, err = _company_or_400(request)
        if err:
            return err
        loan = get_object_or_404(
            FinancingLoan.objects.select_related("credit_nio", "credit_usd", "producer__party"),
            pk=loan_id, company=company,
        )
        return Response(services.loan_statement(loan=loan))


class LoanPaymentView(APIView):
    permission_classes = [rbac_permission("financing.payment.register")]

    def post(self, request, loan_id: int):
        company, err = _company_or_400(request)
        if err:
            return err
        if getattr(request, "branch", None) is None:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = LoanPaymentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        loan = get_object_or_404(
            FinancingLoan.objects.select_related("credit_nio", "credit_usd"),
            pk=loan_id, company=company,
        )
        try:
            result = services.register_loan_payment(
                request=request, actor=request.user, loan=loan, **s.validated_data
            )
        except FinancingError as exc:
            return _business_error(exc)
        except (PortfolioDomainError, PaymentsDomainError) as exc:
            return _kernel_error(exc)
        return Response(result, status=status.HTTP_201_CREATED)


class ReceptionListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("financing.reception.create")()]
        return [rbac_permission("financing.reception.read")()]

    def get(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        qs = CoffeeReception.objects.filter(company=company).select_related("producer__party", "quality")
        producer_f = request.query_params.get("producer")
        if producer_f:
            qs = qs.filter(producer_id=producer_f)
        return Response({"results": ReceptionSerializer(qs.order_by("-id")[:300], many=True).data})

    def post(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        if getattr(request, "branch", None) is None:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = ReceptionCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        producer = get_object_or_404(ProducerProfile, pk=data.pop("producer_id"), company=company)
        quality = get_object_or_404(CoffeeQualityGrade, pk=data.pop("quality_id"), company=company)
        try:
            reception = services.receive_coffee(
                request=request, actor=request.user, producer=producer, quality=quality, **data
            )
        except FinancingError as exc:
            return _business_error(exc)
        except ValueError as exc:
            return _kernel_error(exc)
        return Response(ReceptionSerializer(reception).data, status=status.HTTP_201_CREATED)


class FixationListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("financing.fixation.create")()]
        return [rbac_permission("financing.reception.read")()]

    def get(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        qs = PriceFixation.objects.filter(company=company)
        producer_f = request.query_params.get("producer")
        if producer_f:
            qs = qs.filter(producer_id=producer_f)
        status_f = request.query_params.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return Response({"results": FixationSerializer(qs.order_by("-id")[:300], many=True).data})

    def post(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        s = FixationCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        producer = get_object_or_404(ProducerProfile, pk=data.pop("producer_id"), company=company)
        try:
            fixation = services.fix_price(
                company=company, producer=producer, actor=request.user, **data
            )
        except FinancingError as exc:
            return _business_error(exc)
        return Response(FixationSerializer(fixation).data, status=status.HTTP_201_CREATED)


class LiquidationListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("financing.liquidation.create")()]
        return [rbac_permission("financing.liquidation.read")()]

    def get(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        qs = Liquidation.objects.filter(company=company).select_related("producer__party", "loan")
        producer_f = request.query_params.get("producer")
        if producer_f:
            qs = qs.filter(producer_id=producer_f)
        return Response({"results": LiquidationSerializer(qs.order_by("-id")[:300], many=True).data})

    def post(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        if getattr(request, "branch", None) is None:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = LiquidationCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        producer = get_object_or_404(ProducerProfile, pk=data.pop("producer_id"), company=company)
        loan = None
        loan_id = data.pop("loan_id", None)
        if loan_id:
            loan = get_object_or_404(
                FinancingLoan.objects.select_related("credit_nio", "credit_usd"),
                pk=loan_id, company=company,
            )
        deductions = [dict(d) for d in data.pop("deductions", [])]
        try:
            liq = services.liquidate(
                request=request, actor=request.user, producer=producer,
                loan=loan, deductions=deductions, **data
            )
        except FinancingError as exc:
            return _business_error(exc)
        except (PortfolioDomainError, PaymentsDomainError, ValueError) as exc:
            return _kernel_error(exc)
        return Response(LiquidationSerializer(liq).data, status=status.HTTP_201_CREATED)


class SettingsView(APIView):
    permission_classes = [rbac_permission("financing.settings.manage")]

    def get(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        row = services.get_or_create_settings(company=company)
        return Response({
            "coffee_item_id": row.coffee_item_id,
            "custody_warehouse_id": row.custody_warehouse_id,
            "liquidation_warehouse_id": row.liquidation_warehouse_id,
            "lender_party_id": row.lender_party_id,
        })

    def post(self, request):
        company, err = _company_or_400(request)
        if err:
            return err
        s = SettingsUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        row = services.get_or_create_settings(company=company)
        v = s.validated_data
        if v.get("coffee_item_id") is not None:
            row.coffee_item = get_object_or_404(InventoryItem, pk=v["coffee_item_id"], company=company)
        if v.get("custody_warehouse_id") is not None:
            row.custody_warehouse = get_object_or_404(Warehouse, pk=v["custody_warehouse_id"], company=company)
        if v.get("liquidation_warehouse_id") is not None:
            row.liquidation_warehouse = get_object_or_404(Warehouse, pk=v["liquidation_warehouse_id"], company=company)
        row.save()
        return Response({"ok": True})
