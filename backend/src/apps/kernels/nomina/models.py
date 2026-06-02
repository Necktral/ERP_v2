from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Tasas INSS Nicaragua (configurables por período pero con defaults fijos)
# ---------------------------------------------------------------------------

INSS_LABORAL_RATE = Decimal("0.07")       # 7% — descuento al trabajador
INSS_PATRONAL_RATE = Decimal("0.225")     # 22.5% — costo empresa
INATEC_RATE = Decimal("0.02")             # 2% — costo empresa
VACATION_RATE = Decimal("0.083333")       # 8.33% mensual
THIRTEENTH_MONTH_RATE = Decimal("0.083333")  # 8.33% mensual


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class PeriodType(models.TextChoices):
    FIRST_HALF = "FIRST_HALF", "Primera quincena (1-15)"
    SECOND_HALF = "SECOND_HALF", "Segunda quincena (16-fin)"
    MONTHLY = "MONTHLY", "Mensual"


class PeriodStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    IN_REVIEW = "IN_REVIEW", "En revisión"
    APPROVED = "APPROVED", "Aprobado"
    PAID = "PAID", "Pagado"
    CLOSED = "CLOSED", "Cerrado"



class SheetStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    SUBMITTED = "SUBMITTED", "Enviada al encargado"
    REVIEWED = "REVIEWED", "Revisada"
    APPROVED = "APPROVED", "Aprobada"
    REJECTED = "REJECTED", "Rechazada"


class SalaryType(models.TextChoices):
    MONTHLY = "MONTHLY", "Mensual"
    DAILY = "DAILY", "Por día"
    HOURLY = "HOURLY", "Por hora"


class AttendanceSource(models.TextChoices):
    BIOMETRIC = "BIOMETRIC", "Control biométrico"
    SUPERVISOR_APP = "SUPERVISOR_APP", "Reporte jefe de área (app)"
    PAYROLL_REVIEW = "PAYROLL_REVIEW", "Revisión encargado de nómina"
    MANUAL = "MANUAL", "Manual (eventualidad)"


class AttendanceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    SUBMITTED = "SUBMITTED", "Enviado"
    REVIEWED = "REVIEWED", "Revisado"
    APPROVED = "APPROVED", "Aprobado"
    CONFLICT = "CONFLICT", "Conflicto (requiere resolución)"


class AbsenceReason(models.TextChoices):
    NONE = "NONE", "Sin ausencia"
    SICK = "SICK", "Enfermedad"
    ACCIDENT = "ACCIDENT", "Accidente de trabajo"
    TRANSFERRED = "TRANSFERRED", "Traslado a otra zona"
    DISMISSED = "DISMISSED", "Despedido"
    PERSONAL = "PERSONAL", "Permiso personal"
    INSS_SUBSIDY = "INSS_SUBSIDY", "Subsidio INSS (enfermedad)"
    HOLIDAY = "HOLIDAY", "Feriado"
    VACATION = "VACATION", "Vacaciones"


# ---------------------------------------------------------------------------
# PayrollPeriod — La quincena
# ---------------------------------------------------------------------------

class PayrollPeriod(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="payroll_periods_company")

    year = models.PositiveSmallIntegerField(db_index=True)
    month = models.PositiveSmallIntegerField()
    period_type = models.CharField(max_length=16, choices=PeriodType.choices)

    start_date = models.DateField()
    end_date = models.DateField()
    working_days = models.PositiveSmallIntegerField(default=15)

    # Tasa de cambio fija para todo el período (Nicaragua la mantiene estable)
    exchange_rate_usd = models.DecimalField(
        max_digits=10, decimal_places=4, default=Decimal("36.6243"),
        help_text="Tasa USD→NIO vigente para este período"
    )

    status = models.CharField(max_length=12, choices=PeriodStatus.choices, default=PeriodStatus.DRAFT, db_index=True)

    # Totales consolidados (calculados al cerrar)
    total_gross = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_deductions = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_net = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_patronal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_payroll_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="payroll_periods_created"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="payroll_periods_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "year", "month", "period_type"],
                name="uq_nomina_period"
            ),
            models.CheckConstraint(
                condition=models.Q(month__gte=1, month__lte=12),
                name="ck_nomina_period_month"
            ),
        ]
        indexes = [
            models.Index(fields=["company", "year", "month", "period_type"], name="ix_nom_period_scope"),
            models.Index(fields=["company", "status"], name="ix_nom_period_st"),
        ]

    def __str__(self) -> str:
        return f"{self.company} — {self.year}/{self.month:02d} {self.period_type}"

    def clean(self) -> None:
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "end_date debe ser posterior a start_date."})


# ---------------------------------------------------------------------------
# PayrollSheet — Sub-planilla por área
# ---------------------------------------------------------------------------

class PayrollSheet(models.Model):
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="sheets")

    # La sucursal/empresa que genera esta sub-planilla
    branch = models.ForeignKey(
        "iam.OrgUnit", null=True, blank=True,
        on_delete=models.PROTECT, related_name="payroll_sheets_branch",
        help_text="Empresa o sucursal que genera esta planilla"
    )

    # Nombre libre — cada empresa/área lo nombra como quiere
    sheet_name = models.CharField(
        max_length=160, blank=True, default="",
        help_text="Nombre de la planilla (ej: 'Planilla Finca Abisinia', 'Comisariato Santa Isabel')"
    )

    has_inss = models.BooleanField(default=True, help_text="True = planilla CON INSS")
    status = models.CharField(max_length=12, choices=SheetStatus.choices, default=SheetStatus.DRAFT, db_index=True)

    notes = models.TextField(blank=True, default="")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="payroll_sheets_submitted"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="payroll_sheets_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        indexes = [
            models.Index(fields=["period", "has_inss"], name="ix_nom_sheet_p_inss"),
            models.Index(fields=["period", "status"], name="ix_nom_sheet_p_st"),
            models.Index(fields=["branch", "period"], name="ix_nom_sheet_br_p"),
        ]

    def __str__(self) -> str:
        inss_label = "CON INSS" if self.has_inss else "SIN INSS"
        return f"{self.sheet_name} [{inss_label}]"


# ---------------------------------------------------------------------------
# PayrollEntry — Una línea por empleado en la planilla
# ---------------------------------------------------------------------------

class PayrollEntry(models.Model):
    sheet = models.ForeignKey(PayrollSheet, on_delete=models.PROTECT, related_name="entries")
    employee = models.ForeignKey(
        "hr.Employee", null=True, blank=True,
        on_delete=models.PROTECT, related_name="payroll_entries"
    )

    # Snapshot del empleado al momento de la planilla
    inss_number = models.CharField(max_length=20, blank=True, default="")
    cedula = models.CharField(max_length=20, blank=True, default="")
    full_name = models.CharField(max_length=160)
    gender = models.CharField(max_length=1, choices=[("M", "Masculino"), ("F", "Femenino")], blank=True, default="")
    cargo = models.CharField(max_length=120, blank=True, default="")

    has_inss = models.BooleanField(default=True)
    salary_type = models.CharField(max_length=8, choices=SalaryType.choices, default=SalaryType.MONTHLY)
    payment_frequency = models.CharField(max_length=12, choices=PeriodType.choices, default=PeriodType.FIRST_HALF)

    # Salario base
    base_salary_usd = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    base_salary_nio = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("36.6243"))
    daily_rate_nio = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))

    # Asistencia
    days_in_period = models.PositiveSmallIntegerField(default=15)
    days_worked = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("15.00"))
    days_subsidy = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text="Días cubiertos por INSS (enfermedad)"
    )
    subsidy_daily_rate = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    sunday_worked_days = models.PositiveSmallIntegerField(default=0)

    # --- INGRESOS (todos calculados, almacenados para auditoría) ---
    quincenal_salary = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    subsidy_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    overtime_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    sunday_bonus_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    vacation_provision = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    thirteenth_month_provision = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    other_income = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_income = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    # --- RETENCIONES ---
    inss_laboral = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    ir_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    loan_payment = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
        help_text="Abono a préstamos (del kernel portfolio)"
    )
    food_deduction = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    advance_deduction = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
        help_text="Adelanto finca"
    )
    store_credit_deduction = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
        help_text="Crédito comisariato"
    )
    other_deductions = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_deductions = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    # --- NETO ---
    total_devengado = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    net_to_pay = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    # --- COSTOS PATRONALES ---
    inss_patronal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    inatec = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    vacation_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    thirteenth_month_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_employer_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_payroll_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(
                fields=["sheet", "cedula"],
                condition=~models.Q(cedula=""),
                name="uq_nom_entry_sheet_cedula"
            ),
        ]
        indexes = [
            models.Index(fields=["sheet"], name="ix_nom_entry_sheet"),
            models.Index(fields=["employee"], name="ix_nom_entry_emp"),
            models.Index(fields=["inss_number"], name="ix_nom_entry_inss"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} — {self.sheet}"

    def calculate_daily_rate(self) -> Decimal:
        """Calcula el salario diario en NIO."""
        monthly = self.base_salary_nio
        if self.base_salary_usd and self.exchange_rate:
            monthly = (self.base_salary_usd * self.exchange_rate).quantize(Decimal("0.01"))
        return (monthly / Decimal("30")).quantize(Decimal("0.000001"))

    def compute_all(self) -> None:
        """Recalcula todos los campos de la línea según las tasas Nicaragua."""
        from decimal import ROUND_HALF_UP

        Q2 = Decimal("0.01")
        Q6 = Decimal("0.000001")

        def _r2(x): return Decimal(str(x)).quantize(Q2, rounding=ROUND_HALF_UP)
        def _r6(x): return Decimal(str(x)).quantize(Q6, rounding=ROUND_HALF_UP)

        # 1. Salario base mensual en NIO
        if self.base_salary_usd and self.exchange_rate:
            monthly_nio = _r2(self.base_salary_usd * self.exchange_rate)
            self.base_salary_nio = monthly_nio
        else:
            monthly_nio = self.base_salary_nio

        # 2. Salario diario
        self.daily_rate_nio = _r6(monthly_nio / Decimal("30"))

        # 3. Salario quincenal proporcional a días trabajados
        period_days = Decimal(str(self.days_in_period or 15))
        worked = Decimal(str(self.days_worked))
        quincenal_base = _r2(monthly_nio / 2)

        if worked < period_days:
            self.quincenal_salary = _r2(self.daily_rate_nio * worked)
        else:
            self.quincenal_salary = quincenal_base

        # 4. Subsidio INSS
        subsidy_days = Decimal(str(self.days_subsidy))
        if subsidy_days > 0:
            if not self.subsidy_daily_rate or self.subsidy_daily_rate == 0:
                self.subsidy_daily_rate = self.daily_rate_nio
            self.subsidy_amount = _r2(self.subsidy_daily_rate * subsidy_days)
        else:
            self.subsidy_amount = Decimal("0.00")

        # 5. Horas extra (tarifa 2x del diario dividido en 8 horas)
        hourly_rate = _r6(self.daily_rate_nio / 8)
        self.overtime_amount = _r2(hourly_rate * Decimal("2") * Decimal(str(self.overtime_hours)))

        # 6. Domingos laborados (tarifa doble)
        self.sunday_bonus_amount = _r2(self.daily_rate_nio * Decimal(str(self.sunday_worked_days)))

        # 7. Provisiones (se calculan sobre salario mensual proporcional)
        monthly_proportional = _r2(self.daily_rate_nio * worked * 2)
        self.vacation_provision = _r2(monthly_proportional * VACATION_RATE)
        self.thirteenth_month_provision = _r2(monthly_proportional * THIRTEENTH_MONTH_RATE)

        # 8. Total ingresos
        self.total_income = _r2(
            self.quincenal_salary + self.subsidy_amount +
            self.overtime_amount + self.sunday_bonus_amount +
            self.vacation_provision + self.thirteenth_month_provision +
            self.other_income
        )

        # 9. Retenciones
        if self.has_inss:
            self.inss_laboral = _r2(self.quincenal_salary * INSS_LABORAL_RATE)
        else:
            self.inss_laboral = Decimal("0.00")

        self.total_deductions = _r2(
            self.inss_laboral + self.ir_amount + self.loan_payment +
            self.food_deduction + self.advance_deduction +
            self.store_credit_deduction + self.other_deductions
        )

        # 10. Neto
        self.total_devengado = _r2(self.quincenal_salary + self.subsidy_amount +
                                    self.overtime_amount + self.sunday_bonus_amount)
        self.net_to_pay = _r2(self.total_devengado - self.total_deductions)

        # 11. Costos patronales
        if self.has_inss:
            self.inss_patronal = _r2(self.quincenal_salary * INSS_PATRONAL_RATE)
            self.inatec = _r2(self.quincenal_salary * INATEC_RATE)
        else:
            self.inss_patronal = Decimal("0.00")
            self.inatec = Decimal("0.00")

        self.vacation_cost = self.vacation_provision
        self.thirteenth_month_cost = self.thirteenth_month_provision
        self.total_employer_cost = _r2(
            self.inss_patronal + self.inatec +
            self.vacation_cost + self.thirteenth_month_cost
        )
        self.total_payroll_cost = _r2(self.net_to_pay + self.total_employer_cost)


# ---------------------------------------------------------------------------
# AttendanceReport — Reporte de asistencia (4 fuentes)
# ---------------------------------------------------------------------------

class AttendanceReport(models.Model):
    report_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="attendance_reports_company")
    branch = models.ForeignKey(
        "iam.OrgUnit", null=True, blank=True,
        on_delete=models.PROTECT, related_name="attendance_reports_branch"
    )
    period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="attendance_reports")
    employee = models.ForeignKey(
        "hr.Employee", null=True, blank=True,
        on_delete=models.PROTECT, related_name="attendance_reports"
    )

    # Para trabajadores sin registro HR
    employee_name = models.CharField(max_length=160, blank=True, default="")
    inss_number = models.CharField(max_length=20, blank=True, default="")
    cedula = models.CharField(max_length=20, blank=True, default="")

    source = models.CharField(max_length=20, choices=AttendanceSource.choices, db_index=True)
    status = models.CharField(max_length=12, choices=AttendanceStatus.choices, default=AttendanceStatus.DRAFT, db_index=True)

    # --- Asistencia ---
    days_worked = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    days_absent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    days_sick = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    days_subsidy = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    days_accident = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    days_transferred = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    days_vacation = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    sunday_worked_days = models.PositiveSmallIntegerField(default=0)

    # --- Observaciones del jefe de área ---
    observations = models.TextField(blank=True, default="")
    sick_reason = models.CharField(max_length=255, blank=True, default="")
    accident_description = models.TextField(blank=True, default="")
    transfer_destination = models.CharField(max_length=120, blank=True, default="")
    dismissal_reason = models.CharField(max_length=255, blank=True, default="")

    # --- Workflow de aprobación ---
    # Nivel 1: quien lo captura (biométrico automático o jefe de área)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="attendance_submitted"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    # Nivel 2/3: revisión encargado de nómina
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="attendance_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Nivel final: jefe de área tiene la última palabra
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="attendance_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Conflicto entre fuentes
    has_conflict = models.BooleanField(default=False, db_index=True)
    conflict_note = models.TextField(blank=True, default="")
    conflict_resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="attendance_conflict_resolved"
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        indexes = [
            models.Index(fields=["company", "period", "source"], name="ix_att_c_p_src"),
            models.Index(fields=["period", "status"], name="ix_att_p_st"),
            models.Index(fields=["employee", "period"], name="ix_att_emp_p"),
            models.Index(fields=["company", "has_conflict"], name="ix_att_c_conflict"),
        ]

    def __str__(self) -> str:
        name = self.employee.full_name if self.employee_id else self.employee_name
        return f"{name} | {self.period} [{self.source}]"


# ---------------------------------------------------------------------------
# PayrollPayment — Registro de pago por empleado
# ---------------------------------------------------------------------------

class PayrollPaymentMethod(models.TextChoices):
    CASH = "CASH", "Efectivo"
    BANK_TRANSFER = "BANK_TRANSFER", "Transferencia bancaria"
    CHECK = "CHECK", "Cheque"


class PayrollPayment(models.Model):
    entry = models.ForeignKey(PayrollEntry, on_delete=models.PROTECT, related_name="payments")
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="payroll_payments_company")

    payment_method = models.CharField(max_length=16, choices=PayrollPaymentMethod.choices, default=PayrollPaymentMethod.CASH)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_date = models.DateField(db_index=True)
    reference = models.CharField(max_length=96, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="payroll_payments_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="ck_paypay_positive"),
        ]
        indexes = [
            models.Index(fields=["company", "payment_date"], name="ix_paypay_c_pd"),
        ]


# ---------------------------------------------------------------------------
# PayrollLoanDeduction — Link con kernel portfolio (CxC)
# ---------------------------------------------------------------------------

class PayrollLoanDeduction(models.Model):
    """Liga un abono de nómina con el crédito correspondiente en el kernel portfolio."""

    entry = models.ForeignKey(PayrollEntry, on_delete=models.PROTECT, related_name="loan_deductions")
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="payroll_loan_deductions")

    # FK al registro de crédito/CxC en el kernel portfolio
    credit_id = models.PositiveIntegerField(
        db_index=True, help_text="ID del Credit o Receivable en el kernel portfolio"
    )
    credit_type = models.CharField(
        max_length=16, default="CREDIT",
        help_text="'CREDIT' o 'RECEIVABLE' según el modelo del portfolio kernel"
    )

    amount_deducted = models.DecimalField(max_digits=18, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_deducted__gt=0), name="ck_loandeduc_positive"),
        ]
        indexes = [
            models.Index(fields=["credit_id", "credit_type"], name="ix_loandeduc_credit"),
        ]
