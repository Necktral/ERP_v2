"""Tests de la pantalla de asistencia del día (mandador/capataz).

Cubre: GET sin día abierto (todos SIN_MARCAR), marcar cada estado, corregir
una marca (reemplaza línea y eventos propios sin tocar los del capataz), y que
las marcas alimentan la consolidación formal de 3 fuentes.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.nomina.asistencia_dia import (
    ensure_work_day,
    hoy_local,
    marcar_asistencia,
    personal_del_dia,
)
from apps.kernels.nomina.models import (
    FieldRollCallLine,
    FieldRollCallLineStatus,
    FieldWorkerEvent,
    FieldWorkerEventType,
)
from apps.kernels.nomina.services import consolidate_field_attendance, record_worker_event
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _scope():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}")
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B{t}")
    return company, branch


def _actor():
    u = f"mand_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=u, email=f"{u}@test.local", password="x")


def _request(actor, company, branch=None):
    return SimpleNamespace(
        user=actor, META={}, company=company, branch=branch, _request=None,
        ctx=None, request_id=f"req_{uuid.uuid4().hex[:8]}", path="", method="POST",
    )


def _emp(company, name="Trabajador"):
    return Employee.objects.create(
        company=company, employee_code=f"E-{uuid.uuid4().hex[:6]}",
        first_name=name, last_name="Campo", is_active=True,
    )


@pytest.mark.django_db
def test_personal_sin_dia_abierto_sale_sin_marcar():
    company, branch = _scope()
    _emp(company, "Juan")
    _emp(company, "Ana")
    req = _request(_actor(), company, branch)

    results = personal_del_dia(request=req, work_day=None)
    assert len(results) == 2
    assert all(r["estado"] == "SIN_MARCAR" for r in results)


@pytest.mark.django_db
def test_marcar_estados_y_corregir():
    company, branch = _scope()
    actor = _actor()
    req = _request(actor, company, branch)
    juan = _emp(company, "Juan")
    ana = _emp(company, "Ana")

    wd = ensure_work_day(request=req, actor=actor, work_date=hoy_local())
    # ensure es idempotente
    assert ensure_work_day(request=req, actor=actor, work_date=hoy_local()).id == wd.id

    marcar_asistencia(request=req, actor=actor, work_day=wd, employee=juan, estado="PRESENTE")
    marcar_asistencia(request=req, actor=actor, work_day=wd, employee=ana, estado="ENFERMO")

    by_emp = {r["employee_id"]: r["estado"] for r in personal_del_dia(request=req, work_day=wd)}
    assert by_emp[juan.id] == "PRESENTE"
    assert by_emp[ana.id] == "ENFERMO"

    # Efectos formales: línea de lista + evento SICK
    ana_line = FieldRollCallLine.objects.get(rollcall__work_day=wd, employee=ana)
    assert ana_line.status == FieldRollCallLineStatus.ABSENT
    assert ana_line.absence_reason == "SICK"
    assert FieldWorkerEvent.objects.filter(
        work_day=wd, employee=ana, event_type=FieldWorkerEventType.SICK
    ).count() == 1

    # Corrección: Ana en realidad trabajó medio día → reemplaza evento y línea
    marcar_asistencia(request=req, actor=actor, work_day=wd, employee=ana, estado="MEDIO_DIA")
    ana_line.refresh_from_db()
    assert ana_line.status == FieldRollCallLineStatus.PRESENT
    eventos = list(FieldWorkerEvent.objects.filter(work_day=wd, employee=ana))
    assert [e.event_type for e in eventos] == [FieldWorkerEventType.LEFT_EARLY]

    by_emp = {r["employee_id"]: r["estado"] for r in personal_del_dia(request=req, work_day=wd)}
    assert by_emp[ana.id] == "MEDIO_DIA"


@pytest.mark.django_db
def test_correccion_no_borra_eventos_del_capataz():
    company, branch = _scope()
    actor = _actor()
    req = _request(actor, company, branch)
    juan = _emp(company, "Juan")
    wd = ensure_work_day(request=req, actor=actor, work_date=hoy_local())

    # El capataz registró un traslado por SU canal (sin source de la app)
    record_worker_event(
        request=req, actor=actor, work_day=wd, employee=juan,
        event_type=FieldWorkerEventType.TRANSFERRED, details="Pasó al lote 4",
    )
    marcar_asistencia(request=req, actor=actor, work_day=wd, employee=juan, estado="ACCIDENTADO")
    marcar_asistencia(request=req, actor=actor, work_day=wd, employee=juan, estado="PRESENTE")

    tipos = set(FieldWorkerEvent.objects.filter(work_day=wd, employee=juan).values_list("event_type", flat=True))
    assert FieldWorkerEventType.TRANSFERRED in tipos  # intacto
    assert FieldWorkerEventType.ACCIDENT not in tipos  # el de la app sí se reemplazó


@pytest.mark.django_db
def test_marcas_alimentan_la_consolidacion():
    company, branch = _scope()
    actor = _actor()
    req = _request(actor, company, branch)
    juan = _emp(company, "Juan")
    wd = ensure_work_day(request=req, actor=actor, work_date=hoy_local())
    marcar_asistencia(request=req, actor=actor, work_day=wd, employee=juan, estado="ENFERMO")

    [cons] = consolidate_field_attendance(request=req, actor=actor, work_day=wd)
    assert cons.employee_id == juan.id
    assert cons.primary_event_type == FieldWorkerEventType.SICK
    assert cons.day_value == 0


def _client(*, company, branch, perms):
    u = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", email=f"e_{uuid.uuid4().hex[:6]}@t.com", password="x")
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


@pytest.mark.django_db
def test_api_get_y_marcar():
    company, branch = _scope()
    juan = _emp(company, "Juan")
    client = _client(company=company, branch=branch, perms=["nomina.field.capture", "nomina.field.read"])

    resp = client.get("/api/nomina/asistencia/hoy/")
    assert resp.status_code == 200, resp.data
    assert resp.data["work_day_id"] is None
    assert resp.data["marcados"] == 0
    assert resp.data["results"][0]["estado"] == "SIN_MARCAR"

    marcado = client.post(
        "/api/nomina/asistencia/hoy/", {"employee_id": juan.id, "estado": "ACCIDENTADO"}, format="json"
    )
    assert marcado.status_code == 200, marcado.data

    resp = client.get("/api/nomina/asistencia/hoy/")
    assert resp.data["work_day_id"] is not None
    assert resp.data["marcados"] == 1
    assert resp.data["results"][0]["estado"] == "ACCIDENTADO"

    # Estado inventado → 400
    bad = client.post(
        "/api/nomina/asistencia/hoy/", {"employee_id": juan.id, "estado": "FANTASMA"}, format="json"
    )
    assert bad.status_code == 400

    # Sin permiso de captura → 403
    sin_perm = _client(company=company, branch=branch, perms=["hr.employee.read"])
    resp = sin_perm.get("/api/nomina/asistencia/hoy/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_supervisor_ve_pero_no_marca():
    """SoD: nomina.field.read entra a la pantalla; marcar exige nomina.field.capture."""
    company, branch = _scope()
    juan = _emp(company, "Juan")
    supervisor = _client(company=company, branch=branch, perms=["nomina.field.read"])

    resp = supervisor.get("/api/nomina/asistencia/hoy/")
    assert resp.status_code == 200, resp.data

    bloqueado = supervisor.post(
        "/api/nomina/asistencia/hoy/", {"employee_id": juan.id, "estado": "PRESENTE"}, format="json"
    )
    assert bloqueado.status_code == 403


@pytest.mark.django_db
def test_medio_dia_paga_medio_dia():
    """REGLA: "Trabajó medio día" marcado en la pantalla consolida day_value 0.5
    (antes quedaba como LEFT_EARLY sin valor y pagaba el día completo)."""
    from decimal import Decimal

    company, branch = _scope()
    actor = _actor()
    req = _request(actor, company, branch)
    juan = _emp(company, "Medio")
    maria = _emp(company, "Completo")
    wd = ensure_work_day(request=req, actor=actor, work_date=hoy_local())
    marcar_asistencia(request=req, actor=actor, work_day=wd, employee=juan, estado="MEDIO_DIA")
    marcar_asistencia(request=req, actor=actor, work_day=wd, employee=maria, estado="PRESENTE")

    consolidaciones = {
        c.employee_id: c for c in consolidate_field_attendance(request=req, actor=actor, work_day=wd)
    }
    assert consolidaciones[juan.id].day_value == Decimal("0.50")
    assert consolidaciones[maria.id].day_value == Decimal("1.00")


@pytest.mark.django_db
def test_accidentado_pone_el_dia():
    """REGLA del dueño: el accidente fue EN el trabajo → el día se paga (1.00)."""
    from decimal import Decimal

    company, branch = _scope()
    actor = _actor()
    req = _request(actor, company, branch)
    emp = _emp(company, "Accidentado")
    wd = ensure_work_day(request=req, actor=actor, work_date=hoy_local())
    marcar_asistencia(request=req, actor=actor, work_day=wd, employee=emp, estado="ACCIDENTADO")

    [cons] = consolidate_field_attendance(request=req, actor=actor, work_day=wd)
    assert cons.primary_event_type == FieldWorkerEventType.ACCIDENT
    assert cons.day_value == Decimal("1.00")


@pytest.mark.django_db
def test_enfermo_paga_solo_con_constancia():
    """REGLA del dueño: enfermo se paga SOLO con constancia médica certificada."""
    from decimal import Decimal

    company, branch = _scope()
    actor = _actor()
    req = _request(actor, company, branch)
    con_constancia = _emp(company, "ConConstancia")
    sin_constancia = _emp(company, "SinConstancia")
    wd = ensure_work_day(request=req, actor=actor, work_date=hoy_local())
    marcar_asistencia(
        request=req, actor=actor, work_day=wd, employee=con_constancia,
        estado="ENFERMO", constancia_medica=True,
    )
    marcar_asistencia(
        request=req, actor=actor, work_day=wd, employee=sin_constancia, estado="ENFERMO",
    )

    consolidaciones = {
        c.employee_id: c for c in consolidate_field_attendance(request=req, actor=actor, work_day=wd)
    }
    assert consolidaciones[con_constancia.id].day_value == Decimal("1.00")
    assert consolidaciones[sin_constancia.id].day_value == Decimal("0.00")
