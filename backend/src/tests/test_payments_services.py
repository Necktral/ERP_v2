from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.kernels.payments.models import CashMovement, CashSession, PaymentIntent
from apps.kernels.payments.services import (
    PaymentsConflictError,
    PaymentsInvalidStateError,
    PaymentsNotFoundError,
    PaymentsValidationError,
    capture_payment_intent_for_scope,
    create_payment_intent,
    create_payment_intent_for_scope,
    open_cash_session_for_scope,
    post_cash_movement_for_scope,
    reverse_captured_payment_intent_for_scope,
)
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent

User = get_user_model()


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch", parent=company)
    return company, branch


def _mk_captured_payment_intent(*, company, branch, actor, payment_method: str = "TRANSFER") -> PaymentIntent:
    intent, _ = create_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        amount=Decimal("25.00"),
        currency="NIO",
        idempotency_key=f"intent-{payment_method or 'unknown'}",
        external_ref=f"ref-{payment_method or 'unknown'}",
        provider="TEST",
        payment_method=payment_method,
    )
    return capture_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        payment_id=intent.payment_id,
        provider_txn_id="txn-001",
    )


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
def test_reverse_captured_payment_intent_for_scope_refunds_transfer_and_emits_event_once():
    company, branch = _mk_scope()
    actor = User.objects.create_user(username="pay_reverse_1", password="x")
    intent = _mk_captured_payment_intent(company=company, branch=branch, actor=actor)
    captured_event = OutboxEvent.objects.get(source_module="PAYMENTS", event_type="PaymentCaptured")

    reversed_intent, idempotent = reverse_captured_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        payment_id=intent.payment_id,
        idempotency_key="reverse-1",
        reason="CUSTOMER_VOID",
    )

    reversed_intent.refresh_from_db()
    event = OutboxEvent.objects.get(source_module="PAYMENTS", event_type="PaymentCaptureReversed")
    data = event.payload["data"]
    assert idempotent is False
    assert reversed_intent.status == PaymentIntent.Status.REFUNDED
    assert reversed_intent.refunded_at is not None
    assert reversed_intent.metadata["capture_reversal"]["idempotency_key"] == "reverse-1"
    assert data["payment_id"] == str(intent.payment_id)
    assert data["amount"] == "25.00"
    assert data["currency"] == "NIO"
    assert data["payment_method"] == "TRANSFER"
    assert data["provider_txn_id"] == "txn-001"
    assert data["previous_status"] == PaymentIntent.Status.CAPTURED
    assert data["status"] == PaymentIntent.Status.REFUNDED
    assert data["idempotency_key"] == "reverse-1"
    assert data["reason"] == "CUSTOMER_VOID"
    assert data["reverses_event_type"] == "PaymentCaptured"
    assert data["reverses_outbox_event_id"] == str(captured_event.event_id)
    assert event.causation_id == str(captured_event.event_id)


@pytest.mark.django_db
def test_reverse_captured_payment_intent_for_scope_replay_is_idempotent():
    company, branch = _mk_scope()
    actor = User.objects.create_user(username="pay_reverse_2", password="x")
    intent = _mk_captured_payment_intent(company=company, branch=branch, actor=actor)

    first, first_idempotent = reverse_captured_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        payment_id=intent.payment_id,
        idempotency_key="reverse-2",
        reason="CUSTOMER_VOID",
    )
    second, second_idempotent = reverse_captured_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        payment_id=intent.payment_id,
        idempotency_key="reverse-2",
        reason="CUSTOMER_VOID",
    )

    assert first.id == second.id
    assert first_idempotent is False
    assert second_idempotent is True
    assert OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="PaymentCaptureReversed").count() == 1


@pytest.mark.django_db
def test_reverse_captured_payment_intent_for_scope_rejects_different_replay_key():
    company, branch = _mk_scope()
    actor = User.objects.create_user(username="pay_reverse_3", password="x")
    intent = _mk_captured_payment_intent(company=company, branch=branch, actor=actor)
    reverse_captured_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        payment_id=intent.payment_id,
        idempotency_key="reverse-3",
    )

    with pytest.raises(PaymentsConflictError):
        reverse_captured_payment_intent_for_scope(
            company=company,
            branch=branch,
            actor=actor,
            payment_id=intent.payment_id,
            idempotency_key="reverse-3b",
        )

    assert OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="PaymentCaptureReversed").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("payment_method", ["CASH", "CARD", "CREDIT", ""])
def test_reverse_captured_payment_intent_for_scope_blocks_non_transfer_tenders(payment_method: str):
    company, branch = _mk_scope()
    actor = User.objects.create_user(username=f"pay_reverse_tender_{payment_method or 'unknown'}", password="x")
    intent = _mk_captured_payment_intent(
        company=company,
        branch=branch,
        actor=actor,
        payment_method=payment_method,
    )

    with pytest.raises(PaymentsInvalidStateError):
        reverse_captured_payment_intent_for_scope(
            company=company,
            branch=branch,
            actor=actor,
            payment_id=intent.payment_id,
            idempotency_key=f"reverse-{payment_method or 'unknown'}",
        )

    intent.refresh_from_db()
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="PaymentCaptureReversed").count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "intent_status",
    [
        PaymentIntent.Status.INTENDED,
        PaymentIntent.Status.AUTHORIZED,
        PaymentIntent.Status.FAILED,
        PaymentIntent.Status.REFUNDED,
    ],
)
def test_reverse_captured_payment_intent_for_scope_rejects_non_captured_states(intent_status: str):
    company, branch = _mk_scope()
    actor = User.objects.create_user(username=f"pay_reverse_state_{intent_status.lower()}", password="x")
    intent = PaymentIntent.objects.create(
        company=company,
        branch=branch,
        amount=Decimal("25.00"),
        status=intent_status,
        payment_method="TRANSFER",
    )

    with pytest.raises(PaymentsInvalidStateError):
        reverse_captured_payment_intent_for_scope(
            company=company,
            branch=branch,
            actor=actor,
            payment_id=intent.payment_id,
            idempotency_key=f"reverse-state-{intent_status}",
        )

    assert OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="PaymentCaptureReversed").count() == 0


@pytest.mark.django_db
def test_reverse_captured_payment_intent_for_scope_requires_original_payment_captured_event():
    company, branch = _mk_scope()
    actor = User.objects.create_user(username="pay_reverse_missing_captured", password="x")
    intent = PaymentIntent.objects.create(
        company=company,
        branch=branch,
        amount=Decimal("25.00"),
        status=PaymentIntent.Status.CAPTURED,
        payment_method="TRANSFER",
        captured_at=timezone.now(),
    )

    with pytest.raises(PaymentsConflictError):
        reverse_captured_payment_intent_for_scope(
            company=company,
            branch=branch,
            actor=actor,
            payment_id=intent.payment_id,
            idempotency_key="reverse-missing-captured",
        )

    intent.refresh_from_db()
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="PaymentCaptureReversed").count() == 0


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


@pytest.mark.django_db
def test_post_cash_movement_for_scope_is_idempotent_and_updates_expected_amount_once():
    company, branch = _mk_scope()
    actor = User.objects.create_user(username="pay_actor_5", password="x")
    session = CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=actor,
        status=CashSession.Status.OPEN,
        opening_amount=Decimal("100.00"),
        expected_amount=Decimal("100.00"),
        counted_amount=Decimal("0.00"),
        difference_amount=Decimal("0.00"),
    )

    first, first_idempotent = post_cash_movement_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        session_id=session.id,
        movement_type=CashMovement.MovementType.INCOME,
        amount=Decimal("25.00"),
        reference="ticket-1",
        reason="sale",
        idempotency_key="cash-svc-1",
    )
    second, second_idempotent = post_cash_movement_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        session_id=session.id,
        movement_type=CashMovement.MovementType.INCOME,
        amount=Decimal("25.00"),
        reference="ticket-1",
        reason="sale",
        idempotency_key="cash-svc-1",
    )

    session.refresh_from_db()
    assert first_idempotent is False
    assert second_idempotent is True
    assert second.id == first.id
    assert CashMovement.objects.filter(session=session, idempotency_key="cash-svc-1").count() == 1
    assert session.expected_amount == Decimal("125.00")


@pytest.mark.django_db
def test_post_cash_movement_for_scope_rejects_idempotency_payload_mismatch():
    company, branch = _mk_scope()
    actor = User.objects.create_user(username="pay_actor_6", password="x")
    session = CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=actor,
        status=CashSession.Status.OPEN,
        opening_amount=Decimal("100.00"),
        expected_amount=Decimal("100.00"),
        counted_amount=Decimal("0.00"),
        difference_amount=Decimal("0.00"),
    )

    first, first_idempotent = post_cash_movement_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        session_id=session.id,
        movement_type=CashMovement.MovementType.INCOME,
        amount=Decimal("25.00"),
        reference="ticket-1",
        reason="sale",
        idempotency_key="cash-svc-2",
    )

    with pytest.raises(PaymentsConflictError, match="Idempotency key reutilizada con payload distinto."):
        post_cash_movement_for_scope(
            company=company,
            branch=branch,
            actor=actor,
            session_id=session.id,
            movement_type=CashMovement.MovementType.INCOME,
            amount=Decimal("30.00"),
            reference="ticket-1",
            reason="sale",
            idempotency_key="cash-svc-2",
        )

    session.refresh_from_db()
    assert first_idempotent is False
    assert CashMovement.objects.filter(session=session).count() == 1
    assert CashMovement.objects.get(session=session).id == first.id
    assert session.expected_amount == Decimal("125.00")
