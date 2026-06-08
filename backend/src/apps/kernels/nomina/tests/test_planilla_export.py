"""Tests del export de la planilla legal (.xlsx) — todas las casillas + agrupaciones + firmas."""
from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.nomina.models import PayrollEntry, PayrollPeriod, PayrollSheet, PeriodType, SalaryType
from apps.kernels.nomina.planilla_export import build_planilla_matrix, render_planilla_xlsx
from apps.kernels.nomina.services import compute_entry, create_default_nicaragua_config
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _scope():
    tag = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{tag}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{tag}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{tag}", parent=company)
    return company, branch


def _actor():
    u = f"u_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=u, email=f"{u}@t.local", password="x")


def _req(actor, *, company=None):
    return SimpleNamespace(user=actor, META={}, company=company, branch=None, _request=None,
                           ctx=None, request_id="r", path="", method="POST")


def _sheet_with_entry(company, branch, actor):
    create_default_nicaragua_config(request=_req(actor, company=company), actor=actor, company=company, fiscal_year=2026)
    period = PayrollPeriod.objects.create(
        company=company, year=2026, month=6, period_type=PeriodType.CATORCENA,
        start_date=date(2026, 6, 1), end_date=date(2026, 6, 14), working_days=14,
    )
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="FINCA ABISINIA", has_inss=True)
    emp = Employee.objects.create(company=company, employee_code="E1", first_name="Juan", last_name="Pérez", is_active=True)
    entry = PayrollEntry.objects.create(
        sheet=sheet, employee=emp, full_name="Juan Pérez", inss_number="1234567",
        cedula="001-010190-0001A", cargo="Cortador", has_inss=True, salary_type=SalaryType.DAILY,
        base_salary_nio=Decimal("6000.00"), days_in_period=14, days_worked=Decimal("12.00"),
        seventh_day_days=Decimal("2.00"),
    )
    compute_entry(entry=entry)
    return sheet, entry


@pytest.mark.django_db
def test_planilla_matrix_includes_septimo_and_basico():
    company, branch = _scope()
    actor = _actor()
    sheet, entry = _sheet_with_entry(company, branch, actor)
    data = build_planilla_matrix(sheet)
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["seventh_day_days"] == Decimal("2.00")
    # Total Básico = salario del período + séptimo + feriado
    assert row["total_basico"] == entry.quincenal_salary + entry.seventh_day_amount + entry.holiday_amount
    # Totales agregan el neto
    assert data["totals"]["net_to_pay"] == entry.net_to_pay


@pytest.mark.django_db
def test_planilla_xlsx_is_valid_and_has_all_casillas():
    company, branch = _scope()
    actor = _actor()
    sheet, entry = _sheet_with_entry(company, branch, actor)
    content = render_planilla_xlsx(sheet)

    z = zipfile.ZipFile(io.BytesIO(content))
    # xlsx válido (partes obligatorias presentes)
    for part in ("[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"):
        assert part in z.namelist()
    xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")

    # Casillas legales + grupos + firmas + datos del empleado
    for label in (
        "No. INSS", "Cédula", "Nombres y Apellidos", "Salario Diario", "Salario del Período",
        "Días Laborados", "Séptimo Día", "Total Básico", "Total Ingresos",
        "INSS", "IR", "Abono Préstamos", "Total Retención", "Alimentación",
        "Neto a Pagar", "INSS Patronal", "INATEC 2%", "Total Gastos Nómina",
        "INGRESOS", "RETENCIONES", "COSTOS PATRONALES",
        "ELABORADO", "REVISADO", "AUTORIZADO", "TOTALES",
    ):
        assert label in xml, f"falta casilla/etiqueta: {label}"
    assert "Juan Pérez" in xml
    assert "1234567" in xml
    # encabezados de grupo combinados
    assert "<mergeCell" in xml
