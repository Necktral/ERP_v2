"""Tests del abono de descuentos de planilla → portfolio (Capa 1 follow-up)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.nomina.models import PayrollEntry, PayrollLoanDeduction, PayrollPeriod, PayrollSheet, PeriodType
from apps.kernels.nomina.portfolio_link import register_payroll_loan_deduction
from apps.kernels.portfolio.models import ObligationStatus
from apps.kernels.portfolio.services import create_credit
from apps.modulos.audit.models import AuditEvent
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit
from apps.modulos.parties.models import Party

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


def _credit(company, actor, amount="1000.00"):
    lender = Party.objects.create(company=company, party_type=Party.PartyType.INTERNAL, display_name="Empresa")
    borrower = Party.objects.create(company=company, party_type=Party.PartyType.NATURAL, display_name="Empleado")
    return create_credit(
        company=company, credit_type="TERM_LOAN", lender_party=lender, borrower_party=borrower,
        approved_amount=Decimal(amount), currency="NIO", interest_rate=Decimal("0"),
        term_months=12, maturity_date=date(2027, 1, 1), created_by=actor,
    )


def _entry(company, branch):
    period = PayrollPeriod.objects.create(
        company=company, year=2026, month=6, period_type=PeriodType.SECOND_HALF,
        start_date=date(2026, 6, 16), end_date=date(2026, 6, 30), working_days=15,
    )
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="S", has_inss=True)
    emp = Employee.objects.create(company=company, employee_code="E1", first_name="T", last_name="X", is_active=True)
    return PayrollEntry.objects.create(
        sheet=sheet, employee=emp, full_name="T X", has_inss=True,
        base_salary_nio=Decimal("12000.00"), days_in_period=15, days_worked=Decimal("15.00"),
    )


@pytest.mark.django_db
def test_loan_deduction_applies_partial_abono_and_audits():
    company, branch = _scope()
    actor = _actor()
    credit = _credit(company, actor, "1000.00")
    entry = _entry(company, branch)

    deduction, applied = register_payroll_loan_deduction(
        request=_req(actor, company=company), actor=actor, entry=entry, credit_id=credit.id, amount=Decimal("300.00")
    )

    assert applied == Decimal("300.00")
    credit.refresh_from_db()
    assert credit.outstanding_amount == Decimal("700.00")
    assert credit.status == ObligationStatus.PARTIAL
    assert PayrollLoanDeduction.objects.filter(entry=entry, credit_id=credit.id).count() == 1
    assert AuditEvent.objects.filter(event_type="NOMINA_LOAN_DEDUCTION_RECORDED", subject_id=str(deduction.id)).exists()
    assert AuditEvent.objects.filter(event_type="PORTFOLIO_PAYROLL_ABONO_APPLIED").exists()


@pytest.mark.django_db
def test_full_abono_marks_credit_paid():
    company, branch = _scope()
    actor = _actor()
    credit = _credit(company, actor, "1000.00")
    entry = _entry(company, branch)

    _deduction, applied = register_payroll_loan_deduction(
        request=_req(actor, company=company), actor=actor, entry=entry, credit_id=credit.id, amount=Decimal("1000.00")
    )
    assert applied == Decimal("1000.00")
    credit.refresh_from_db()
    assert credit.outstanding_amount == Decimal("0.00")
    assert credit.status == ObligationStatus.PAID


@pytest.mark.django_db
def test_abono_caps_at_outstanding():
    company, branch = _scope()
    actor = _actor()
    credit = _credit(company, actor, "1000.00")
    entry = _entry(company, branch)

    _deduction, applied = register_payroll_loan_deduction(
        request=_req(actor, company=company), actor=actor, entry=entry, credit_id=credit.id, amount=Decimal("1500.00")
    )
    assert applied == Decimal("1000.00")  # topado al saldo
    credit.refresh_from_db()
    assert credit.outstanding_amount == Decimal("0.00")
    assert credit.status == ObligationStatus.PAID
