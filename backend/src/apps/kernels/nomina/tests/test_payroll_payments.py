"""Tests de pagos del neto + cierre de período (U5)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.nomina.models import (
    PayrollEntry,
    PayrollPayment,
    PayrollPaymentMethod,
    PayrollPeriod,
    PayrollSheet,
    PeriodStatus,
    PeriodType,
    SalaryType,
)
from apps.kernels.nomina.payroll_payments import PayrollPaymentError, close_period, register_payroll_payment
from apps.kernels.nomina.services import compute_entry, create_default_nicaragua_config
from apps.modulos.audit.models import AuditEvent
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


def _approved_period(company, branch, actor, *, n=2, status=PeriodStatus.APPROVED):
    create_default_nicaragua_config(request=_req(actor, company=company), actor=actor, company=company, fiscal_year=2026)
    period = PayrollPeriod.objects.create(
        company=company, year=2026, month=6, period_type=PeriodType.SECOND_HALF,
        start_date=date(2026, 6, 16), end_date=date(2026, 6, 30), working_days=15, status=status,
    )
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="FINCA", has_inss=True)
    entries = []
    for i in range(n):
        emp = Employee.objects.create(company=company, employee_code=f"E{i}", first_name=f"T{i}", last_name="X", is_active=True)
        entry = PayrollEntry.objects.create(
            sheet=sheet, employee=emp, full_name=f"T{i} X", has_inss=True,
            salary_type=SalaryType.MONTHLY, base_salary_nio=Decimal("12000.00"),
            days_in_period=15, days_worked=Decimal("15.00"),
        )
        compute_entry(entry=entry)
        entries.append(entry)
    return period, entries


def _pay(actor, company, entry, amount):
    return register_payroll_payment(
        request=_req(actor, company=company), actor=actor, entry=entry,
        payment_method=PayrollPaymentMethod.CASH, amount=amount, payment_date=date(2026, 7, 1),
    )


@pytest.mark.django_db
def test_register_payment_creates_record_and_audits():
    company, branch = _scope()
    actor = _actor()
    period, entries = _approved_period(company, branch, actor, n=1)
    entry = entries[0]

    payment = _pay(actor, company, entry, entry.net_to_pay)

    assert PayrollPayment.objects.filter(entry=entry).count() == 1
    assert payment.amount == entry.net_to_pay
    assert AuditEvent.objects.filter(event_type="NOMINA_PAYMENT_REGISTERED", subject_id=str(payment.id)).exists()


@pytest.mark.django_db
def test_payment_cannot_exceed_remaining_net():
    """NM-05: el pago no puede exceder el neto restante (anti-sobrepago)."""
    company, branch = _scope()
    actor = _actor()
    period, entries = _approved_period(company, branch, actor, n=1)
    entry = entries[0]

    # Pago completo OK.
    _pay(actor, company, entry, entry.net_to_pay)
    # Un segundo pago (cualquier monto) excede el neto restante (0) → rechazado.
    with pytest.raises(PayrollPaymentError, match="excede el neto restante"):
        _pay(actor, company, entry, Decimal("0.01"))


@pytest.mark.django_db
def test_payment_over_net_in_single_shot_rejected():
    """NM-05: un único pago mayor al neto se rechaza."""
    company, branch = _scope()
    actor = _actor()
    period, entries = _approved_period(company, branch, actor, n=1)
    entry = entries[0]
    with pytest.raises(PayrollPaymentError, match="excede el neto restante"):
        _pay(actor, company, entry, entry.net_to_pay + Decimal("1000.00"))


@pytest.mark.django_db
def test_period_marks_paid_when_all_entries_covered():
    company, branch = _scope()
    actor = _actor()
    period, entries = _approved_period(company, branch, actor, n=2)

    _pay(actor, company, entries[0], entries[0].net_to_pay)
    period.refresh_from_db()
    assert period.status == PeriodStatus.APPROVED  # aún falta una línea

    _pay(actor, company, entries[1], entries[1].net_to_pay)
    period.refresh_from_db()
    assert period.status == PeriodStatus.PAID
    assert AuditEvent.objects.filter(event_type="NOMINA_PERIOD_PAID", subject_id=str(period.id)).exists()


@pytest.mark.django_db
def test_register_payment_rejects_non_approved_period():
    company, branch = _scope()
    actor = _actor()
    period, entries = _approved_period(company, branch, actor, n=1, status=PeriodStatus.DRAFT)
    with pytest.raises(PayrollPaymentError):
        _pay(actor, company, entries[0], entries[0].net_to_pay)


@pytest.mark.django_db
def test_close_period_requires_paid_then_closes():
    company, branch = _scope()
    actor = _actor()
    period, entries = _approved_period(company, branch, actor, n=1)

    # No se puede cerrar APPROVED
    with pytest.raises(PayrollPaymentError):
        close_period(request=_req(actor, company=company), actor=actor, period=period)

    _pay(actor, company, entries[0], entries[0].net_to_pay)
    period.refresh_from_db()
    assert period.status == PeriodStatus.PAID

    close_period(request=_req(actor, company=company), actor=actor, period=period)
    period.refresh_from_db()
    assert period.status == PeriodStatus.CLOSED
    assert AuditEvent.objects.filter(event_type="NOMINA_PERIOD_CLOSED", subject_id=str(period.id)).exists()
