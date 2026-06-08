"""
Tests del kernel portfolio — CxC, CxP, Créditos, allocations, devengo de interés.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.kernels.portfolio.models import (
    AccountingStatus,
    AllocationStatus,
    CreditStatus,
    InterestAccrual,
    ObligationStatus,
    PortfolioSettings,
    Receivable,
)
from apps.kernels.portfolio.services import (
    PortfolioDomainError,
    accrue_interest_for_credit,
    allocate_payment_to_obligation,
    auto_allocate_payment,
    create_credit,
    create_payable,
    create_receivable,
    disburse_credit,
    update_aging_for_obligations,
)
from apps.modulos.iam.models import OrgUnit
from apps.modulos.parties.models import Party


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mk_scope(suffix=""):
    s = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _mk_party(company, name="Cliente A"):
    return Party.objects.create(
        company=company,
        party_type=Party.PartyType.NATURAL,
        display_name=name,
        status=Party.Status.ACTIVE,
    )


def _mk_payment_intent(company, amount="1000.00", currency="NIO", status="CAPTURED"):
    """Stub de PaymentIntent para tests de allocation."""
    from apps.kernels.payments.models import PaymentIntent
    intent = PaymentIntent(
        company=company,
        amount=Decimal(amount),
        currency=currency,
        status=status,
        payment_method="CASH",
    )
    intent.save()
    return intent


def _today():
    return timezone.localdate()


def _due(days=30):
    return _today() + timedelta(days=days)


# ---------------------------------------------------------------------------
# create_receivable
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_receivable_basic():
    company, branch = _mk_scope()
    party = _mk_party(company)

    receivable = create_receivable(
        company=company,
        branch=branch,
        party=party,
        reference_type="INVOICE",
        reference_id=1,
        principal_amount=Decimal("500.00"),
        currency="NIO",
        issue_date=_today(),
        due_date=_due(30),
    )

    assert receivable.pk is not None
    assert receivable.principal_amount == Decimal("500.00")
    assert receivable.status == ObligationStatus.PENDING
    assert receivable.accounting_status == AccountingStatus.PENDING_RULESET
    assert receivable.outstanding_amount == Decimal("500.00")


@pytest.mark.django_db
def test_create_receivable_invalid_amount_raises():
    company, branch = _mk_scope()
    party = _mk_party(company)

    with pytest.raises(PortfolioDomainError, match="INVALID_AMOUNT"):
        create_receivable(
            company=company, branch=branch, party=party,
            reference_type="INVOICE", reference_id=1,
            principal_amount=Decimal("0.00"), currency="NIO",
            issue_date=_today(), due_date=_due(30),
        )


@pytest.mark.django_db
def test_create_receivable_negative_amount_raises():
    company, branch = _mk_scope()
    party = _mk_party(company)

    with pytest.raises(PortfolioDomainError, match="INVALID_AMOUNT"):
        create_receivable(
            company=company, branch=branch, party=party,
            reference_type="INVOICE", reference_id=2,
            principal_amount=Decimal("-100.00"), currency="NIO",
            issue_date=_today(), due_date=_due(30),
        )


# ---------------------------------------------------------------------------
# create_payable
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_payable_basic():
    company, branch = _mk_scope()
    party = _mk_party(company, "Proveedor A")

    payable = create_payable(
        company=company,
        branch=branch,
        party=party,
        reference_type="SUPPLIER_INVOICE",
        reference_id=10,
        principal_amount=Decimal("2000.00"),
        currency="NIO",
        issue_date=_today(),
        due_date=_due(45),
        supplier_invoice_number="FAC-001",
    )

    assert payable.pk is not None
    assert payable.principal_amount == Decimal("2000.00")
    assert payable.status == ObligationStatus.PENDING
    assert payable.withholding_tax_amount == Decimal("0.00")


@pytest.mark.django_db
def test_create_payable_with_withholding():
    company, branch = _mk_scope()
    party = _mk_party(company, "Proveedor B")

    payable = create_payable(
        company=company, branch=branch, party=party,
        reference_type="SUPPLIER_INVOICE", reference_id=11,
        principal_amount=Decimal("1000.00"), currency="NIO",
        issue_date=_today(), due_date=_due(30),
        withholding_tax_rate=Decimal("2.00"),
    )

    assert payable.withholding_tax_amount == Decimal("20.00")  # 2% de 1000


@pytest.mark.django_db
def test_create_payable_with_early_payment_discount():
    company, branch = _mk_scope()
    party = _mk_party(company, "Proveedor C")
    issue = _today()

    payable = create_payable(
        company=company, branch=branch, party=party,
        reference_type="SUPPLIER_INVOICE", reference_id=12,
        principal_amount=Decimal("3000.00"), currency="NIO",
        issue_date=issue, due_date=issue + timedelta(days=60),
        early_payment_discount_rate=Decimal("2.00"),
        early_payment_discount_days=10,
    )

    assert payable.early_payment_discount_date == issue + timedelta(days=10)


# ---------------------------------------------------------------------------
# create_credit + disburse_credit
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_credit_basic():
    company, _ = _mk_scope()
    lender = _mk_party(company, "Banco A")
    borrower = _mk_party(company, "Cliente Crédito")

    credit = create_credit(
        company=company,
        credit_type="TERM_LOAN",
        lender_party=lender,
        borrower_party=borrower,
        approved_amount=Decimal("50000.00"),
        currency="NIO",
        interest_rate=Decimal("18.00"),
        term_months=12,
        maturity_date=_due(365),
    )

    assert credit.pk is not None
    assert credit.credit_status == CreditStatus.APPROVED
    assert credit.disbursed_amount == Decimal("0.00")
    assert credit.approved_amount == Decimal("50000.00")


@pytest.mark.django_db
def test_create_credit_same_lender_borrower_raises():
    company, _ = _mk_scope()
    party = _mk_party(company, "Mismo Party")

    with pytest.raises(PortfolioDomainError, match="INVALID_PARTIES"):
        create_credit(
            company=company, credit_type="TERM_LOAN",
            lender_party=party, borrower_party=party,
            approved_amount=Decimal("10000.00"), currency="NIO",
            interest_rate=Decimal("10.00"), term_months=6,
            maturity_date=_due(180),
        )


@pytest.mark.django_db
def test_disburse_credit_full():
    company, _ = _mk_scope()
    lender = _mk_party(company, "Banco B")
    borrower = _mk_party(company, "Empresa X")

    credit = create_credit(
        company=company, credit_type="WORKING_CAPITAL",
        lender_party=lender, borrower_party=borrower,
        approved_amount=Decimal("100000.00"), currency="NIO",
        interest_rate=Decimal("15.00"), term_months=24,
        maturity_date=_due(730),
    )
    from django.contrib.auth import get_user_model
    actor = get_user_model().objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")

    credit = disburse_credit(
        credit=credit,
        disbursed_amount=Decimal("100000.00"),
        disbursement_date=_today(),
        disbursed_by=actor,
    )

    assert credit.credit_status == CreditStatus.DISBURSED
    assert credit.disbursed_amount == Decimal("100000.00")
    assert credit.disbursement_date == _today()


@pytest.mark.django_db
def test_disburse_credit_partial_then_full():
    company, _ = _mk_scope()
    lender = _mk_party(company, "Banco C")
    borrower = _mk_party(company, "Empresa Y")

    credit = create_credit(
        company=company, credit_type="WORKING_CAPITAL",
        lender_party=lender, borrower_party=borrower,
        approved_amount=Decimal("60000.00"), currency="NIO",
        interest_rate=Decimal("12.00"), term_months=12,
        maturity_date=_due(365),
    )

    from django.contrib.auth import get_user_model
    actor = get_user_model().objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")

    credit = disburse_credit(credit=credit, disbursed_amount=Decimal("30000.00"),
                              disbursement_date=_today(), disbursed_by=actor)
    assert credit.credit_status == CreditStatus.ACTIVE

    credit = disburse_credit(credit=credit, disbursed_amount=Decimal("30000.00"),
                              disbursement_date=_today(), disbursed_by=actor)
    assert credit.credit_status == CreditStatus.DISBURSED
    assert credit.disbursed_amount == Decimal("60000.00")


@pytest.mark.django_db
def test_disburse_credit_exceeds_approved_raises():
    company, _ = _mk_scope()
    lender = _mk_party(company, "Banco D")
    borrower = _mk_party(company, "Empresa Z")

    credit = create_credit(
        company=company, credit_type="TERM_LOAN",
        lender_party=lender, borrower_party=borrower,
        approved_amount=Decimal("10000.00"), currency="NIO",
        interest_rate=Decimal("10.00"), term_months=6,
        maturity_date=_due(180),
    )
    from django.contrib.auth import get_user_model
    actor = get_user_model().objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")

    with pytest.raises(PortfolioDomainError, match="EXCEEDS_APPROVED"):
        disburse_credit(credit=credit, disbursed_amount=Decimal("20000.00"),
                        disbursement_date=_today(), disbursed_by=actor)


# ---------------------------------------------------------------------------
# allocate_payment_to_obligation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_allocate_payment_full():
    company, branch = _mk_scope()
    party = _mk_party(company)
    receivable = create_receivable(
        company=company, branch=branch, party=party,
        reference_type="INVOICE", reference_id=100,
        principal_amount=Decimal("800.00"), currency="NIO",
        issue_date=_today(), due_date=_due(30),
    )
    intent = _mk_payment_intent(company, amount="800.00")

    allocation = allocate_payment_to_obligation(
        payment_intent=intent,
        obligation=receivable,
        allocated_amount=Decimal("800.00"),
        allocation_date=_today(),
        created_by=None,
    )

    assert allocation.status == AllocationStatus.APPLIED
    assert allocation.allocated_amount == Decimal("800.00")
    receivable.refresh_from_db()
    assert receivable.status == ObligationStatus.PAID


@pytest.mark.django_db
def test_allocate_payment_partial():
    company, branch = _mk_scope()
    party = _mk_party(company)
    receivable = create_receivable(
        company=company, branch=branch, party=party,
        reference_type="INVOICE", reference_id=101,
        principal_amount=Decimal("1000.00"), currency="NIO",
        issue_date=_today(), due_date=_due(30),
    )
    intent = _mk_payment_intent(company, amount="1000.00")

    allocate_payment_to_obligation(
        payment_intent=intent, obligation=receivable,
        allocated_amount=Decimal("400.00"),
        allocation_date=_today(), created_by=None,
    )

    receivable.refresh_from_db()
    assert receivable.status == ObligationStatus.PARTIAL
    assert receivable.allocated_amount == Decimal("400.00")
    assert receivable.outstanding_amount == Decimal("600.00")


@pytest.mark.django_db
def test_allocate_payment_not_captured_raises():
    company, branch = _mk_scope()
    party = _mk_party(company)
    receivable = create_receivable(
        company=company, branch=branch, party=party,
        reference_type="INVOICE", reference_id=102,
        principal_amount=Decimal("500.00"), currency="NIO",
        issue_date=_today(), due_date=_due(30),
    )
    intent = _mk_payment_intent(company, amount="500.00", status="INTENDED")

    with pytest.raises(PortfolioDomainError, match="PAYMENT_NOT_CAPTURED"):
        allocate_payment_to_obligation(
            payment_intent=intent, obligation=receivable,
            allocated_amount=Decimal("500.00"),
            allocation_date=_today(), created_by=None,
        )


@pytest.mark.django_db
def test_allocate_exceeds_outstanding_raises():
    company, branch = _mk_scope()
    party = _mk_party(company)
    receivable = create_receivable(
        company=company, branch=branch, party=party,
        reference_type="INVOICE", reference_id=103,
        principal_amount=Decimal("300.00"), currency="NIO",
        issue_date=_today(), due_date=_due(30),
    )
    intent = _mk_payment_intent(company, amount="1000.00")

    with pytest.raises(PortfolioDomainError, match="EXCEEDS_OUTSTANDING"):
        allocate_payment_to_obligation(
            payment_intent=intent, obligation=receivable,
            allocated_amount=Decimal("500.00"),
            allocation_date=_today(), created_by=None,
        )


@pytest.mark.django_db
def test_allocate_with_breakdown():
    company, branch = _mk_scope()
    party = _mk_party(company)
    receivable = create_receivable(
        company=company, branch=branch, party=party,
        reference_type="INVOICE", reference_id=104,
        principal_amount=Decimal("1000.00"), currency="NIO",
        issue_date=_today(), due_date=_due(30),
    )
    # Agregar interés y penalidad manualmente
    receivable.interest_amount = Decimal("50.00")
    receivable.penalty_amount = Decimal("20.00")
    receivable.save(update_fields=["interest_amount", "penalty_amount"])

    intent = _mk_payment_intent(company, amount="1070.00")

    breakdown = {
        "principal": Decimal("1000.00"),
        "interest": Decimal("50.00"),
        "fee": Decimal("0.00"),
        "penalty": Decimal("20.00"),
    }
    allocation = allocate_payment_to_obligation(
        payment_intent=intent, obligation=receivable,
        allocated_amount=Decimal("1070.00"),
        allocation_date=_today(), created_by=None,
        allocation_breakdown=breakdown,
    )

    assert allocation.principal_applied == Decimal("1000.00")
    assert allocation.interest_applied == Decimal("50.00")
    assert allocation.penalty_applied == Decimal("20.00")


# ---------------------------------------------------------------------------
# auto_allocate_payment — FIFO a receivables
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_auto_allocate_fifo_multiple_receivables():
    company, branch = _mk_scope()
    party = _mk_party(company)

    # Habilitar auto allocation
    settings_obj = PortfolioSettings.get_or_create_for_company(company)
    settings_obj.auto_allocate_payments = True
    settings_obj.save(update_fields=["auto_allocate_payments"])

    # Dos facturas, la más antigua primero (FIFO)
    r1 = create_receivable(
        company=company, branch=branch, party=party,
        reference_type="INVOICE", reference_id=200,
        principal_amount=Decimal("300.00"), currency="NIO",
        issue_date=_today() - timedelta(days=10),
        due_date=_today() + timedelta(days=20),
    )
    r2 = create_receivable(
        company=company, branch=branch, party=party,
        reference_type="INVOICE", reference_id=201,
        principal_amount=Decimal("500.00"), currency="NIO",
        issue_date=_today() - timedelta(days=5),
        due_date=_today() + timedelta(days=25),
    )

    intent = _mk_payment_intent(company, amount="800.00")
    allocations = auto_allocate_payment(
        payment_intent=intent, party=party, created_by=None,
    )

    assert len(allocations) == 2
    r1.refresh_from_db()
    r2.refresh_from_db()
    assert r1.status == ObligationStatus.PAID
    assert r2.status == ObligationStatus.PAID


@pytest.mark.django_db
def test_auto_allocate_disabled_raises():
    company, branch = _mk_scope()
    party = _mk_party(company)

    settings_obj = PortfolioSettings.get_or_create_for_company(company)
    settings_obj.auto_allocate_payments = False
    settings_obj.save(update_fields=["auto_allocate_payments"])

    intent = _mk_payment_intent(company, amount="500.00")

    with pytest.raises(PortfolioDomainError, match="AUTO_ALLOCATION_DISABLED"):
        auto_allocate_payment(payment_intent=intent, party=party, created_by=None)


# ---------------------------------------------------------------------------
# accrue_interest_for_credit
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_accrue_interest_simple():
    company, _ = _mk_scope()
    lender = _mk_party(company, "Banco E")
    borrower = _mk_party(company, "Deudor F")

    credit = create_credit(
        company=company, credit_type="TERM_LOAN",
        lender_party=lender, borrower_party=borrower,
        approved_amount=Decimal("12000.00"), currency="NIO",
        interest_rate=Decimal("18.00"), term_months=12,
        maturity_date=_due(365),
    )
    from django.contrib.auth import get_user_model
    actor = get_user_model().objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")
    disburse_credit(credit=credit, disbursed_amount=Decimal("12000.00"),
                    disbursement_date=_today(), disbursed_by=actor)

    period_start = _today()
    period_end = _today() + timedelta(days=29)

    accrual = accrue_interest_for_credit(
        credit=credit,
        accrual_date=period_end,
        period_start=period_start,
        period_end=period_end,
    )

    assert accrual is not None
    assert accrual.accrued_interest > Decimal("0.00")
    assert accrual.days_in_period == 30
    credit.refresh_from_db()
    assert credit.interest_amount == accrual.accrued_interest


@pytest.mark.django_db
def test_accrue_interest_idempotent():
    company, _ = _mk_scope()
    lender = _mk_party(company, "Banco G")
    borrower = _mk_party(company, "Deudor H")

    credit = create_credit(
        company=company, credit_type="TERM_LOAN",
        lender_party=lender, borrower_party=borrower,
        approved_amount=Decimal("6000.00"), currency="NIO",
        interest_rate=Decimal("12.00"), term_months=6,
        maturity_date=_due(180),
    )
    from django.contrib.auth import get_user_model
    actor = get_user_model().objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")
    disburse_credit(credit=credit, disbursed_amount=Decimal("6000.00"),
                    disbursement_date=_today(), disbursed_by=actor)

    period_start = _today()
    accrual_date = _today() + timedelta(days=14)

    a1 = accrue_interest_for_credit(credit=credit, accrual_date=accrual_date,
                                    period_start=period_start, period_end=accrual_date)
    a2 = accrue_interest_for_credit(credit=credit, accrual_date=accrual_date,
                                    period_start=period_start, period_end=accrual_date)

    assert a1.id == a2.id
    assert InterestAccrual.objects.filter(credit=credit).count() == 1


@pytest.mark.django_db
def test_accrue_interest_not_disbursed_returns_none():
    company, _ = _mk_scope()
    lender = _mk_party(company, "Banco I")
    borrower = _mk_party(company, "Deudor J")

    credit = create_credit(
        company=company, credit_type="TERM_LOAN",
        lender_party=lender, borrower_party=borrower,
        approved_amount=Decimal("5000.00"), currency="NIO",
        interest_rate=Decimal("10.00"), term_months=6,
        maturity_date=_due(180),
    )
    # No desembolsado → credit_status=APPROVED → retorna None
    result = accrue_interest_for_credit(
        credit=credit, accrual_date=_today(),
        period_start=_today(), period_end=_today(),
    )
    assert result is None


# ---------------------------------------------------------------------------
# update_aging_for_obligations
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_update_aging_marks_overdue():
    company, branch = _mk_scope()
    party = _mk_party(company)

    # Crear con fecha futura → PENDING
    receivable = create_receivable(
        company=company, branch=branch, party=party,
        reference_type="INVOICE", reference_id=300,
        principal_amount=Decimal("200.00"), currency="NIO",
        issue_date=_today() - timedelta(days=35),
        due_date=_today() + timedelta(days=30),
    )
    assert receivable.status == ObligationStatus.PENDING

    # Mover due_date al pasado sin disparar save() override
    Receivable.objects.filter(pk=receivable.pk).update(
        due_date=_today() - timedelta(days=5)
    )

    update_aging_for_obligations(company=company, as_of_date=_today())

    receivable.refresh_from_db()
    assert receivable.status == ObligationStatus.OVERDUE
    assert receivable.days_overdue >= 5


@pytest.mark.django_db
def test_update_aging_skips_paid():
    company, branch = _mk_scope()
    party = _mk_party(company)

    paid = create_receivable(
        company=company, branch=branch, party=party,
        reference_type="INVOICE", reference_id=301,
        principal_amount=Decimal("100.00"), currency="NIO",
        issue_date=_today() - timedelta(days=40),
        due_date=_today() - timedelta(days=10),
    )
    paid.status = ObligationStatus.PAID
    paid.save(update_fields=["status"])

    update_aging_for_obligations(company=company, as_of_date=_today())

    paid.refresh_from_db()
    assert paid.status == ObligationStatus.PAID
