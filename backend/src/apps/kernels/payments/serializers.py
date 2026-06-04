from __future__ import annotations

from rest_framework import serializers

from apps.modulos.common.tender import TENDER_PAYMENT_METHOD_CHOICES

from .models import CashMovement


class PaymentIntentCreateIn(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    currency = serializers.CharField(max_length=8, required=False, allow_blank=True)
    external_ref = serializers.CharField(max_length=96, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    provider = serializers.CharField(max_length=32, required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(
        choices=TENDER_PAYMENT_METHOD_CHOICES,
        required=False,
        allow_blank=True,
    )


class PaymentIntentReverseCaptureIn(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=96, allow_blank=False, trim_whitespace=True)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, trim_whitespace=True)


class CashSessionOpenIn(serializers.Serializer):
    opening_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class CashSessionCloseIn(serializers.Serializer):
    counted_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)


class CashMovementCreateIn(serializers.Serializer):
    movement_type = serializers.ChoiceField(choices=CashMovement.MovementType.choices)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    reference = serializers.CharField(max_length=96, required=False, allow_blank=True)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)


class PaymentIntentAuthorizeIn(serializers.Serializer):
    amount_authorized = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, allow_null=True)
    provider_txn_id = serializers.CharField(max_length=96, required=False, allow_blank=True)


class PaymentIntentCaptureIn(serializers.Serializer):
    provider_txn_id = serializers.CharField(max_length=96, required=False, allow_blank=True)


class PaymentIntentRefundIn(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)


class CashSessionOpenWithRegisterIn(serializers.Serializer):
    opening_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    register_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True)
