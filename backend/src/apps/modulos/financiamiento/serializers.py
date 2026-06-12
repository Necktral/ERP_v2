"""Serializers del módulo financiamiento (validación de forma; el negocio vive en services)."""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import (
    CoffeeQualityGrade,
    CoffeeReception,
    CreditApplication,
    Currency,
    DisbursementForm,
    ExchangeRate,
    FinancingLoan,
    Liquidation,
    PhysicalState,
    PriceFixation,
    ProducerProfile,
)


class ProducerCreateSerializer(serializers.Serializer):
    party_id = serializers.IntegerField()
    acopio_code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    certifications = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class ProducerSerializer(serializers.ModelSerializer):
    party_name = serializers.CharField(source="party.display_name", read_only=True)
    national_id = serializers.CharField(source="party.national_id", read_only=True)

    class Meta:
        model = ProducerProfile
        fields = [
            "id", "party_id", "party_name", "national_id", "acopio_code",
            "certifications", "is_active", "notes",
        ]


class ExchangeRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRate
        fields = ["id", "rate_date", "rate"]


class QualityGradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoffeeQualityGrade
        fields = ["id", "code", "name", "default_tare_pct", "is_active"]


class ApplicationCreateSerializer(serializers.Serializer):
    producer_id = serializers.IntegerField()
    requested_nio = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0"))
    requested_usd = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0"))
    term_months = serializers.IntegerField(min_value=1)
    credit_type = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    activity = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    interest_rate = serializers.DecimalField(max_digits=7, decimal_places=4)
    penalty_rate = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, default=Decimal("0"))
    commission_rate = serializers.DecimalField(max_digits=7, decimal_places=4, required=False, default=Decimal("0"))
    disbursement_form = serializers.ChoiceField(choices=DisbursementForm.choices, required=False, default=DisbursementForm.CASH)
    guarantee_farm_area_mz = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0"))
    guarantee_solar = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    guarantee_other = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    guarantee_coffee_qq = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=Decimal("0"))


class ApplicationSerializer(serializers.ModelSerializer):
    producer_name = serializers.CharField(source="producer.party.display_name", read_only=True)

    class Meta:
        model = CreditApplication
        fields = [
            "id", "producer_id", "producer_name", "requested_nio", "requested_usd",
            "term_months", "credit_type", "activity", "interest_rate", "penalty_rate",
            "commission_rate", "disbursement_form", "guarantee_farm_area_mz",
            "guarantee_solar", "guarantee_other", "guarantee_coffee_qq", "status",
            "submitted_at", "decided_at", "rejection_reason", "created_at",
        ]


class RejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class DisburseSerializer(serializers.Serializer):
    disbursement_date = serializers.DateField(required=False)
    reference = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")


class LoanSerializer(serializers.ModelSerializer):
    producer_name = serializers.CharField(source="producer.party.display_name", read_only=True)

    class Meta:
        model = FinancingLoan
        fields = [
            "id", "reference", "producer_id", "producer_name", "credit_type", "activity",
            "interest_rate", "penalty_rate", "commission_rate", "term_months",
            "maturity_date", "disbursement_form", "disbursed_at", "status", "created_at",
        ]


class LoanPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    paid_currency = serializers.ChoiceField(choices=Currency.choices)
    target_currency = serializers.ChoiceField(choices=Currency.choices, required=False, allow_blank=True, default="")
    payment_method = serializers.CharField(max_length=32, required=False, default="CASH")
    exchange_rate = serializers.DecimalField(max_digits=12, decimal_places=6, required=False, allow_null=True, default=None)
    payment_date = serializers.DateField(required=False, allow_null=True, default=None)
    idempotency_key = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class RateUpsertSerializer(serializers.Serializer):
    rate_date = serializers.DateField()
    rate = serializers.DecimalField(max_digits=12, decimal_places=6)


class QualityCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=16)
    name = serializers.CharField(max_length=80)
    default_tare_pct = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, default=Decimal("0"))


class ReceptionCreateSerializer(serializers.Serializer):
    producer_id = serializers.IntegerField()
    quality_id = serializers.IntegerField()
    physical_state = serializers.ChoiceField(choices=PhysicalState.choices, required=False, default=PhysicalState.HUMID)
    sacks = serializers.IntegerField(min_value=1)
    gross_lb = serializers.DecimalField(max_digits=14, decimal_places=2)
    tare_lb = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True, default=None)
    reception_date = serializers.DateField(required=False, allow_null=True, default=None)
    reference = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class ReceptionSerializer(serializers.ModelSerializer):
    producer_name = serializers.CharField(source="producer.party.display_name", read_only=True)
    quality_code = serializers.CharField(source="quality.code", read_only=True)

    class Meta:
        model = CoffeeReception
        fields = [
            "id", "producer_id", "producer_name", "reception_date", "reference",
            "quality_id", "quality_code", "physical_state", "sacks", "gross_lb",
            "tare_lb", "net_lb", "stock_movement_id", "note",
        ]


class FixationCreateSerializer(serializers.Serializer):
    producer_id = serializers.IntegerField()
    pounds = serializers.DecimalField(max_digits=14, decimal_places=2)
    price_per_lb = serializers.DecimalField(max_digits=12, decimal_places=4)
    currency = serializers.ChoiceField(choices=Currency.choices, required=False, default=Currency.USD)
    fixation_date = serializers.DateField(required=False, allow_null=True, default=None)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class FixationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceFixation
        fields = [
            "id", "producer_id", "fixation_date", "pounds", "price_per_lb",
            "currency", "status", "liquidation_id", "note",
        ]


class DeductionSerializer(serializers.Serializer):
    concept = serializers.CharField(max_length=120)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)


class LiquidationCreateSerializer(serializers.Serializer):
    producer_id = serializers.IntegerField()
    fixation_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    loan_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    deductions = DeductionSerializer(many=True, required=False, default=list)
    liquidation_date = serializers.DateField(required=False, allow_null=True, default=None)
    exchange_rate = serializers.DecimalField(max_digits=12, decimal_places=6, required=False, allow_null=True, default=None)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class LiquidationSerializer(serializers.ModelSerializer):
    producer_name = serializers.CharField(source="producer.party.display_name", read_only=True)
    loan_reference = serializers.CharField(source="loan.reference", read_only=True, default="")

    class Meta:
        model = Liquidation
        fields = [
            "id", "producer_id", "producer_name", "loan_id", "loan_reference",
            "liquidation_date", "currency", "pounds_total", "gross_value",
            "deductions_total", "applied_to_loan", "applied_currency",
            "surplus_amount", "exchange_rate_used", "payment_intent_id",
            "custody_issue_movement_id", "own_receive_movement_id", "note",
        ]


class SettingsUpdateSerializer(serializers.Serializer):
    coffee_item_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    custody_warehouse_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    liquidation_warehouse_id = serializers.IntegerField(required=False, allow_null=True, default=None)
