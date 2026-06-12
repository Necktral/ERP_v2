"""API de la pantalla de asistencia del día (mandador/capataz, PC y cel).

Permiso: nomina.field.capture (el de captura de campo — quien levanta la lista).
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission
from apps.modulos.common.throttling import MethodThrottleScopeMixin
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

from .asistencia_dia import (
    ESTADOS_VALIDOS,
    ensure_work_day,
    hoy_local,
    marcar_asistencia,
    personal_del_dia,
)
from .models import FieldWorkDay
from .services import FieldAttendanceError


class MarcarSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    estado = serializers.CharField(max_length=16)
    # Solo para ENFERMO: con constancia médica certificada el día SE PAGA.
    constancia_medica = serializers.BooleanField(required=False, default=False)


def _find_work_day(request, work_date) -> FieldWorkDay | None:
    company: OrgUnit = request.company
    qs = FieldWorkDay.objects.filter(company=company, work_date=work_date)
    branch = getattr(request, "branch", None)
    if branch is not None:
        qs = qs.filter(branch=branch)
    return qs.first()


class AsistenciaHoyView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {"GET": "heavy_reads", "POST": "admin_writes"}

    def get_permissions(self):
        # SoD: ver la lista (supervisor) vs marcarla (mandador/capataz/planillero).
        if self.request.method == "POST":
            return [rbac_permission("nomina.field.capture")()]
        return [rbac_permission("nomina.field.read")()]

    def get(self, request):
        work_date = hoy_local()
        work_day = _find_work_day(request, work_date)
        results = personal_del_dia(request=request, work_day=work_day)
        marcados = sum(1 for r in results if r["estado"] != "SIN_MARCAR")
        return Response(
            {
                "work_date": str(work_date),
                "work_day_id": work_day.id if work_day else None,
                "work_day_status": work_day.status if work_day else None,
                "total": len(results),
                "marcados": marcados,
                "results": results,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        s = MarcarSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        estado = s.validated_data["estado"].strip().upper()
        if estado not in ESTADOS_VALIDOS:
            return Response(
                {"estado": f"Estado inválido. Opciones: {sorted(ESTADOS_VALIDOS)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        employee = get_object_or_404(
            Employee, id=s.validated_data["employee_id"], company=request.company, is_active=True
        )
        work_date = hoy_local()
        try:
            work_day = ensure_work_day(request=request, actor=request.user, work_date=work_date)
            marcar_asistencia(
                request=request,
                actor=request.user,
                work_day=work_day,
                employee=employee,
                estado=estado,
                constancia_medica=bool(s.validated_data.get("constancia_medica")),
            )
        except FieldAttendanceError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "employee_id": employee.id, "estado": estado}, status=status.HTTP_200_OK)
