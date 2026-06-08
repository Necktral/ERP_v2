from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.nomina.models import (
    FieldAttendanceConsolidation,
    FieldAttendanceConsolidationStatus,
    FieldCrewReportLine,
    FieldRollCall,
    FieldWorkerEvent,
    FieldWorkerEventType,
    FieldWorkDayStatus,
    PayrollEntry,
    PayrollPeriod,
    PeriodType,
)
from apps.kernels.nomina.services import (
    FieldAttendanceError,
    approve_field_attendance,
    consolidate_field_attendance,
    create_field_crew,
    open_field_work_day,
    record_worker_event,
    submit_crew_report,
    submit_rollcall,
    transfer_worker,
)
from apps.modulos.audit.models import AuditEvent
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _mk_scope(suffix: str = ""):
    tag = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{tag}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{tag}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{tag}", parent=company)
    return company, branch


def _actor(prefix: str = "field"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="x")


def _request(actor, *, company=None, branch=None):
    return SimpleNamespace(
        user=actor,
        META={},
        company=company,
        branch=branch,
        _request=None,
        ctx=None,
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        path="",
        method="POST",
    )


def _period(company, *, period_type=PeriodType.CATORCENA):
    return PayrollPeriod.objects.create(
        company=company,
        year=2026,
        month=6,
        period_type=period_type,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 14),
        working_days=14,
    )


def _employee(company, first_name="Trabajador", *, active=True):
    return Employee.objects.create(
        company=company,
        employee_code=f"E-{uuid.uuid4().hex[:6]}",
        first_name=first_name,
        last_name="Campo",
        is_active=active,
    )


def _open_day(company, branch, actor, *, work_date=date(2026, 6, 5), period=None):
    period = period or _period(company)
    return open_field_work_day(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        company=company,
        branch=branch,
        payroll_period=period,
        work_date=work_date,
    )


def _audit(event_type, subject_id=None):
    qs = AuditEvent.objects.filter(event_type=event_type)
    if subject_id is not None:
        qs = qs.filter(subject_id=str(subject_id))
    return qs


@pytest.mark.django_db
def test_open_field_work_day_creates_audited_catorcena_day_and_blocks_duplicate():
    company, branch = _mk_scope()
    actor = _actor()
    period = _period(company, period_type=PeriodType.CATORCENA)

    work_day = _open_day(company, branch, actor, period=period)

    assert work_day.status == FieldWorkDayStatus.OPEN
    assert work_day.payroll_period == period
    assert period.period_type == PeriodType.CATORCENA
    assert _audit("FIELD_WORK_DAY_OPENED", work_day.id).exists()

    with pytest.raises(FieldAttendanceError) as exc:
        _open_day(company, branch, actor, period=period)
    assert exc.value.code == "duplicate_work_day"


@pytest.mark.django_db
def test_open_field_work_day_rejects_branch_from_another_company():
    company, _ = _mk_scope("a")
    _, foreign_branch = _mk_scope("b")
    actor = _actor()

    with pytest.raises(FieldAttendanceError) as exc:
        open_field_work_day(
            request=_request(actor, company=company, branch=foreign_branch),
            actor=actor,
            company=company,
            branch=foreign_branch,
            work_date=date(2026, 6, 5),
        )

    assert exc.value.code == "invalid_scope"


@pytest.mark.django_db
def test_submit_rollcall_rejects_employee_from_other_company():
    company, branch = _mk_scope("a")
    foreign_company, _ = _mk_scope("b")
    actor = _actor()
    work_day = _open_day(company, branch, actor)
    foreign_employee = _employee(foreign_company)

    with pytest.raises(FieldAttendanceError) as exc:
        submit_rollcall(
            request=_request(actor, company=company, branch=branch),
            actor=actor,
            work_day=work_day,
            lines=[{"employee": foreign_employee, "status": "PRESENT"}],
        )

    assert exc.value.code == "employee_out_of_scope"
    assert not FieldRollCall.objects.filter(work_day=work_day).exists()


@pytest.mark.django_db
def test_rollcall_crew_and_present_report_use_hr_employees_and_audit():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Juan")
    supervisor = _employee(company, "Capataz")
    work_day = _open_day(company, branch, actor)

    rollcall = submit_rollcall(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        lines=[{"employee": worker, "status": "PRESENT"}],
    )
    crew = create_field_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        name="Cuadrilla A",
        supervisor_employee=supervisor,
    )
    report = submit_crew_report(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        crew=crew,
        labor_code="CORTE",
        labor_name="Corte de cafe",
        zone_label="Lote 1",
        lines=[{"employee": worker, "event_type": FieldWorkerEventType.PRESENT}],
    )

    assert rollcall.lines.get().employee == worker
    assert crew.supervisor_employee == supervisor
    line = FieldCrewReportLine.objects.get(report=report, employee=worker)
    assert line.day_value == Decimal("1.00")
    assert _audit("FIELD_ROLLCALL_SUBMITTED", rollcall.id).exists()
    assert _audit("FIELD_CREW_CREATED", crew.id).exists()
    assert _audit("FIELD_CREW_REPORT_SUBMITTED", report.id).exists()


@pytest.mark.django_db
def test_worker_event_requires_details_and_records_sick_and_accident():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Maria")
    work_day = _open_day(company, branch, actor)

    with pytest.raises(FieldAttendanceError) as exc:
        record_worker_event(
            request=_request(actor, company=company, branch=branch),
            actor=actor,
            work_day=work_day,
            employee=worker,
            event_type=FieldWorkerEventType.SICK,
        )
    assert exc.value.code == "missing_required_detail"

    sick = record_worker_event(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        employee=worker,
        event_type=FieldWorkerEventType.SICK,
        details="Fiebre reportada por capataz",
    )
    accident = record_worker_event(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        employee=worker,
        event_type=FieldWorkerEventType.ACCIDENT,
        details="Golpe leve en mano derecha",
    )

    assert FieldWorkerEvent.objects.filter(id__in=[sick.id, accident.id]).count() == 2
    assert _audit("FIELD_WORKER_EVENT_RECORDED", sick.id).exists()
    assert _audit("FIELD_WORKER_EVENT_RECORDED", accident.id).exists()


@pytest.mark.django_db
def test_transfer_between_crews_warns_but_does_not_duplicate_jornal():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Luis")
    supervisor_a = _employee(company, "CapatazA")
    supervisor_b = _employee(company, "CapatazB")
    work_day = _open_day(company, branch, actor)
    submit_rollcall(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        lines=[{"employee": worker, "status": "PRESENT"}],
    )
    crew_a = create_field_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        name="Origen",
        supervisor_employee=supervisor_a,
    )
    crew_b = create_field_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        name="Destino",
        supervisor_employee=supervisor_b,
    )
    submit_crew_report(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        crew=crew_a,
        lines=[{"employee": worker, "event_type": FieldWorkerEventType.PRESENT}],
    )
    submit_crew_report(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        crew=crew_b,
        lines=[{"employee": worker, "event_type": FieldWorkerEventType.PRESENT}],
    )
    transfer = transfer_worker(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        employee=worker,
        from_crew=crew_a,
        to_crew=crew_b,
        reason="Cambio de zona por necesidad operativa",
    )

    consolidations = consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
    )

    assert _audit("FIELD_WORKER_TRANSFERRED", transfer.id).exists()
    assert len(consolidations) == 1
    consolidation = consolidations[0]
    assert consolidation.status == FieldAttendanceConsolidationStatus.WARNING
    assert consolidation.day_value == Decimal("1.00")
    assert consolidation.conflict_codes == ["TRANSFERRED_BETWEEN_CREWS"]


@pytest.mark.django_db
def test_consolidation_blocks_employee_in_two_crews_without_transfer():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Ana")
    supervisor_a = _employee(company, "SupA")
    supervisor_b = _employee(company, "SupB")
    work_day = _open_day(company, branch, actor)
    crew_a = create_field_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        name="A",
        supervisor_employee=supervisor_a,
    )
    crew_b = create_field_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        name="B",
        supervisor_employee=supervisor_b,
    )
    submit_crew_report(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        crew=crew_a,
        lines=[{"employee": worker, "event_type": FieldWorkerEventType.PRESENT}],
    )
    submit_crew_report(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        crew=crew_b,
        lines=[{"employee": worker, "event_type": FieldWorkerEventType.PRESENT}],
    )

    consolidation = consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
    )[0]

    assert consolidation.status == FieldAttendanceConsolidationStatus.BLOCKED
    assert consolidation.conflict_codes == ["DUPLICATE_CREW_WITHOUT_TRANSFER"]
    assert _audit("FIELD_ATTENDANCE_CONFLICT_RAISED", consolidation.id).exists()


@pytest.mark.django_db
def test_consolidation_detects_absent_rollcall_present_crew_conflict():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Carlos")
    supervisor = _employee(company, "Sup")
    work_day = _open_day(company, branch, actor)
    submit_rollcall(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        lines=[{"employee": worker, "status": "ABSENT", "absence_reason": "No llego"}],
    )
    crew = create_field_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        name="Campo",
        supervisor_employee=supervisor,
    )
    submit_crew_report(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        crew=crew,
        lines=[{"employee": worker, "event_type": FieldWorkerEventType.PRESENT}],
    )

    consolidation = consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
    )[0]

    assert consolidation.status == FieldAttendanceConsolidationStatus.CONFLICT
    assert consolidation.conflict_codes == ["ROLLCALL_ABSENT_CREW_PRESENT"]


@pytest.mark.django_db
def test_approve_field_attendance_blocks_conflicts_and_does_not_generate_payroll_entries():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Pedro")
    supervisor = _employee(company, "Sup")
    work_day = _open_day(company, branch, actor)
    submit_rollcall(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        lines=[{"employee": worker, "status": "ABSENT"}],
    )
    crew = create_field_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        name="Campo",
        supervisor_employee=supervisor,
    )
    submit_crew_report(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        crew=crew,
        lines=[{"employee": worker, "event_type": FieldWorkerEventType.PRESENT}],
    )
    consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
    )

    with pytest.raises(FieldAttendanceError) as exc:
        approve_field_attendance(
            request=_request(actor, company=company, branch=branch),
            actor=actor,
            work_day=work_day,
        )

    assert exc.value.code == "blocked_conflict"
    assert PayrollEntry.objects.count() == 0


@pytest.mark.django_db
def test_approve_field_attendance_marks_clean_consolidation_and_audits():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Rosa")
    supervisor = _employee(company, "Sup")
    work_day = _open_day(company, branch, actor)
    submit_rollcall(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        lines=[{"employee": worker, "status": "PRESENT"}],
    )
    crew = create_field_crew(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
        name="Campo",
        supervisor_employee=supervisor,
    )
    submit_crew_report(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        crew=crew,
        lines=[{"employee": worker, "event_type": FieldWorkerEventType.PRESENT}],
    )
    consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
    )

    approved = approve_field_attendance(
        request=_request(actor, company=company, branch=branch),
        actor=actor,
        work_day=work_day,
    )

    assert [item.status for item in approved] == [FieldAttendanceConsolidationStatus.APPROVED]
    work_day.refresh_from_db()
    assert work_day.status == FieldWorkDayStatus.APPROVED
    assert FieldAttendanceConsolidation.objects.get(work_day=work_day, employee=worker).approved_by == actor
    assert _audit("FIELD_ATTENDANCE_CONSOLIDATED", work_day.id).exists()
    assert _audit("FIELD_ATTENDANCE_APPROVED", work_day.id).exists()
