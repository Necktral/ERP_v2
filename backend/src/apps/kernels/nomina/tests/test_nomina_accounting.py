"""Tests del puente nómina → contabilidad (U4): aprobar período genera el asiento de planilla."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.accounting.models import EconomicEvent, JournalDraft, OperationalPostingConfig
from apps.kernels.nomina.models import (
    PayrollEntry,
    PayrollPeriod,
    PayrollSheet,
    PeriodType,
    SalaryType,
)
from apps.kernels.nomina.period_sod import approve_period, request_period_approval
from apps.kernels.nomina.services import compute_entry, create_default_nicaragua_config
from apps.modulos.audit.models import AuditEvent
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent

User = get_user_model()


def _mk_scope():
    tag = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{tag}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{tag}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{tag}", parent=company)
    return company, branch


def _actor():
    u = f"u_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=u, email=f"{u}@t.local", password="x")


def _superuser():
    u = f"jefe_{uuid.uuid4().hex[:8]}"
    return User.objects.create_superuser(username=u, email=f"{u}@t.local", password="x")


def _req(actor, *, company=None):
    return SimpleNamespace(user=actor, META={}, company=company, branch=None, _request=None,
                           ctx=None, request_id=f"r_{uuid.uuid4().hex[:6]}", path="", method="POST")


def _posting_config(company):
    return OperationalPostingConfig.objects.create(
        company=company, branch=None,
        posting_mode=OperationalPostingConfig.PostingMode.HYBRID,
        enable_billing=True, enable_inventory=True, enable_nomina=True,
        auto_post_on_write=False, is_active=True,
    )


def _period_with_entries(company, branch, actor, *, has_inss=True):
    create_default_nicaragua_config(request=_req(actor, company=company), actor=actor, company=company, fiscal_year=2026)
    period = PayrollPeriod.objects.create(
        company=company, year=2026, month=6, period_type=PeriodType.SECOND_HALF,
        start_date=date(2026, 6, 16), end_date=date(2026, 6, 30), working_days=15,
    )
    label = "CON INSS" if has_inss else "SIN INSS"
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name=f"FINCA {label}", has_inss=has_inss)
    for i in range(2):
        emp = Employee.objects.create(company=company, employee_code=f"E{i}", first_name=f"T{i}", last_name="X", is_active=True)
        entry = PayrollEntry.objects.create(
            sheet=sheet, employee=emp, full_name=f"T{i} X", has_inss=has_inss,
            salary_type=SalaryType.MONTHLY, base_salary_nio=Decimal("12000.00"),
            days_in_period=15, days_worked=Decimal("15.00"),
        )
        compute_entry(entry=entry)
    return period


def _approve(company, period):
    maker = _actor()
    checker = _superuser()
    approval = request_period_approval(request=_req(maker, company=company), actor=maker, period=period)
    approve_period(request=_req(checker, company=company), approver=checker, approval=approval)


def _draft_for_period(company):
    ev = OutboxEvent.objects.get(source_module="NOMINA", event_type="PayrollPeriodApproved")
    ee = EconomicEvent.objects.get(company=company, source_outbox_event_id=ev.event_id)
    return JournalDraft.objects.get(economic_event=ee)


@pytest.mark.django_db
def test_approve_period_generates_balanced_payroll_journal_draft():
    company, branch = _mk_scope()
    actor = _actor()
    _posting_config(company)
    period = _period_with_entries(company, branch, actor, has_inss=True)

    expected_net = sum((e.net_to_pay for e in PayrollEntry.objects.filter(sheet__period=period)), Decimal("0.00"))
    _approve(company, period)

    # Outbox + audit emitidos
    assert OutboxEvent.objects.filter(source_module="NOMINA", event_type="PayrollPeriodApproved").exists()
    assert AuditEvent.objects.filter(event_type="NOMINA_PAYROLL_POSTED", subject_id=str(period.id)).exists()

    # Rollup al período
    period.refresh_from_db()
    assert period.total_net == expected_net

    # Asiento balanceado en JournalDraft
    draft = _draft_for_period(company)
    assert draft.total_debit == draft.total_credit
    assert draft.total_debit > Decimal("0.00")
    assert draft.state == JournalDraft.State.VALIDATED
    # La línea de "nómina por pagar" (2304) = neto del período
    net_line = next(line for line in draft.lines_json if line["account"] == "2304")
    assert Decimal(net_line["credit"]) == expected_net


@pytest.mark.django_db
def test_sin_inss_period_posts_zero_inss_lines():
    company, branch = _mk_scope()
    actor = _actor()
    _posting_config(company)
    period = _period_with_entries(company, branch, actor, has_inss=False)
    _approve(company, period)

    draft = _draft_for_period(company)
    assert draft.total_debit == draft.total_credit  # sigue balanceado
    inss_lab = next(line for line in draft.lines_json if line["account"] == "2301")  # INSS laboral por pagar
    inss_pat = next(line for line in draft.lines_json if line["account"] == "6204")  # gasto INSS patronal
    assert Decimal(inss_lab["credit"]) == Decimal("0.00")
    assert Decimal(inss_pat["debit"]) == Decimal("0.00")
