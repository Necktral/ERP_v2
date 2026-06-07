"""Endpoints HTTP del régimen INSS (afiliación fechada + elección por período).

Capa delgada sobre `services_inss.py`. Resuelve el "dolor de cabeza" de los
trabajadores que cotizan un período y al siguiente no, sin el shuffle manual entre
planillas CON/SIN INSS. RBAC: `nomina.inss.manage` (escritura) · `nomina.inss.read`.
"""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

from .models import EmployeeInssEnrollment, PayrollInssElection, PayrollPeriod
from .serializers import (
    InssElectionOut,
    InssElectionSetIn,
    InssEnrollmentCreateIn,
    InssEnrollmentOut,
)
from .services_inss import (
    classify_entries_by_inss,
    resolve_period_inss_elections,
    set_employee_inss_enrollment,
    set_period_inss_election,
)


def _period(company: OrgUnit, period_id: int) -> PayrollPeriod:
    return get_object_or_404(PayrollPeriod, id=period_id, company=company)


def _employee(company: OrgUnit, employee_id: int) -> Employee:
    return get_object_or_404(Employee, id=employee_id, company=company)


class EmployeeInssEnrollmentView(APIView):
    """GET → historial de afiliación INSS de un empleado   POST → nueva afiliación fechada"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.inss.manage")()]
        return [rbac_permission("nomina.inss.read")()]

    def get(self, request, employee_id):
        employee = _employee(request.company, employee_id)
        qs = EmployeeInssEnrollment.objects.filter(employee=employee).order_by("-effective_from")
        return Response({"results": InssEnrollmentOut(qs, many=True).data})

    def post(self, request, employee_id):
        employee = _employee(request.company, employee_id)
        s = InssEnrollmentCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        enrollment = set_employee_inss_enrollment(
            request=request, actor=request.user, employee=employee,
            regime=v["regime"], effective_from=v["effective_from"], reason=v.get("reason", ""),
        )
        return Response(InssEnrollmentOut(enrollment).data, status=status.HTTP_201_CREATED)


class PeriodInssElectionView(APIView):
    """GET → elecciones INSS del período   POST → override auditado de un trabajador"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("nomina.inss.manage")()]
        return [rbac_permission("nomina.inss.read")()]

    def get(self, request, period_id):
        period = _period(request.company, period_id)
        qs = PayrollInssElection.objects.filter(period=period).order_by("employee_id", "cedula")
        return Response({"results": InssElectionOut(qs, many=True).data})

    def post(self, request, period_id):
        period = _period(request.company, period_id)
        s = InssElectionSetIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        employee = _employee(request.company, v["employee_id"]) if v.get("employee_id") else None
        election = set_period_inss_election(
            request=request, actor=request.user, period=period,
            employee=employee, cedula=v.get("cedula", ""),
            elected_has_inss=v["elected_has_inss"], reason=v.get("reason", ""),
        )
        return Response(InssElectionOut(election).data, status=status.HTTP_201_CREATED)


class PeriodInssResolveView(APIView):
    """POST → materializa la elección por afiliación para cada empleado con entry en el período"""

    permission_classes = [rbac_permission("nomina.inss.manage")]

    def post(self, request, period_id):
        period = _period(request.company, period_id)
        elections = resolve_period_inss_elections(request=request, actor=request.user, period=period)
        return Response({"elections": elections})


class PeriodInssClassifyView(APIView):
    """POST → auto-clasifica cada entry a la planilla CON/SIN INSS correcta y recalcula"""

    permission_classes = [rbac_permission("nomina.inss.manage")]

    def post(self, request, period_id):
        period = _period(request.company, period_id)
        result = classify_entries_by_inss(request=request, actor=request.user, period=period)
        return Response(result)
