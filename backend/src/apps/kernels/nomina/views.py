from __future__ import annotations

from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset as _paginate
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit

from .models import NominaConfig, PayrollEntry, PayrollPeriod, PayrollSheet
from .serializers import (
    IRBracketIn,
    NominaConfigOut,
    NominaConfigUpdateIn,
    PayrollEntryCreateIn,
    PayrollEntryOut,
    PayrollPeriodCreateIn,
    PayrollPeriodOut,
    PayrollSheetCreateIn,
    PayrollSheetOut,
)
from .planilla_export import render_planilla_xlsx
from .planilla_pdf import render_planilla_pdf
from .services import (
    approve_sheet,
    compute_all_entries_in_sheet,
    compute_entry,
    create_default_nicaragua_config,
    create_period,
    create_sheet,
    submit_sheet,
    update_nomina_config,
    upsert_ir_brackets,
)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "nomina"})


# ---------------------------------------------------------------------------
# NominaConfig
# ---------------------------------------------------------------------------

class NominaConfigView(APIView):
    """GET → config activa   POST → crear config Nicaragua por defecto"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.config.manage")()]
        return [rbac_permission("nomina.config.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        configs = NominaConfig.objects.filter(company=company).prefetch_related("ir_brackets").order_by("-effective_from")
        limit, offset = get_limit_offset(request)
        total, rows = _paginate(configs, limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": NominaConfigOut(rows, many=True).data})

    def post(self, request):
        company: OrgUnit = request.company
        fiscal_year = request.data.get("fiscal_year")
        cfg = create_default_nicaragua_config(
            request=request,
            actor=request.user,
            company=company,
            fiscal_year=int(fiscal_year) if fiscal_year else None,
        )
        return Response(NominaConfigOut(cfg).data, status=status.HTTP_201_CREATED)


class NominaConfigDetailView(APIView):
    """GET/PATCH una config específica"""

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [rbac_permission("nomina.config.manage")()]
        return [rbac_permission("nomina.config.read")()]

    def _get_config(self, request, config_id):
        company: OrgUnit = request.company
        return get_object_or_404(NominaConfig, id=config_id, company=company)

    def get(self, request, config_id):
        cfg = self._get_config(request, config_id)
        return Response(NominaConfigOut(cfg).data)

    def patch(self, request, config_id):
        cfg = self._get_config(request, config_id)
        s = NominaConfigUpdateIn(data=request.data)
        s.is_valid(raise_exception=True)
        updated = update_nomina_config(request=request, actor=request.user, config=cfg, data=s.validated_data)
        return Response(NominaConfigOut(updated).data)


class IRBracketView(APIView):
    """PUT → reemplaza tabla IR completa de una config"""

    permission_classes = [rbac_permission("nomina.config.manage")]

    def put(self, request, config_id):
        company: OrgUnit = request.company
        cfg = get_object_or_404(NominaConfig, id=config_id, company=company)
        s = IRBracketIn(data=request.data.get("brackets", []), many=True)
        s.is_valid(raise_exception=True)
        brackets = upsert_ir_brackets(request=request, actor=request.user, config=cfg, brackets=s.validated_data)
        from .serializers import IRBracketOut
        return Response(IRBracketOut(brackets, many=True).data)


# ---------------------------------------------------------------------------
# PayrollPeriod
# ---------------------------------------------------------------------------

class PayrollPeriodView(APIView):
    """GET → listar períodos   POST → crear quincena"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.period.create")()]
        return [rbac_permission("nomina.period.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = PayrollPeriod.objects.filter(company=company).order_by("-year", "-month", "-period_type")

        year = request.query_params.get("year")
        if year:
            qs = qs.filter(year=int(year))
        st = request.query_params.get("status")
        if st:
            qs = qs.filter(status=st)

        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs, limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": PayrollPeriodOut(rows, many=True).data})

    def post(self, request):
        company: OrgUnit = request.company
        s = PayrollPeriodCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            period = create_period(
                request=request,
                actor=request.user,
                company=company,
                year=v["year"],
                month=v["month"],
                period_type=v["period_type"],
                start_date=v["start_date"],
                end_date=v["end_date"],
                working_days=v.get("working_days", 15),
                exchange_rate_usd=v.get("exchange_rate_usd"),
                notes=v.get("notes", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PayrollPeriodOut(period).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# PayrollSheet
# ---------------------------------------------------------------------------

class PayrollSheetView(APIView):
    """GET → listar planillas de un período   POST → crear planilla"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.sheet.create")()]
        return [rbac_permission("nomina.sheet.read")()]

    def get(self, request, period_id):
        company: OrgUnit = request.company
        period = get_object_or_404(PayrollPeriod, id=period_id, company=company)
        qs = PayrollSheet.objects.filter(period=period).order_by("sheet_name")

        has_inss = request.query_params.get("has_inss")
        if has_inss is not None:
            qs = qs.filter(has_inss=has_inss.lower() == "true")

        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs, limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": PayrollSheetOut(rows, many=True).data})

    def post(self, request, period_id):
        company: OrgUnit = request.company
        period = get_object_or_404(PayrollPeriod, id=period_id, company=company)

        s = PayrollSheetCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        branch = None
        if v.get("branch_id"):
            branch = get_object_or_404(OrgUnit, id=v["branch_id"], parent=company)

        sheet = create_sheet(
            request=request, actor=request.user,
            period=period, sheet_name=v["sheet_name"],
            has_inss=v["has_inss"], branch=branch, notes=v.get("notes", ""),
        )
        return Response(PayrollSheetOut(sheet).data, status=status.HTTP_201_CREATED)


class PayrollSheetActionView(APIView):
    """POST → submit o approve una planilla"""

    permission_classes = [rbac_permission("nomina.sheet.manage")]

    def post(self, request, period_id, sheet_id, action):
        company: OrgUnit = request.company
        period = get_object_or_404(PayrollPeriod, id=period_id, company=company)
        sheet = get_object_or_404(PayrollSheet, id=sheet_id, period=period)

        try:
            if action == "submit":
                sheet = submit_sheet(request=request, actor=request.user, sheet=sheet)
            elif action == "approve":
                sheet = approve_sheet(request=request, actor=request.user, sheet=sheet)
            elif action == "compute":
                count = compute_all_entries_in_sheet(sheet=sheet)
                return Response({"ok": True, "computed": count})
            else:
                return Response({"detail": f"Acción desconocida: {action}"}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PayrollSheetOut(sheet).data)


# ---------------------------------------------------------------------------
# PayrollEntry
# ---------------------------------------------------------------------------

class PayrollEntryView(APIView):
    """GET → listar entradas de una planilla   POST → agregar empleado"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.entry.create")()]
        return [rbac_permission("nomina.entry.read")()]

    def get(self, request, period_id, sheet_id):
        company: OrgUnit = request.company
        period = get_object_or_404(PayrollPeriod, id=period_id, company=company)
        sheet = get_object_or_404(PayrollSheet, id=sheet_id, period=period)

        qs = PayrollEntry.objects.filter(sheet=sheet).order_by("full_name")
        search = request.query_params.get("search")
        if search:
            from django.db.models import Q
            qs = qs.filter(Q(full_name__icontains=search) | Q(inss_number__icontains=search) | Q(cedula__icontains=search))

        limit, offset = get_limit_offset(request)
        total, rows = _paginate(qs, limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset, "results": PayrollEntryOut(rows, many=True).data})

    def post(self, request, period_id, sheet_id):
        company: OrgUnit = request.company
        period = get_object_or_404(PayrollPeriod, id=period_id, company=company)
        sheet = get_object_or_404(PayrollSheet, id=sheet_id, period=period)

        s = PayrollEntryCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        entry = PayrollEntry.objects.create(
            sheet=sheet,
            employee_id=v.get("employee_id"),
            inss_number=v.get("inss_number", ""),
            cedula=v.get("cedula", ""),
            full_name=v["full_name"],
            gender=v.get("gender", ""),
            cargo=v.get("cargo", ""),
            has_inss=v["has_inss"],
            salary_type=v["salary_type"],
            payment_frequency=v["payment_frequency"],
            base_salary_usd=v.get("base_salary_usd"),
            base_salary_nio=v.get("base_salary_nio", Decimal("0.00")),
            exchange_rate=period.exchange_rate_usd,
            days_in_period=v["days_in_period"],
            days_worked=v["days_worked"],
            days_subsidy=v.get("days_subsidy", Decimal("0.00")),
            overtime_hours=v.get("overtime_hours", Decimal("0.00")),
            sunday_worked_days=v.get("sunday_worked_days", 0),
            seventh_day_days=v.get("seventh_day_days", Decimal("0.00")),
            holiday_worked_days=v.get("holiday_worked_days", Decimal("0.00")),
            loan_payment=v.get("loan_payment", Decimal("0.00")),
            food_deduction=v.get("food_deduction", Decimal("0.00")),
            advance_deduction=v.get("advance_deduction", Decimal("0.00")),
            store_credit_deduction=v.get("store_credit_deduction", Decimal("0.00")),
            other_deductions=v.get("other_deductions", Decimal("0.00")),
            other_income=v.get("other_income", Decimal("0.00")),
            ir_amount=v.get("ir_amount", Decimal("0.00")),
            # Un IR provisto (>0) por el cliente es un override manual: compute_all lo respeta.
            ir_manual=bool(v.get("ir_amount")),
            notes=v.get("notes", ""),
        )

        # Calcular automáticamente al crear
        entry = compute_entry(entry=entry)
        return Response(PayrollEntryOut(entry).data, status=status.HTTP_201_CREATED)


class PayrollSheetXlsxView(APIView):
    """Descarga la planilla legal (norma INSS) en .xlsx con todas las casillas."""

    permission_classes = [rbac_permission("nomina.sheet.read")]

    def get(self, request, period_id, sheet_id):
        company: OrgUnit = request.company
        period = get_object_or_404(PayrollPeriod, id=period_id, company=company)
        sheet = get_object_or_404(PayrollSheet, id=sheet_id, period=period)
        content = render_planilla_xlsx(sheet)
        resp = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = (
            f'attachment; filename="planilla_{period.year}_{period.month:02d}_sheet{sheet_id}.xlsx"'
        )
        return resp


class PayrollSheetPdfView(APIView):
    """Descarga la planilla legal en PDF (WeasyPrint), mismas casillas que el .xlsx."""

    permission_classes = [rbac_permission("nomina.sheet.read")]

    def get(self, request, period_id, sheet_id):
        company: OrgUnit = request.company
        period = get_object_or_404(PayrollPeriod, id=period_id, company=company)
        sheet = get_object_or_404(PayrollSheet, id=sheet_id, period=period)
        content = render_planilla_pdf(sheet)
        resp = HttpResponse(content, content_type="application/pdf")
        resp["Content-Disposition"] = (
            f'attachment; filename="planilla_{period.year}_{period.month:02d}_sheet{sheet_id}.pdf"'
        )
        return resp
