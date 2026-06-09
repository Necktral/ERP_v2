from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

from .alerts import run_fleet_alerts
from .models import (
    Driver,
    FleetAsset,
    FleetDocument,
    MaintenancePlan,
    MaintenanceType,
)
from .serializers import (
    ApplyPlanSerializer,
    AssetUpsertSerializer,
    AssignDriverSerializer,
    DocumentSerializer,
    DriverUpsertSerializer,
    MaintenanceTypeSerializer,
    PlanSerializer,
    RecordMeterSerializer,
    RuleSerializer,
)
from .services import (
    FleetError,
    add_rule,
    apply_plan_to_asset,
    assign_driver,
    create_plan,
    record_meter_reading,
    register_document,
    upsert_asset,
    upsert_driver,
    upsert_maintenance_type,
)


def _company(request):
    return getattr(request, "company", None)


def _asset_payload(a: FleetAsset) -> dict:
    return {
        "id": a.id, "code": a.code, "name": a.name, "asset_type": a.asset_type, "status": a.status,
        "plate": a.plate, "make": a.make, "model": a.model, "year": a.year,
        "current_odometer_km": str(a.current_odometer_km), "current_hourmeter": str(a.current_hourmeter),
        "has_obd": a.has_obd, "obd_protocol": a.obd_protocol, "branch_id": a.branch_id,
    }


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "fleet"}, status=status.HTTP_200_OK)


class AssetView(APIView):
    def get_permissions(self):
        code = "fleet.asset.read" if self.request.method == "GET" else "fleet.asset.manage"
        return [rbac_permission(code)()]

    def get(self, request):
        company = _company(request)
        rows = FleetAsset.objects.filter(company=company).order_by("code")
        if request.query_params.get("asset_type"):
            rows = rows.filter(asset_type=request.query_params["asset_type"])
        return Response([_asset_payload(a) for a in rows], status=status.HTTP_200_OK)

    def post(self, request):
        company = _company(request)
        if company is None:
            return Response({"detail": "X-Company-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = AssetUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        code = v.pop("code")
        branch_id = v.pop("branch_id", None)
        if branch_id:
            v["branch"] = OrgUnit.objects.filter(id=branch_id).first()
        asset = upsert_asset(request=request, actor=request.user, company=company, code=code, **v)
        return Response(_asset_payload(asset), status=status.HTTP_201_CREATED)


class AssetDetailView(APIView):
    permission_classes = [rbac_permission("fleet.asset.read")]

    def get(self, request, asset_id: int):
        asset = FleetAsset.objects.filter(id=asset_id, company=_company(request)).first()
        if asset is None:
            return Response({"detail": "activo no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        return Response(_asset_payload(asset), status=status.HTTP_200_OK)


class DriverView(APIView):
    permission_classes = [rbac_permission("fleet.driver.manage")]

    def post(self, request):
        company = _company(request)
        if company is None:
            return Response({"detail": "X-Company-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = DriverUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        full_name = v.pop("full_name")
        employee = None
        emp_id = v.pop("employee_id", None)
        if emp_id:
            employee = Employee.objects.filter(id=emp_id, company=company).first()
            if employee is None:
                return Response({"detail": "employee no existe en esta empresa"}, status=status.HTTP_400_BAD_REQUEST)
        driver = upsert_driver(request=request, actor=request.user, company=company, full_name=full_name, employee=employee, **v)
        return Response({"id": driver.id, "full_name": driver.full_name, "license_number": driver.license_number}, status=status.HTTP_201_CREATED)


class AssignDriverView(APIView):
    permission_classes = [rbac_permission("fleet.driver.manage")]

    def post(self, request):
        company = _company(request)
        s = AssignDriverSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        asset = FleetAsset.objects.filter(id=s.validated_data["asset_id"], company=company).first()
        driver = Driver.objects.filter(id=s.validated_data["driver_id"], company=company).first()
        if asset is None or driver is None:
            return Response({"detail": "activo o conductor no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        asg = assign_driver(request=request, actor=request.user, asset=asset, driver=driver)
        return Response({"assignment_id": asg.id, "asset_id": asset.id, "driver_id": driver.id}, status=status.HTTP_201_CREATED)


class RecordMeterView(APIView):
    permission_classes = [rbac_permission("fleet.meter.record")]

    def post(self, request):
        company = _company(request)
        s = RecordMeterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        asset = FleetAsset.objects.filter(id=s.validated_data["asset_id"], company=company).first()
        if asset is None:
            return Response({"detail": "activo no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        result = record_meter_reading(
            request=request, actor=request.user, asset=asset,
            odometer_km=s.validated_data.get("odometer_km"), hourmeter=s.validated_data.get("hourmeter"),
        )
        return Response(result, status=status.HTTP_200_OK)


class DocumentView(APIView):
    def get_permissions(self):
        code = "fleet.document.read" if self.request.method == "GET" else "fleet.document.manage"
        return [rbac_permission(code)()]

    def get(self, request):
        company = _company(request)
        rows = FleetDocument.objects.filter(company=company)
        if request.query_params.get("status"):
            rows = rows.filter(status=request.query_params["status"])
        return Response(
            [{"id": d.id, "doc_type": d.doc_type, "status": d.status,
              "expiry_date": d.expiry_date.isoformat() if d.expiry_date else None,
              "asset_id": d.asset_id, "driver_id": d.driver_id} for d in rows.order_by("expiry_date")],
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        company = _company(request)
        if company is None:
            return Response({"detail": "X-Company-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = DocumentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        doc_type = v.pop("doc_type")
        asset = driver = None
        if v.pop("asset_id", None):
            asset = FleetAsset.objects.filter(id=s.validated_data["asset_id"], company=company).first()
        if v.pop("driver_id", None):
            driver = Driver.objects.filter(id=s.validated_data["driver_id"], company=company).first()
        try:
            doc = register_document(
                request=request, actor=request.user, company=company, doc_type=doc_type,
                asset=asset, driver=driver, **v,
            )
        except FleetError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": doc.id, "doc_type": doc.doc_type, "status": doc.status}, status=status.HTTP_201_CREATED)


class MaintenanceTypeView(APIView):
    permission_classes = [rbac_permission("fleet.maintenance.manage")]

    def post(self, request):
        company = _company(request)
        s = MaintenanceTypeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        mt = upsert_maintenance_type(company=company, code=v.pop("code"), name=v.pop("name"), **v)
        return Response({"id": mt.id, "code": mt.code, "name": mt.name}, status=status.HTTP_201_CREATED)


class PlanView(APIView):
    permission_classes = [rbac_permission("fleet.maintenance.manage")]

    def post(self, request):
        company = _company(request)
        s = PlanSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        plan = create_plan(company=company, name=s.validated_data["name"], asset_class=s.validated_data.get("asset_class", ""))
        return Response({"id": plan.id, "name": plan.name}, status=status.HTTP_201_CREATED)


class RuleView(APIView):
    permission_classes = [rbac_permission("fleet.maintenance.manage")]

    def post(self, request):
        company = _company(request)
        s = RuleSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        plan = MaintenancePlan.objects.filter(id=v["plan_id"], company=company).first()
        mtype = MaintenanceType.objects.filter(id=v["maintenance_type_id"], company=company).first()
        if plan is None or mtype is None:
            return Response({"detail": "plan o tipo no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        rule = add_rule(
            plan=plan, maintenance_type=mtype, trigger_basis=v["trigger_basis"],
            interval_km=v.get("interval_km"), interval_hours=v.get("interval_hours"),
            interval_days=v.get("interval_days"), severity_factor=v.get("severity_factor"),
            recommended_action=v.get("recommended_action", ""),
        )
        return Response({"id": rule.id, "plan_id": plan.id}, status=status.HTTP_201_CREATED)


class ApplyPlanView(APIView):
    permission_classes = [rbac_permission("fleet.maintenance.manage")]

    def post(self, request):
        company = _company(request)
        s = ApplyPlanSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        asset = FleetAsset.objects.filter(id=s.validated_data["asset_id"], company=company).first()
        plan = MaintenancePlan.objects.filter(id=s.validated_data["plan_id"], company=company).first()
        if asset is None or plan is None:
            return Response({"detail": "activo o plan no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        states = apply_plan_to_asset(asset=asset, plan=plan)
        return Response({"asset_id": asset.id, "states_created": len(states)}, status=status.HTTP_201_CREATED)


class RunAlertsView(APIView):
    permission_classes = [rbac_permission("fleet.maintenance.manage")]

    def post(self, request):
        company = _company(request)
        if company is None:
            return Response({"detail": "X-Company-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        horizon = int(request.data.get("horizon_days", 30))
        result = run_fleet_alerts(company=company, horizon_days=horizon, actor=request.user)
        return Response(
            {"documents_flagged": len(result["documents"]), "maintenance_flagged": len(result["maintenance"])},
            status=status.HTTP_200_OK,
        )
