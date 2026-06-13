"""PDF de la planilla legal (WeasyPrint).

La lógica HTML (`build_planilla_html`) y el cableado del endpoint se testean sin
depender de WeasyPrint (que requiere libs de sistema). El render real va detrás de
`importorskip`: corre solo cuando la imagen tiene WeasyPrint instalado.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.nomina import views as nomina_views
from apps.kernels.nomina.models import PayrollEntry, PayrollPeriod, PayrollSheet, PeriodType
from apps.kernels.nomina.planilla_pdf import build_planilla_html
from apps.kernels.nomina.services import compute_entry, create_default_nicaragua_config
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _scope():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    return company, branch


def _client(*, company, branch, perms):
    u = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", email=f"e_{uuid.uuid4().hex[:8]}@t.com", password="x")
    UserMembership.objects.create(user=u, org_unit=company, is_active=True)
    UserMembership.objects.create(user=u, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=u, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=u, role=role, org_unit=branch, is_active=True)
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": u.username, "password": "x"}, format="json")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


def _config(company, actor):
    req = SimpleNamespace(user=actor, META={}, company=company, branch=None, _request=None,
                          ctx=None, request_id="", path="", method="POST")
    return create_default_nicaragua_config(request=req, actor=actor, company=company, fiscal_year=2026)


def _sheet_with_entry(company, branch, *, full_name="Juan Pérez López"):
    period = PayrollPeriod.objects.create(
        company=company, year=2026, month=6, period_type=PeriodType.CATORCENA,
        start_date=date(2026, 6, 1), end_date=date(2026, 6, 14), working_days=14,
    )
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="Finca Santa Isabel", has_inss=True)
    entry = PayrollEntry.objects.create(
        sheet=sheet, full_name=full_name, has_inss=True,
        base_salary_nio=Decimal("14000.00"), days_in_period=14, days_worked=Decimal("14.00"),
    )
    compute_entry(entry=entry)
    return period, sheet


@pytest.mark.django_db
def test_build_planilla_html_contains_casillas_and_employee():
    company, branch = _scope()
    actor = User.objects.create_user(username=f"a_{uuid.uuid4().hex[:6]}", email="a@t.com", password="x")
    _config(company, actor)
    _period, sheet = _sheet_with_entry(company, branch, full_name="María Cardoza")

    html = build_planilla_html(sheet)
    assert isinstance(html, str)
    assert "PLANILLA DE SALARIO" in html
    assert "María Cardoza" in html
    # Encabezados agrupados + casillas clave
    for token in ("INGRESOS", "RETENCIONES", "COSTOS PATRONALES", "Séptimo Día", "Neto a Pagar"):
        assert token in html, token
    assert "TOTALES" in html
    assert "ELABORADO POR" in html


@pytest.mark.django_db
def test_pdf_endpoint_returns_pdf_with_permission(monkeypatch):
    company, branch = _scope()
    actor = User.objects.create_user(username=f"a_{uuid.uuid4().hex[:6]}", email="a@t.com", password="x")
    _config(company, actor)
    period, sheet = _sheet_with_entry(company, branch)

    # No exigimos WeasyPrint para testear el cableado del endpoint.
    monkeypatch.setattr(nomina_views, "render_planilla_pdf", lambda s: b"%PDF-1.7 fake")

    c = _client(company=company, branch=branch, perms=["nomina.sheet.read"])
    r = c.get(f"/api/nomina/periods/{period.id}/sheets/{sheet.id}/planilla.pdf")
    assert r.status_code == 200, r.status_code
    assert r["Content-Type"] == "application/pdf"
    assert "attachment" in r["Content-Disposition"]
    assert r.content.startswith(b"%PDF")


@pytest.mark.django_db
def test_pdf_endpoint_denied_without_permission():
    company, branch = _scope()
    actor = User.objects.create_user(username=f"a_{uuid.uuid4().hex[:6]}", email="a@t.com", password="x")
    _config(company, actor)
    period, sheet = _sheet_with_entry(company, branch)

    c = _client(company=company, branch=branch, perms=[])
    r = c.get(f"/api/nomina/periods/{period.id}/sheets/{sheet.id}/planilla.pdf")
    assert r.status_code == 403, r.status_code


@pytest.mark.django_db
def test_render_planilla_pdf_real_bytes():
    """Render real: corre solo si WeasyPrint Y sus libs nativas están disponibles.

    `importorskip` no basta: las libs del SO (gobject/pango) pueden faltar aun con el wheel
    instalado, y su ausencia lanza ``OSError`` (no ``ImportError``) — en esta versión, ya
    al importar weasyprint (cffi carga las libs ahí). Capturamos import y render, y saltamos,
    para que el test no FALLE en entornos solo-pip (corre y cubre normal donde sí están las
    libs, p.ej. CI con la imagen del Dockerfile).
    """
    try:
        import weasyprint
        weasyprint.HTML(string="<p>x</p>").write_pdf()
    except (ImportError, OSError) as exc:
        pytest.skip(f"WeasyPrint no disponible (paquete o libs nativas): {exc}")
    from apps.kernels.nomina.planilla_pdf import render_planilla_pdf

    company, branch = _scope()
    actor = User.objects.create_user(username=f"a_{uuid.uuid4().hex[:6]}", email="a@t.com", password="x")
    _config(company, actor)
    _period, sheet = _sheet_with_entry(company, branch)

    pdf = render_planilla_pdf(sheet)
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf[:4] == b"%PDF"
