from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.nomina.field.models_field import CrewMembership, FieldCaptureReport, FieldCaptureEvent
from apps.kernels.nomina.field.services_field import (
    add_crew_member,
    approve_report,
    build_attendance_report,
    create_crew,
    record_worker_event,
    request_report_approval,
    upsert_crew_report,
    upsert_work_day,
)
from apps.kernels.nomina.models import AttendanceReport, AttendanceSource, AttendanceStatus, PayrollPeriod, PeriodType
from apps.modulos.audit.models import AuditEvent
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import ApprovalRequest, OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.rbac.seed_v01 import seed_rbac_v01

User = get_user_model()


def _mk_scope(suffix: str = ""):
    s = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _actor(prefix: str = "field"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _request(actor, *, company=None, branch=None):
    return SimpleNamespace(
        user=actor,
        META={},
        company=company,
        branch=branch,
        _request=None,
        ctx=None,
        request_id="",
        path="/api/nomina/field/test/",
        method="POST",
    )


def _mk_period(company):
    return PayrollPeriod.objects.create(
        company=company,
        year=2026,
        month=1,
        period_type=PeriodType.FIRST_HALF,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 15),
        working_days=15,
    )


def _mk_employee(company, *, first_name="Juan", last_name="Perez"):
    return Employee.objects.create(
        company=company,
        employee_code=f"E-{uuid.uuid4().hex[:6]}",
        first_name=first_name,
        last_name=last_name,
    )


def _grant(user, *, company, branch, perm_codes):
    UserMembership.objects.get_or_create(user=user, org_unit=company, defaults={"is_active": True})
    UserMembership.objects.get_or_create(user=user, org_unit=branch, defaults={"is_active": True})
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)
    return role


def _client(user, *, company, branch, perm_codes):
    _grant(user, company=company, branch=branch, perm_codes=perm_codes)
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _field_report(company, branch, actor):
    period = _mk_period(company)
    crew = create_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        company=company,
        branch=branch,
        name=f"Cuadrilla {uuid.uuid4().hex[:6]}",
    )
    work_day = upsert_work_day(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        period=period,
        crew=crew,
        work_date=date(2026, 1, 2),
    )
    report = upsert_crew_report(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        observations="Reporte de campo",
    )
    return period, crew, report


@pytest.mark.django_db
def test_field_work_day_and_crew_report_are_idempotent_by_crew_date():
    company, branch = _mk_scope()
    actor = _actor()
    period = _mk_period(company)
    crew = create_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        company=company,
        branch=branch,
        name="Corte Cafe",
    )

    day_1 = upsert_work_day(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        period=period,
        crew=crew,
        work_date=date(2026, 1, 3),
    )
    day_2 = upsert_work_day(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        period=period,
        crew=crew,
        work_date=date(2026, 1, 3),
    )
    report_1 = upsert_crew_report(request=_request(actor, company=company, branch=branch), actor=actor, work_day=day_1)
    report_2 = upsert_crew_report(request=_request(actor, company=company, branch=branch), actor=actor, work_day=day_2)

    assert day_1.id == day_2.id
    assert report_1.id == report_2.id
    assert FieldCaptureReport.objects.count() == 1


@pytest.mark.django_db
def test_field_worker_event_allows_eventual_by_cedula():
    company, branch = _mk_scope()
    actor = _actor()
    _period, _crew, report = _field_report(company, branch, actor)

    event = record_worker_event(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        report=report,
        event_type=FieldCaptureEvent.EventType.PRESENT,
        cedula="001-010101-0001A",
        employee_name="Eventual Uno",
    )

    assert event.employee_id is None
    assert event.cedula == "001-010101-0001A"
    assert AuditEvent.objects.filter(event_type="FIELD_WORKER_EVENT_RECORDED", subject_id=str(event.id)).exists()


@pytest.mark.django_db
def test_field_worker_transfer_moves_membership_between_crews():
    company, branch = _mk_scope()
    actor = _actor()
    employee = _mk_employee(company)
    _period, crew_from, report = _field_report(company, branch, actor)
    crew_to = create_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        company=company,
        branch=branch,
        name=f"Cuadrilla destino {uuid.uuid4().hex[:6]}",
    )
    add_crew_member(crew=crew_from, employee=employee, active_from=date(2026, 1, 1))

    transfer = record_worker_event(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        report=report,
        event_type=FieldCaptureEvent.EventType.TRANSFER,
        employee=employee,
        to_crew=crew_to,
        notes="Cambio de tajo",
    )

    assert transfer.from_crew_id == crew_from.id
    assert transfer.to_crew_id == crew_to.id
    assert not CrewMembership.objects.get(crew=crew_from, employee=employee).is_active
    assert CrewMembership.objects.get(crew=crew_to, employee=employee).is_active


@pytest.mark.django_db
def test_field_report_sod_self_approval_forbidden_and_checker_executes():
    company, branch = _mk_scope()
    maker = _actor("maker")
    checker = _actor("checker")
    _period, _crew, report = _field_report(company, branch, maker)
    maker_client = _client(
        maker,
        company=company,
        branch=branch,
        perm_codes=["nomina.attendance.review", "nomina.attendance.approve"],
    )
    checker_client = _client(
        checker,
        company=company,
        branch=branch,
        perm_codes=["nomina.attendance.approve"],
    )

    request_resp = maker_client.post(f"/api/nomina/field/reports/{report.id}/approve/request/", {}, format="json")
    assert request_resp.status_code == 201, request_resp.data
    approval_request_id = request_resp.data["approval_request_id"]

    self_resp = maker_client.post(
        f"/api/nomina/field/reports/{report.id}/approve/",
        {"approval_request_id": approval_request_id},
        format="json",
    )
    assert self_resp.status_code == 403

    ok_resp = checker_client.post(
        f"/api/nomina/field/reports/{report.id}/approve/",
        {"approval_request_id": approval_request_id, "note": "OK"},
        format="json",
    )
    assert ok_resp.status_code == 200, ok_resp.data
    report.refresh_from_db()
    approval = ApprovalRequest.objects.get(request_id=approval_request_id)
    assert report.status == FieldCaptureReport.Status.APPROVED
    assert approval.status == ApprovalRequest.Status.EXECUTED


@pytest.mark.django_db
def test_build_attendance_report_sums_approved_field_events():
    company, branch = _mk_scope()
    maker = _actor("maker")
    checker = _actor("checker")
    employee = _mk_employee(company, first_name="Ana", last_name="Rivas")
    _grant(checker, company=company, branch=branch, perm_codes=["nomina.attendance.approve"])
    _period, _crew, report = _field_report(company, branch, maker)
    record_worker_event(
        request=_request(maker, company=company, branch=branch),
        actor=maker,
        report=report,
        event_type=FieldCaptureEvent.EventType.PRESENT,
        employee=employee,
        day_value=Decimal("1.00"),
    )
    record_worker_event(
        request=_request(maker, company=company, branch=branch),
        actor=maker,
        report=report,
        event_type=FieldCaptureEvent.EventType.SUBSIDY,
        employee=employee,
        day_value=Decimal("1.00"),
    )
    approval = request_report_approval(
        request=_request(maker, company=company, branch=branch),
        actor=maker,
        report=report,
    )
    approve_report(
        request=_request(checker, company=company, branch=branch),
        approver=checker,
        report=report,
        approval=approval,
    )

    reports = build_attendance_report(
        request=_request(maker, company=company, branch=branch),
        actor=maker,
        report=report,
    )

    assert len(reports) == 1
    attendance = AttendanceReport.objects.get(id=reports[0].id)
    assert attendance.source == AttendanceSource.SUPERVISOR_APP
    assert attendance.status == AttendanceStatus.APPROVED
    assert attendance.employee_id == employee.id
    assert attendance.days_worked == Decimal("1.00")
    assert attendance.days_subsidy == Decimal("1.00")


@pytest.mark.django_db
def test_field_crew_endpoint_requires_rbac_permission():
    company, branch = _mk_scope()
    denied_client = _client(_actor("denied"), company=company, branch=branch, perm_codes=[])
    allowed_client = _client(_actor("allowed"), company=company, branch=branch, perm_codes=["nomina.field.manage"])

    denied = denied_client.post(
        "/api/nomina/field/crews/",
        {"branch_id": branch.id, "name": "Cuadrilla sin permiso"},
        format="json",
    )
    assert denied.status_code == 403

    allowed = allowed_client.post(
        "/api/nomina/field/crews/",
        {"branch_id": branch.id, "name": f"Cuadrilla {uuid.uuid4().hex[:6]}"},
        format="json",
    )
    assert allowed.status_code == 201, allowed.data


@pytest.mark.django_db
def test_field_capture_endpoints_roundtrip_to_attendance_report():
    company, branch = _mk_scope()
    maker = _actor("maker")
    checker = _actor("checker")
    foreman = _mk_employee(company, first_name="Foreman", last_name="Uno")
    worker = _mk_employee(company, first_name="Luis", last_name="Mora")
    period = _mk_period(company)
    maker_client = _client(
        maker,
        company=company,
        branch=branch,
        perm_codes=[
            "nomina.field.manage",
            "nomina.field.capture",
            "nomina.field.read",
            "nomina.attendance.review",
            "nomina.attendance.build",
        ],
    )
    checker_client = _client(
        checker,
        company=company,
        branch=branch,
        perm_codes=["nomina.attendance.approve"],
    )

    crew_resp = maker_client.post(
        "/api/nomina/field/crews/",
        {
            "branch_id": branch.id,
            "name": f"Cuadrilla API {uuid.uuid4().hex[:6]}",
            "code": "API-1",
            "foreman_id": foreman.id,
        },
        format="json",
    )
    assert crew_resp.status_code == 201, crew_resp.data
    crew_id = crew_resp.data["id"]

    crew_to_resp = maker_client.post(
        "/api/nomina/field/crews/",
        {"branch_id": branch.id, "name": f"Cuadrilla API destino {uuid.uuid4().hex[:6]}"},
        format="json",
    )
    assert crew_to_resp.status_code == 201, crew_to_resp.data

    crew_list = maker_client.get(f"/api/nomina/field/crews/?branch_id={branch.id}")
    assert crew_list.status_code == 200, crew_list.data
    assert crew_list.data["count"] >= 2

    work_day_resp = maker_client.post(
        "/api/nomina/field/capture/work-days/",
        {
            "period_id": period.id,
            "crew_id": crew_id,
            "work_date": "2026-01-04",
            "notes": "captura api",
            "observations": "reporte api",
        },
        format="json",
    )
    assert work_day_resp.status_code == 201, work_day_resp.data
    report_id = work_day_resp.data["report"]["id"]

    reports_list = maker_client.get(
        f"/api/nomina/field/capture/work-days/?period_id={period.id}&crew_id={crew_id}"
    )
    assert reports_list.status_code == 200, reports_list.data
    assert reports_list.data["count"] == 1

    present_resp = maker_client.post(
        f"/api/nomina/field/reports/{report_id}/events/",
        {
            "employee_id": worker.id,
            "event_type": FieldCaptureEvent.EventType.PRESENT,
            "day_value": "1.00",
            "overtime_hours": "2.50",
            "sunday_worked_days": 1,
            "notes": "presente api",
        },
        format="json",
    )
    assert present_resp.status_code == 201, present_resp.data

    transfer_resp = maker_client.post(
        f"/api/nomina/field/reports/{report_id}/events/",
        {
            "employee_id": worker.id,
            "event_type": FieldCaptureEvent.EventType.TRANSFER,
            "to_crew_id": crew_to_resp.data["id"],
            "day_value": "1.00",
            "notes": "traslado api",
        },
        format="json",
    )
    assert transfer_resp.status_code == 201, transfer_resp.data

    events_list = maker_client.get(f"/api/nomina/field/reports/{report_id}/events/")
    assert events_list.status_code == 200, events_list.data
    assert events_list.data["count"] == 2

    request_resp = maker_client.post(
        f"/api/nomina/field/reports/{report_id}/approve/request/",
        {"reason": "cierre api"},
        format="json",
    )
    assert request_resp.status_code == 201, request_resp.data

    approve_resp = checker_client.post(
        f"/api/nomina/field/reports/{report_id}/approve/",
        {"approval_request_id": request_resp.data["approval_request_id"], "note": "aprobado api"},
        format="json",
    )
    assert approve_resp.status_code == 200, approve_resp.data

    build_resp = maker_client.post(f"/api/nomina/field/reports/{report_id}/build-attendance/", {}, format="json")
    assert build_resp.status_code == 200, build_resp.data
    assert build_resp.data["count"] == 1
    row = build_resp.data["results"][0]
    assert row["employee"] == worker.id
    assert row["days_worked"] == "1.00"
    assert row["days_transferred"] == "1.00"
    assert row["overtime_hours"] == "2.50"


@pytest.mark.django_db
def test_seed_rbac_includes_nomina_field_permissions_and_payroll_manager():
    seed_rbac_v01()
    again = seed_rbac_v01()
    assert again.roles_created == 0
    assert again.perms_created == 0
    assert again.roleperms_created == 0

    role = Role.objects.get(name="payroll_manager")
    codes = set(RolePermission.objects.filter(role=role).values_list("permission__code", flat=True))
    assert "nomina.field.capture" in codes
    assert "nomina.attendance.approve" in codes
    assert Permission.objects.filter(code="nomina.entry.create", is_active=True).exists()
