"""API del control biométrico (fuente ① de asistencia).

Permisos (sin códigos nuevos):
  - Dispositivos (crear/editar/rotar token): nomina.config.manage
  - Import de archivo, mapeo y rollup:       nomina.attendance.build
  - Lecturas (dispositivos, chequeos, lotes): nomina.attendance.read
  - Push del aparato: SIN sesión — token del dispositivo (X-Device-Token).
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.audit.writer import write_event
from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.common.throttling import MethodThrottleScopeMixin
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

from ..models import PayrollPeriod
from .models_biometric import (
    BiometricCheck,
    BiometricCheckDirection,
    BiometricDevice,
    BiometricImportBatch,
    new_device_token,
)
from .services_biometric import (
    ParsedCheck,
    import_checks_file,
    ingest_checks,
    rollup_biometric_to_period,
    set_person_map,
)
from .tabular_reader import TabularReadError


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


class DeviceCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    vendor = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    serial = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    branch_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class DeviceUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False)
    vendor = serializers.CharField(max_length=120, required=False, allow_blank=True)
    serial = serializers.CharField(max_length=120, required=False, allow_blank=True)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)


class PushCheckSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    ts = serializers.DateTimeField()
    direction = serializers.CharField(max_length=16, required=False, allow_blank=True, default="")
    name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")


class PushSerializer(serializers.Serializer):
    checks = PushCheckSerializer(many=True)


class MapSerializer(serializers.Serializer):
    external_code = serializers.CharField(max_length=64)
    employee_id = serializers.IntegerField()


class RollupSerializer(serializers.Serializer):
    period_id = serializers.IntegerField()


def _device_payload(d: BiometricDevice, *, include_token: bool = False) -> dict:
    out = {
        "id": d.id,
        "name": d.name,
        "vendor": d.vendor,
        "serial": d.serial,
        "branch_id": d.branch_id,
        "is_active": d.is_active,
        "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
        "created_at": d.created_at.isoformat(),
    }
    if include_token:
        out["api_token"] = d.api_token
    return out


# ---------------------------------------------------------------------------
# Dispositivos
# ---------------------------------------------------------------------------


class BiometricDeviceListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {"GET": "heavy_reads", "POST": "admin_writes"}

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.config.manage")()]
        return [rbac_permission("nomina.attendance.read")()]

    def get(self, request):
        qs = BiometricDevice.objects.filter(company=request.company).order_by("name")
        return Response({"results": [_device_payload(d) for d in qs]}, status=status.HTTP_200_OK)

    def post(self, request):
        s = DeviceCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        branch = None
        if v.get("branch_id") is not None:
            branch = get_object_or_404(
                OrgUnit, id=int(v["branch_id"]), parent=request.company, unit_type=OrgUnit.UnitType.BRANCH
            )
        device = BiometricDevice.objects.create(
            company=request.company,
            branch=branch,
            name=v["name"],
            vendor=v.get("vendor", ""),
            serial=v.get("serial", ""),
            created_by=request.user,
        )
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_BIOMETRIC_DEVICE_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="DEVICE",
            subject_id=str(device.id),
            metadata={"name": device.name},
        )
        # el token se muestra UNA vez (como una clave temporal)
        return Response(_device_payload(device, include_token=True), status=status.HTTP_201_CREATED)


class BiometricDeviceDetailView(APIView):
    permission_classes = [rbac_permission("nomina.config.manage")]
    throttle_scope = "admin_writes"

    def patch(self, request, device_pk: int):
        device = get_object_or_404(BiometricDevice, id=device_pk, company=request.company)
        s = DeviceUpdateSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if "branch_id" in v:
            if v["branch_id"] is None:
                device.branch = None
            else:
                device.branch = get_object_or_404(
                    OrgUnit, id=int(v["branch_id"]), parent=request.company, unit_type=OrgUnit.UnitType.BRANCH
                )
        for f in ["name", "vendor", "serial", "is_active"]:
            if f in v:
                setattr(device, f, v[f])
        device.save()
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_BIOMETRIC_DEVICE_UPDATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="DEVICE",
            subject_id=str(device.id),
            metadata={"fields": sorted(v.keys())},
        )
        return Response(_device_payload(device), status=status.HTTP_200_OK)


class BiometricDeviceRotateTokenView(APIView):
    permission_classes = [rbac_permission("nomina.config.manage")]
    throttle_scope = "admin_writes"

    def post(self, request, device_pk: int):
        device = get_object_or_404(BiometricDevice, id=device_pk, company=request.company)
        device.api_token = new_device_token()
        device.save(update_fields=["api_token", "updated_at"])
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_BIOMETRIC_DEVICE_UPDATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="DEVICE",
            subject_id=str(device.id),
            metadata={"fields": ["api_token"]},
        )
        return Response(_device_payload(device, include_token=True), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Import de archivo (la vía principal mientras no hay push)
# ---------------------------------------------------------------------------


class BiometricImportView(APIView):
    permission_classes = [rbac_permission("nomina.attendance.build")]
    throttle_scope = "admin_writes"

    def post(self, request, device_pk: int):
        device = get_object_or_404(BiometricDevice, id=device_pk, company=request.company, is_active=True)
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"file": "Adjuntá el archivo exportado por el aparato (.xlsx o .csv)."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            batch = import_checks_file(
                device=device,
                file_name=upload.name,
                content=upload.read(),
                request=request,
                actor=request.user,
            )
        except TabularReadError as e:
            return Response({"file": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "batch_id": batch.id,
                "rows_total": batch.rows_total,
                "created": batch.created_count,
                "duplicates": batch.duplicate_count,
                "unmatched": batch.unmatched_count,
                "errors": batch.errors,
                "error_count": batch.error_count,
            },
            status=status.HTTP_201_CREATED,
        )


class BiometricBatchListView(APIView):
    permission_classes = [rbac_permission("nomina.attendance.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        qs = BiometricImportBatch.objects.filter(company=request.company).select_related("device")
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        data = [
            {
                "id": b.id,
                "device_id": b.device_id,
                "device_name": b.device.name if b.device_id else "",
                "file_name": b.file_name,
                "rows_total": b.rows_total,
                "created": b.created_count,
                "duplicates": b.duplicate_count,
                "unmatched": b.unmatched_count,
                "error_count": b.error_count,
                "created_at": b.created_at.isoformat(),
            }
            for b in rows
        ]
        return Response({"count": total, "limit": limit, "offset": offset, "results": data})


# ---------------------------------------------------------------------------
# Push del aparato (token por dispositivo, sin sesión)
# ---------------------------------------------------------------------------


class BiometricPushView(APIView):
    """POST /nomina/biometric/push/ — el aparato (o el puente en la WiFi) empuja chequeos.

    Autenticación: header X-Device-Token (token del dispositivo). Idempotente.
    """

    authentication_classes: list = []
    permission_classes: list = []
    throttle_scope = "admin_writes"

    def post(self, request):
        token = (request.headers.get("X-Device-Token") or "").strip()
        if not token:
            return Response({"detail": "Falta X-Device-Token."}, status=status.HTTP_401_UNAUTHORIZED)
        device = BiometricDevice.objects.filter(api_token=token, is_active=True).select_related("company").first()
        if device is None:
            return Response({"detail": "Token inválido."}, status=status.HTTP_401_UNAUTHORIZED)

        s = PushSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        parsed = []
        for item in s.validated_data["checks"]:
            ts = item["ts"]
            if timezone.is_naive(ts):
                ts = timezone.make_aware(ts, timezone.get_current_timezone())
            direction = (item.get("direction") or "").strip().upper()
            if direction not in BiometricCheckDirection.values:
                direction = BiometricCheckDirection.UNKNOWN
            parsed.append(
                ParsedCheck(
                    external_code=item["code"],
                    checked_at=ts,
                    direction=direction,
                    external_name=item.get("name", ""),
                    raw={"push": True},
                )
            )
        result = ingest_checks(device=device, parsed_checks=parsed)
        device.last_seen_at = timezone.now()
        device.save(update_fields=["last_seen_at", "updated_at"])
        return Response(
            {"ok": True, "created": result.created, "duplicates": result.duplicates, "unmatched": result.unmatched},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Chequeos + mapeo de pendientes
# ---------------------------------------------------------------------------


class BiometricCheckListView(APIView):
    permission_classes = [rbac_permission("nomina.attendance.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        qs = BiometricCheck.objects.filter(company=request.company).select_related("employee", "device")
        work_date = request.query_params.get("work_date")
        if work_date:
            qs = qs.filter(work_date=work_date)
        employee_id = request.query_params.get("employee_id")
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        if request.query_params.get("only_unmatched") in ("1", "true"):
            qs = qs.filter(employee__isnull=True)
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        data = [
            {
                "id": c.id,
                "device_id": c.device_id,
                "external_code": c.external_code,
                "external_name": c.external_name,
                "employee_id": c.employee_id,
                "employee_name": (
                    f"{c.employee.first_name} {c.employee.last_name}".strip() if c.employee_id and c.employee else None
                ),
                "direction": c.direction,
                "checked_at": c.checked_at.isoformat(),
                "work_date": str(c.work_date),
            }
            for c in rows
        ]
        return Response({"count": total, "limit": limit, "offset": offset, "results": data})


class BiometricMapView(APIView):
    permission_classes = [rbac_permission("nomina.attendance.build")]
    throttle_scope = "admin_writes"

    def post(self, request):
        s = MapSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        employee = get_object_or_404(Employee, id=s.validated_data["employee_id"], company=request.company)
        try:
            rematched = set_person_map(
                company=request.company,
                external_code=s.validated_data["external_code"],
                employee=employee,
                request=request,
                actor=request.user,
            )
        except ValueError:
            return Response({"detail": "El trabajador no pertenece a esta empresa."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "rematched_checks": rematched}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Rollup al período (alimenta el cruce de 3 controles)
# ---------------------------------------------------------------------------


class BiometricRollupView(APIView):
    permission_classes = [rbac_permission("nomina.attendance.build")]
    throttle_scope = "admin_writes"

    def post(self, request):
        s = RollupSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        period = get_object_or_404(PayrollPeriod, id=s.validated_data["period_id"], company=request.company)
        try:
            result = rollup_biometric_to_period(period=period, request=request, actor=request.user)
        except ValueError:
            return Response(
                {"detail": "El período ya no es editable (aprobado/pagado/cerrado)."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"ok": True, **result}, status=status.HTTP_200_OK)
