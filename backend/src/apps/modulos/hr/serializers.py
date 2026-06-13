from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers


# Payload para reset password provisional
class ResetTempPasswordSerializer(serializers.Serializer):
    temp_password = serializers.CharField(required=False, allow_blank=True, default="")


class EmployeeRevokeAccessSerializer(serializers.Serializer):
    # Si True: intenta setear user.is_active=False, pero solo si el usuario ya no tiene
    # memberships activas en ninguna otra org_unit
    disable_user = serializers.BooleanField(required=False, default=False)


class PositionCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")


class PositionUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    code = serializers.CharField(max_length=64, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class PositionRoleMapUpdateSerializer(serializers.Serializer):
    maps = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=True,
    )


class EmployeeCreateSerializer(serializers.Serializer):
    employee_code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    party_id = serializers.IntegerField(required=False)
    first_name = serializers.CharField(max_length=120)
    last_name = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    # Datos de planilla (la nómina los copia del expediente al crear la entrada)
    cedula = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    inss_number = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    gender = serializers.ChoiceField(choices=["M", "F"], required=False, allow_blank=True, default="")
    salary_type = serializers.ChoiceField(choices=["DAILY", "MONTHLY"], required=False, default="DAILY")
    daily_rate_nio = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0.00"))
    monthly_salary_nio = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0.00"))
    is_active = serializers.BooleanField(required=False, default=True)
    linked_user_id = serializers.IntegerField(required=False)


class EmployeeUpdateSerializer(serializers.Serializer):
    employee_code = serializers.CharField(max_length=64, required=False, allow_blank=True)
    party_id = serializers.IntegerField(required=False, allow_null=True)
    first_name = serializers.CharField(max_length=120, required=False)
    last_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    cedula = serializers.CharField(max_length=20, required=False, allow_blank=True)
    inss_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=["M", "F", ""], required=False, allow_blank=True)
    salary_type = serializers.ChoiceField(choices=["DAILY", "MONTHLY"], required=False)
    daily_rate_nio = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    monthly_salary_nio = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    is_active = serializers.BooleanField(required=False)
    linked_user_id = serializers.IntegerField(required=False, allow_null=True)


class AssignmentCreateSerializer(serializers.Serializer):
    position_id = serializers.IntegerField()
    branch_id = serializers.IntegerField(required=False, allow_null=True)


class EmployeeProvisionUserSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    temp_password = serializers.CharField(required=False, allow_blank=True, default="")


# --- Ciclo de vida laboral ---


class EmployeeSuspendSerializer(serializers.Serializer):
    reason_code = serializers.CharField(max_length=32)
    reason_detail = serializers.CharField(required=False, allow_blank=True, default="")
    effective_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True, default=None)
    with_pay = serializers.BooleanField(required=False, default=False)
    suspend_access = serializers.BooleanField(required=False, default=False)


class EmployeeReinstateSerializer(serializers.Serializer):
    reason_detail = serializers.CharField(required=False, allow_blank=True, default="")
    effective_date = serializers.DateField()


class EmployeeTerminateSerializer(serializers.Serializer):
    reason_code = serializers.CharField(max_length=32)
    reason_detail = serializers.CharField(required=False, allow_blank=True, default="")
    effective_date = serializers.DateField()


class EmployeeRehireSerializer(serializers.Serializer):
    reason_detail = serializers.CharField(required=False, allow_blank=True, default="")
    effective_date = serializers.DateField()


# --- Contratos laborales ---


class ContractCreateSerializer(serializers.Serializer):
    contract_type = serializers.CharField(max_length=16)
    position_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True, default=None)
    salary_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, default=None
    )
    salary_period = serializers.CharField(max_length=16, required=False, default="MENSUAL")
    work_description = serializers.CharField(required=False, allow_blank=True, default="")
    season_description = serializers.CharField(required=False, allow_blank=True, default="")


class ContractUpdateSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False, allow_null=True)
    salary_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    salary_period = serializers.CharField(max_length=16, required=False)


# --- Memorandos ---


class MemoCreateSerializer(serializers.Serializer):
    memo_type = serializers.CharField(max_length=32)
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField(required=False, allow_blank=True, default="")
    issued_date = serializers.DateField(required=False, allow_null=True, default=None)
