from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.common.throttling import MethodThrottleScopeMixin
from apps.modulos.iam.models import OrgUnit

from .models import FincaProfile, Labor, Plot, WorkOrder
from .serializers import (
    FincaProfileIn,
    FincaProfileOut,
    InsumoIn,
    LaborCreateIn,
    LaborOut,
    PlotCreateIn,
    PlotOut,
    PlotUpdateIn,
    WorkOrderCreateIn,
    WorkOrderOut,
    WorkOrderUpdateIn,
)
from .field_link import (
    company_real_cost_summary,
    field_labor_rollup,
    field_zone_rollup,
    finca_real_cost_summary,
    reconcile_field_catalog,
)
from .services import (
    apply_insumo,
    company_cost_summary,
    create_labor,
    create_plot,
    labors_for,
    log_work,
    plot_cost_summary,
    update_work_order,
    upsert_finca_profile,
)

UT = OrgUnit.UnitType


def _branch_of_company(request, branch_id: int) -> OrgUnit:
    return get_object_or_404(OrgUnit, id=branch_id, parent=request.company, unit_type=UT.BRANCH)


def _field_filters(request) -> dict:
    """Filtros opcionales del puente de asistencia: rango de fechas / período."""
    f: dict = {}
    if (df := request.query_params.get("date_from")):
        f["date_from"] = df
    if (dt := request.query_params.get("date_to")):
        f["date_to"] = dt
    if (pp := request.query_params.get("payroll_period_id")):
        f["payroll_period_id"] = pp
    return f


# --------------------------------------------------------------------------- #
# Fincas (BRANCH) + perfil/geografía
# --------------------------------------------------------------------------- #

class FincaListView(APIView):
    permission_classes = [rbac_permission("finca.finca.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        company: OrgUnit = request.company
        fincas = OrgUnit.objects.filter(parent=company, unit_type=UT.BRANCH).order_by("name")
        out = []
        for f in fincas:
            prof = getattr(f, "finca_profile", None)
            out.append(
                {
                    "finca_id": f.id,
                    "name": f.name,
                    "code": f.code,
                    "zona": getattr(prof, "zona", ""),
                    "department": getattr(prof, "department", ""),
                    "municipio": getattr(prof, "municipio", ""),
                    "area_manzanas": str(getattr(prof, "area_manzanas", "")) if prof else "",
                    "is_headquarters": getattr(prof, "is_headquarters", False),
                }
            )
        return Response({"results": out}, status=status.HTTP_200_OK)


class FincaProfileView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {"GET": "heavy_reads", "PUT": "admin_writes"}

    def get_permissions(self):
        if self.request.method == "PUT":
            return [rbac_permission("finca.finca.manage")()]
        return [rbac_permission("finca.finca.read")()]

    def get(self, request, branch_id: int):
        finca = _branch_of_company(request, branch_id)
        prof, _ = FincaProfile.objects.get_or_create(finca=finca)
        return Response(FincaProfileOut(prof).data, status=status.HTTP_200_OK)

    def put(self, request, branch_id: int):
        finca = _branch_of_company(request, branch_id)
        s = FincaProfileIn(data=request.data)
        s.is_valid(raise_exception=True)
        prof = upsert_finca_profile(finca, data=s.validated_data, request=request, actor=request.user)
        return Response(FincaProfileOut(prof).data, status=status.HTTP_200_OK)


# --------------------------------------------------------------------------- #
# Lotes
# --------------------------------------------------------------------------- #

class PlotListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {"GET": "heavy_reads", "POST": "admin_writes"}

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("finca.plot.manage")()]
        return [rbac_permission("finca.plot.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = Plot.objects.filter(finca__parent=company).order_by("finca_id", "code")
        finca_id = request.query_params.get("finca_id")
        if finca_id:
            qs = qs.filter(finca_id=finca_id)
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": PlotOut(rows, many=True).data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        finca_id = request.data.get("finca_id")
        if not finca_id:
            return Response({"finca_id": "Requerido"}, status=status.HTTP_400_BAD_REQUEST)
        finca = _branch_of_company(request, int(finca_id))
        s = PlotCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        plot = create_plot(finca, data=s.validated_data, request=request, actor=request.user)
        return Response({"id": plot.id}, status=status.HTTP_201_CREATED)


class PlotDetailView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {"GET": "heavy_reads", "PATCH": "admin_writes"}

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [rbac_permission("finca.plot.manage")()]
        return [rbac_permission("finca.plot.read")()]

    def _get(self, request, plot_id):
        return get_object_or_404(Plot, id=plot_id, finca__parent=request.company)

    def get(self, request, plot_id: int):
        return Response(PlotOut(self._get(request, plot_id)).data, status=status.HTTP_200_OK)

    def patch(self, request, plot_id: int):
        plot = self._get(request, plot_id)
        s = PlotUpdateIn(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        for k, v in s.validated_data.items():
            setattr(plot, k, v)
        plot.save()
        return Response(PlotOut(plot).data, status=status.HTTP_200_OK)


# --------------------------------------------------------------------------- #
# Catálogo de labores
# --------------------------------------------------------------------------- #

class LaborListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {"GET": "heavy_reads", "POST": "admin_writes"}

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("finca.labor.manage")()]
        return [rbac_permission("finca.labor.read")()]

    def get(self, request):
        rows = labors_for(request.company)
        return Response({"results": LaborOut(rows, many=True).data}, status=status.HTTP_200_OK)

    def post(self, request):
        s = LaborCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        labor = create_labor(request.company, data=s.validated_data, request=request, actor=request.user)
        return Response({"id": labor.id}, status=status.HTTP_201_CREATED)


# --------------------------------------------------------------------------- #
# Órdenes de trabajo / bitácora
# --------------------------------------------------------------------------- #

class WorkOrderListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {"GET": "heavy_reads", "POST": "admin_writes"}

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("finca.work.capture")()]
        return [rbac_permission("finca.work.read")()]

    def get(self, request):
        qs = WorkOrder.objects.filter(finca__parent=request.company).order_by("-created_at", "-id")
        for key in ("finca_id", "plot_id", "status", "season_label"):
            val = request.query_params.get(key)
            if val:
                qs = qs.filter(**{key: val})
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": WorkOrderOut(rows, many=True).data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        s = WorkOrderCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        plot = get_object_or_404(Plot, id=v["plot_id"], finca__parent=request.company)
        labor = (
            Labor.objects.filter(id=v["labor_id"])
            .filter(Q(company=request.company) | Q(company__isnull=True))
            .first()
        )
        if labor is None:
            return Response({"labor_id": "Labor no encontrada/aplicable"}, status=status.HTTP_400_BAD_REQUEST)
        wo = log_work(plot.finca, plot=plot, labor=labor, data=v, request=request, actor=request.user)
        return Response({"id": wo.id, "status": wo.status}, status=status.HTTP_201_CREATED)


class WorkOrderDetailView(APIView):
    permission_classes = [rbac_permission("finca.work.capture")]
    throttle_scope = "admin_writes"

    def patch(self, request, work_order_id: int):
        wo = get_object_or_404(WorkOrder, id=work_order_id, finca__parent=request.company)
        s = WorkOrderUpdateIn(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        wo = update_work_order(wo, data=s.validated_data, request=request, actor=request.user)
        return Response(WorkOrderOut(wo).data, status=status.HTTP_200_OK)


class WorkOrderInsumoView(APIView):
    permission_classes = [rbac_permission("finca.work.capture")]
    throttle_scope = "admin_writes"

    def post(self, request, work_order_id: int):
        wo = get_object_or_404(WorkOrder, id=work_order_id, finca__parent=request.company)
        s = InsumoIn(data=request.data)
        s.is_valid(raise_exception=True)
        app = apply_insumo(wo, data=s.validated_data, request=request, actor=request.user)
        return Response({"id": app.id}, status=status.HTTP_201_CREATED)


# --------------------------------------------------------------------------- #
# Reportes / costeo
# --------------------------------------------------------------------------- #

class PlotCostReportView(APIView):
    permission_classes = [rbac_permission("finca.report.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        finca_id = request.query_params.get("finca_id")
        if not finca_id:
            return Response({"finca_id": "Requerido"}, status=status.HTTP_400_BAD_REQUEST)
        finca = _branch_of_company(request, int(finca_id))
        season = request.query_params.get("season") or None
        return Response({"results": plot_cost_summary(finca, season=season)}, status=status.HTTP_200_OK)


class CompanyCostReportView(APIView):
    permission_classes = [rbac_permission("finca.report.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        season = request.query_params.get("season") or None
        return Response(company_cost_summary(request.company, season=season), status=status.HTTP_200_OK)


# --------------------------------------------------------------------------- #
# Puente Asistencia de campo (nómina) → Labores → costeo real (Fase 2)
# --------------------------------------------------------------------------- #

class FieldLaborCostReportView(APIView):
    """Jornales reales por labor (y por zona) leídos de la captura de campo."""

    permission_classes = [rbac_permission("finca.field.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        finca_id = request.query_params.get("finca_id")
        if not finca_id:
            return Response({"finca_id": "Requerido"}, status=status.HTTP_400_BAD_REQUEST)
        finca = _branch_of_company(request, int(finca_id))
        filters = _field_filters(request)
        return Response(
            {
                "finca_id": finca.id,
                "by_labor": field_labor_rollup(finca, **filters),
                "by_zone": field_zone_rollup(finca, **filters),
            },
            status=status.HTTP_200_OK,
        )


class FieldReconciliationReportView(APIView):
    """Reconciliación de `labor_code`/`zone_label` del campo contra el catálogo."""

    permission_classes = [rbac_permission("finca.field.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        finca_id = request.query_params.get("finca_id")
        if not finca_id:
            return Response({"finca_id": "Requerido"}, status=status.HTTP_400_BAD_REQUEST)
        finca = _branch_of_company(request, int(finca_id))
        return Response(reconcile_field_catalog(finca, **_field_filters(request)), status=status.HTTP_200_OK)


class FincaRealCostReportView(APIView):
    """Costeo REAL de una finca: mano de obra desde asistencia + insumos."""

    permission_classes = [rbac_permission("finca.field.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        finca_id = request.query_params.get("finca_id")
        if not finca_id:
            return Response({"finca_id": "Requerido"}, status=status.HTTP_400_BAD_REQUEST)
        finca = _branch_of_company(request, int(finca_id))
        season = request.query_params.get("season") or None
        return Response(
            finca_real_cost_summary(finca, season=season, **_field_filters(request)),
            status=status.HTTP_200_OK,
        )


class CompanyRealCostReportView(APIView):
    """Costeo REAL consolidado de la empresa (por finca y por zona)."""

    permission_classes = [rbac_permission("finca.field.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        season = request.query_params.get("season") or None
        return Response(
            company_real_cost_summary(request.company, season=season, **_field_filters(request)),
            status=status.HTTP_200_OK,
        )
