from __future__ import annotations

from rest_framework import serializers

from .models import IRBracket, NominaConfig, PayrollEntry, PayrollPeriod, PayrollSheet


# ---------------------------------------------------------------------------
# NominaConfig
# ---------------------------------------------------------------------------

class IRBracketOut(serializers.ModelSerializer):
    class Meta:
        model = IRBracket
        fields = ["id", "order", "min_income", "max_income", "base_tax", "rate"]


class NominaConfigOut(serializers.ModelSerializer):
    ir_brackets = IRBracketOut(many=True, read_only=True)

    class Meta:
        model = NominaConfig
        fields = [
            "id", "fiscal_year", "effective_from", "is_active",
            "inss_laboral_rate",
            "inss_patronal_rate_small", "inss_patronal_rate_large", "inss_size_threshold",
            "inatec_rate",
            "vacation_rate", "thirteenth_month_rate",
            "overtime_rate", "sunday_bonus_rate", "seventh_day_rate",
            "subsidy_employer_days", "subsidy_inss_rate",
            "min_wage_agro", "min_wage_general",
            "payment_deadline_days", "late_payment_surcharge",
            "notes", "created_at", "updated_at",
            "ir_brackets",
        ]


class NominaConfigUpdateIn(serializers.Serializer):
    inss_laboral_rate = serializers.DecimalField(max_digits=6, decimal_places=5, required=False)
    inss_patronal_rate_small = serializers.DecimalField(max_digits=6, decimal_places=5, required=False)
    inss_patronal_rate_large = serializers.DecimalField(max_digits=6, decimal_places=5, required=False)
    inss_size_threshold = serializers.IntegerField(min_value=1, required=False)
    inatec_rate = serializers.DecimalField(max_digits=6, decimal_places=5, required=False)
    vacation_rate = serializers.DecimalField(max_digits=8, decimal_places=6, required=False)
    thirteenth_month_rate = serializers.DecimalField(max_digits=8, decimal_places=6, required=False)
    overtime_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    sunday_bonus_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    seventh_day_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    subsidy_employer_days = serializers.IntegerField(min_value=0, required=False)
    subsidy_inss_rate = serializers.DecimalField(max_digits=5, decimal_places=4, required=False)
    min_wage_agro = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    min_wage_general = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    payment_deadline_days = serializers.IntegerField(min_value=1, required=False)
    late_payment_surcharge = serializers.DecimalField(max_digits=5, decimal_places=4, required=False)
    is_active = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class IRBracketIn(serializers.Serializer):
    order = serializers.IntegerField(min_value=1)
    min_income = serializers.DecimalField(max_digits=14, decimal_places=2)
    max_income = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    base_tax = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    rate = serializers.DecimalField(max_digits=6, decimal_places=5)


# ---------------------------------------------------------------------------
# PayrollPeriod
# ---------------------------------------------------------------------------

class PayrollPeriodOut(serializers.ModelSerializer):
    class Meta:
        model = PayrollPeriod
        fields = [
            "id", "year", "month", "period_type",
            "start_date", "end_date", "working_days",
            "exchange_rate_usd", "status",
            "total_gross", "total_deductions", "total_net",
            "total_patronal", "total_payroll_cost",
            "notes", "created_at", "updated_at",
        ]


class PayrollPeriodCreateIn(serializers.Serializer):
    year = serializers.IntegerField(min_value=2020, max_value=2099)
    month = serializers.IntegerField(min_value=1, max_value=12)
    period_type = serializers.ChoiceField(choices=["FIRST_HALF", "SECOND_HALF", "MONTHLY"])
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    working_days = serializers.IntegerField(min_value=1, max_value=31, required=False, default=15)
    exchange_rate_usd = serializers.DecimalField(max_digits=10, decimal_places=4, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# PayrollSheet
# ---------------------------------------------------------------------------

class PayrollSheetOut(serializers.ModelSerializer):
    entry_count = serializers.IntegerField(source="entries.count", read_only=True)

    class Meta:
        model = PayrollSheet
        fields = [
            "id", "sheet_name", "has_inss", "status",
            "entry_count", "notes",
            "submitted_by", "submitted_at",
            "approved_by", "approved_at",
            "created_at", "updated_at",
        ]


class PayrollSheetCreateIn(serializers.Serializer):
    sheet_name = serializers.CharField(max_length=160)
    has_inss = serializers.BooleanField(default=True)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# PayrollEntry
# ---------------------------------------------------------------------------

class PayrollEntryOut(serializers.ModelSerializer):
    class Meta:
        model = PayrollEntry
        fields = [
            "id", "full_name", "inss_number", "cedula", "gender", "cargo",
            "has_inss", "salary_type", "payment_frequency",
            "base_salary_usd", "base_salary_nio", "exchange_rate", "daily_rate_nio",
            "days_in_period", "days_worked", "days_subsidy",
            "overtime_hours", "sunday_worked_days",
            # Ingresos
            "quincenal_salary", "subsidy_amount", "overtime_amount", "sunday_bonus_amount",
            "vacation_provision", "thirteenth_month_provision", "other_income", "total_income",
            # Retenciones
            "inss_laboral", "ir_amount", "loan_payment",
            "food_deduction", "advance_deduction", "store_credit_deduction",
            "other_deductions", "total_deductions",
            # Neto
            "total_devengado", "net_to_pay",
            # Patronal
            "inss_patronal", "inatec",
            "vacation_cost", "thirteenth_month_cost",
            "total_employer_cost", "total_payroll_cost",
            "notes",
        ]


class PayrollEntryCreateIn(serializers.Serializer):
    # Identificación
    employee_id = serializers.IntegerField(required=False, allow_null=True)
    inss_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    cedula = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    full_name = serializers.CharField(max_length=160)
    gender = serializers.ChoiceField(choices=["M", "F"], required=False, allow_blank=True, default="")
    cargo = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")

    # Tipo de nómina
    has_inss = serializers.BooleanField(default=True)
    salary_type = serializers.ChoiceField(choices=["MONTHLY", "DAILY", "HOURLY"], default="MONTHLY")
    payment_frequency = serializers.ChoiceField(
        choices=["FIRST_HALF", "SECOND_HALF", "MONTHLY"], default="FIRST_HALF"
    )

    # Salario
    base_salary_usd = serializers.DecimalField(max_digits=10, decimal_places=4, required=False, allow_null=True)
    base_salary_nio = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")

    # Asistencia
    days_in_period = serializers.IntegerField(min_value=1, max_value=31, default=15)
    days_worked = serializers.DecimalField(max_digits=5, decimal_places=2, default="15.00")
    days_subsidy = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default="0.00")
    overtime_hours = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, default="0.00")
    sunday_worked_days = serializers.IntegerField(min_value=0, required=False, default=0)

    # Descuentos adicionales manuales
    loan_payment = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")
    food_deduction = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")
    advance_deduction = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")
    store_credit_deduction = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")
    other_deductions = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")
    other_income = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")
    ir_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")

    notes = serializers.CharField(required=False, allow_blank=True, default="")
