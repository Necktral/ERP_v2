from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.payments.models import CashSession, PaymentIntent
from apps.kernels.payments.services import (
    PaymentsConflictError,
    PaymentsInvalidStateError,
    PaymentsNotFoundError,
    PaymentsValidationError,
    capture_payment_intent_for_scope,
    create_payment_intent,
    open_cash_session_for_scope,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch", parent=company)
    return company, branch


@pytest.mark.django_db
def test_capture_payment_intent_for_scope_raises_not_found():
    company, branch = _mk_scope()
    actor = User.objects.create_user(username="pay_actor_1", password="x")

    with pytest.raises(PaymentsNotFoundError):
        capture_payment_intent_for_scope(
            company=company,
            branch=branch,
            actor=actor,
            payment_id="00000000-0000-0000-0000-000000000001",
        )


@pytest.mark.django_db
def test_capture_payment_intent_for_scope_raises_invalid_state():
    company, branch = _mk_scope()
    actor = User.objects.create_user(username="pay_actor_2", password="x")
    intent = PaymentIntent.objects.create(
        company=company,
        branch=branch,
        amount=Decimal("10.00"),
        status=PaymentIntent.Status.FAILED,
    )

    with pytest.raises(PaymentsInvalidStateError):
        capture_payment_intent_for_scope(
            company=company,
            branch=branch,
            actor=actor,
            payment_id=intent.payment_id,
        )


@pytest.mark.django_db
def test_open_cash_session_for_scope_raises_conflict_if_open_exists():
    company, branch = _mk_scope()
    actor = User.objects.create_user(username="pay_actor_3", password="x")
    CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=actor,
        status=CashSession.Status.OPEN,
        opening_amount=Decimal("0.00"),
        expected_amount=Decimal("0.00"),
        counted_amount=Decimal("0.00"),
        difference_amount=Decimal("0.00"),
    )

    with pytest.raises(PaymentsConflictError):
        open_cash_session_for_scope(
            company=company,
            branch=branch,
            actor=actor,
            opening_amount=Decimal("1.00"),
        )


@pytest.mark.django_db
def test_create_payment_intent_wrapper_requires_branch_scope():
    company, _branch = _mk_scope()
    actor = User.objects.create_user(username="pay_actor_4", password="x")
    request = SimpleNamespace(company=company, user=actor)

    with pytest.raises(PaymentsValidationError):
        create_payment_intent(
            request=request,
            actor=actor,
            amount=Decimal("5.00"),
        )


@pytest.mark.django_db
def test_open_cash_session_for_scope_requires_actor_with_non_null_id():
    company, branch = _mk_scope()

    class ActorWithoutId:
        pass

    class ActorWithNullId:
        id = None

    with pytest.raises(PaymentsValidationError, match="opened_by requiere actor con id no nulo"):
        open_cash_session_for_scope(
            company=company,
            branch=branch,
            actor=ActorWithoutId(),
            opening_amount=Decimal("1.00"),
        )

    with pytest.raises(PaymentsValidationError, match="opened_by requiere actor con id no nulo"):
        open_cash_session_for_scope(
            company=company,
            branch=branch,
            actor=ActorWithNullId(),
            opening_amount=Decimal("1.00"),
        )
