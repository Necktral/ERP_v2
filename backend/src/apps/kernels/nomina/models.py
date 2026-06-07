from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Defaults Nicaragua — se usan cuando no hay NominaConfig activa
# ---------------------------------------------------------------------------

DEFAULT_INSS_LABORAL = Decimal("0.07")
DEFAULT_INSS_PATRONAL_SMALL = Decimal("0.215")   # < 50 trabajadores
DEFAULT_INSS_PATRONAL_LARGE = Decimal("0.225")   # >= 50 trabajadores
DEFAULT_INSS_SIZE_THRESHOLD = 50
DEFAULT_INATEC = Decimal("0.02")
DEFAULT_VACATION_RATE = Decimal("0.083333")
DEFAULT_THIRTEENTH_RATE = Decimal("0.083333")
DEFAULT_OVERTIME_RATE = Decimal("2.0")            # 2x el valor hora
DEFAULT_SUNDAY_RATE = Decimal("2.0")              # 2x el salario diario
DEFAULT_SUBSIDY_EMPLOYER_DAYS = 3                 # días 1-3 paga empresa
DEFAULT_SUBSIDY_INSS_RATE = Decimal("0.60")       # 60% desde día 4
DEFAULT_MIN_WAGE_AGRO = Decimal("6188.02")        # sector agropecuario 2026


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------

class PeriodType(models.TextChoices):
    FIRST_HALF = "FIRST_HALF", "Primera quincena (1-15)"
    SECOND_HALF = "SECOND_HALF", "Segunda quincena (16-fin)"
    CATORCENA = "CATORCENA", "Catorcena"
    MONTHLY = "MONTHLY", "Mensual"


def periods_per_year(period_type: str) -> int:
    """Cantidad de períodos de pago por año según la frecuencia.

    Catorcenal = 26 (cada 14 días); quincenal (1ra/2da) = 24; mensual = 12.
    Driver del IR para no anualizar incorrectamente una planilla catorcenal.
    """
    return {
        PeriodType.MONTHLY: 12,
        PeriodType.FIRST_HALF: 24,
        PeriodType.SECOND_HALF: 24,
        PeriodType.CATORCENA: 26,
    }.get(period_type, 24)


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


class FieldWorkDayStatus(models.TextChoices):
    OPEN = "OPEN", "Abierto"
    ROLLCALL_SUBMITTED = "ROLLCALL_SUBMITTED", "Lista enviada"
    CREW_REPORTS_PENDING = "CREW_REPORTS_PENDING", "Reportes pendientes"
    IN_REVIEW = "IN_REVIEW", "En revision"
    APPROVED = "APPROVED", "Aprobado"
    LOCKED = "LOCKED", "Bloqueado"


class FieldRollCallLineStatus(models.TextChoices):
    PRESENT = "PRESENT", "Presente"
    ABSENT = "ABSENT", "Ausente"
    UNKNOWN = "UNKNOWN", "No confirmado"


class FieldCrewReportStatus(models.TextChoices):
    DRAFT = "DRAFT", "Borrador"
    SUBMITTED = "SUBMITTED", "Enviado"
    RETURNED_FOR_CORRECTION = "RETURNED_FOR_CORRECTION", "Devuelto"
    REVIEWED = "REVIEWED", "Revisado"
    APPROVED = "APPROVED", "Aprobado"
    REJECTED = "REJECTED", "Rechazado"


class FieldWorkerEventType(models.TextChoices):
    PRESENT = "PRESENT", "Presente"
    ABSENT = "ABSENT", "Ausente"
    SICK = "SICK", "Enfermo"
    ACCIDENT = "ACCIDENT", "Accidente"
    TRANSFERRED = "TRANSFERRED", "Trasladado"
    PERMISSION = "PERMISSION", "Permiso"
    LEFT_EARLY = "LEFT_EARLY", "Salio temprano"
    JOINED_LATE = "JOINED_LATE", "Ingreso tarde"
    DISMISSED = "DISMISSED", "Despedido"
    OTHER = "OTHER", "Otro"


class FieldAttendanceConsolidationStatus(models.TextChoices):
    OK = "OK", "OK"
    WARNING = "WARNING", "Advertencia"
    CONFLICT = "CONFLICT", "Conflicto"
    BLOCKED = "BLOCKED", "Bloqueado"
    APPROVED = "APPROVED", "Aprobado"
    LOCKED_FOR_PAYROLL = "LOCKED_FOR_PAYROLL", "Bloqueado para nomina"


# ---------------------------------------------------------------------------
# NominaConfig — Configuración de tasas por empresa y año fiscal
# ---------------------------------------------------------------------------

class NominaConfig(models.Model):
    """
    Configuración flexible de tasas y parámetros de nómina por empresa.

    Permite actualizar las tasas INSS, IR, salario mínimo, etc. sin
    cambiar código. Cada registro es una versión vigente a partir de
    effective_from. El sistema usa la versión más reciente activa.
    """

    company = models.ForeignKey(
        "iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_configs"
    )
    fiscal_year = models.PositiveSmallIntegerField(db_index=True, help_text="Año fiscal vigente")
    effective_from = models.DateField(db_index=True, help_text="Fecha desde la que aplica esta configuración")
    is_active = models.BooleanField(default=True, db_index=True)

    # --- INSS Laboral (deducción al trabajador) ---
    inss_laboral_rate = models.DecimalField(
        max_digits=6, decimal_places=5, default=DEFAULT_INSS_LABORAL,
        help_text="Tasa INSS laboral (ej. 0.07000 = 7%)"
    )

    # --- INSS Patronal (costo empresa) ---
    # Nicaragua tiene dos tasas según tamaño de empresa
    inss_patronal_rate_small = models.DecimalField(
        max_digits=6, decimal_places=5, default=DEFAULT_INSS_PATRONAL_SMALL,
        help_text="INSS patronal para empresas < umbral de trabajadores (ej. 0.21500 = 21.5%)"
    )
    inss_patronal_rate_large = models.DecimalField(
        max_digits=6, decimal_places=5, default=DEFAULT_INSS_PATRONAL_LARGE,
        help_text="INSS patronal para empresas >= umbral de trabajadores (ej. 0.22500 = 22.5%)"
    )
    inss_size_threshold = models.PositiveSmallIntegerField(
        default=DEFAULT_INSS_SIZE_THRESHOLD,
        help_text="Número de trabajadores a partir del cual aplica la tasa 'large'"
    )

    # --- INATEC ---
    inatec_rate = models.DecimalField(
        max_digits=6, decimal_places=5, default=DEFAULT_INATEC,
        help_text="Tasa INATEC (ej. 0.02000 = 2%)"
    )

    # --- Prestaciones ---
    vacation_rate = models.DecimalField(
        max_digits=8, decimal_places=6, default=DEFAULT_VACATION_RATE,
        help_text="Tasa provisión vacaciones mensual (ej. 0.083333 = 8.33%)"
    )
    thirteenth_month_rate = models.DecimalField(
        max_digits=8, decimal_places=6, default=DEFAULT_THIRTEENTH_RATE,
        help_text="Tasa provisión 13vo mes mensual (ej. 0.083333 = 8.33%)"
    )

    # --- Horas extras y 7mo día ---
    overtime_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=DEFAULT_OVERTIME_RATE,
        help_text="Multiplicador horas extra sobre tarifa hora (ej. 2.00 = doble)"
    )
    sunday_bonus_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=DEFAULT_SUNDAY_RATE,
        help_text="Multiplicador domingos laborados (ej. 2.00 = doble)"
    )
    seventh_day_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.00"),
        help_text="Multiplicador 7mo día de descanso (ej. 1.00 = salario normal)"
    )

    # --- Subsidio por enfermedad ---
    subsidy_employer_days = models.PositiveSmallIntegerField(
        default=DEFAULT_SUBSIDY_EMPLOYER_DAYS,
        help_text="Días de enfermedad que paga la empresa al 100% (antes de aplicar INSS)"
    )
    subsidy_inss_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=DEFAULT_SUBSIDY_INSS_RATE,
        help_text="Porcentaje que paga el INSS desde el día N+1 (ej. 0.6000 = 60%)"
    )

    # --- Salario mínimo por sector ---
    min_wage_agro = models.DecimalField(
        max_digits=12, decimal_places=2, default=DEFAULT_MIN_WAGE_AGRO,
        help_text="Salario mínimo sector agropecuario (C$/mes)"
    )
    min_wage_general = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("7000.00"),
        help_text="Salario mínimo sector servicios/general (C$/mes)"
    )

    # --- Pago al INSS ---
    payment_deadline_days = models.PositiveSmallIntegerField(
        default=10,
        help_text="Días hábiles del mes siguiente para pagar al INSS"
    )
    late_payment_surcharge = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.03"),
        help_text="Recargo por mora (ej. 0.0300 = 3%)"
    )

    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="nomina_configs_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "fiscal_year", "effective_from"],
                name="uq_nomina_config_company_year_date"
            ),
        ]
        indexes = [
            models.Index(fields=["company", "fiscal_year", "is_active"], name="ix_nomcfg_c_y_a"),
        ]
        ordering = ["-effective_from"]

    def __str__(self) -> str:
        return f"Config Nómina {self.company} / {self.fiscal_year} (desde {self.effective_from})"

    @classmethod
    def get_active(cls, *, company, date=None) -> "NominaConfig | None":
        """Retorna la configuración activa más reciente para la empresa y fecha dadas."""
        from django.utils import timezone as tz
        ref_date = date or tz.localdate()
        return (
            cls.objects.filter(
                company=company,
                is_active=True,
                effective_from__lte=ref_date,
            )
            .order_by("-effective_from")
            .first()
        )

    def get_inss_patronal_rate(self, *, worker_count: int) -> Decimal:
        """Retorna la tasa patronal según el número de trabajadores activos."""
        if worker_count >= self.inss_size_threshold:
            return self.inss_patronal_rate_large
        return self.inss_patronal_rate_small


# ---------------------------------------------------------------------------
# IRBracket — Tabla progresiva del IR laboral (configurable por año)
# ---------------------------------------------------------------------------

class IRBracket(models.Model):
    """
    Un tramo de la tabla progresiva del IR laboral de Nicaragua.
    Se registra una fila por cada tramo. Se configura por empresa y año.

    Ejemplo Nicaragua 2026:
      tramo 1: 0 – 100,000  →  base=0,       tasa=0%
      tramo 2: 100,001 – 200,000 → base=0,    tasa=15%
      tramo 3: 200,001 – 350,000 → base=15000, tasa=20%
      tramo 4: 350,001 – 500,000 → base=45000, tasa=25%
      tramo 5: 500,001+          → base=82500, tasa=30%

    Los montos son ANUALES. El sistema calcula mensual/quincenal dividiendo.
    """

    config = models.ForeignKey(
        NominaConfig, on_delete=models.CASCADE, related_name="ir_brackets"
    )
    order = models.PositiveSmallIntegerField(help_text="Orden del tramo (1, 2, 3...)")

    min_income = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text="Ingreso anual mínimo de este tramo (C$)"
    )
    max_income = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Ingreso anual máximo (null = sin límite superior)"
    )
    base_tax = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00"),
        help_text="Impuesto fijo del tramo (C$)"
    )
    rate = models.DecimalField(
        max_digits=6, decimal_places=5, default=Decimal("0.00"),
        help_text="Tasa marginal sobre el exceso (ej. 0.15000 = 15%)"
    )

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(fields=["config", "order"], name="uq_irbracket_config_order"),
        ]
        ordering = ["order"]

    def __str__(self) -> str:
        max_str = f"– {self.max_income:,.0f}" if self.max_income else "+"
        return f"IR Tramo {self.order}: {self.min_income:,.0f} {max_str} → {self.rate*100:.0f}%"

    @classmethod
    def calculate_annual_ir(cls, *, config: "NominaConfig", annual_income: Decimal) -> Decimal:
        """Calcula el IR anual dado un ingreso anual bruto."""
        brackets = cls.objects.filter(config=config).order_by("order")
        ir = Decimal("0.00")
        for bracket in brackets:
            if annual_income <= bracket.min_income:
                break
            excess = annual_income - bracket.min_income
            if bracket.max_income is not None:
                excess = min(excess, bracket.max_income - bracket.min_income)
            ir = bracket.base_tax + (excess * bracket.rate)
        return ir.quantize(Decimal("0.01"))

    @classmethod
    def calculate_period_ir(
        cls, *, config: "NominaConfig", period_income: Decimal, periods_per_year: int = 24
    ) -> Decimal:
        """IR del período: anualiza por la frecuencia REAL, calcula IR anual y retorna la porción del período.

        period_income × periods_per_year = ingreso anual estimado. Para una planilla catorcenal
        periods_per_year=26 (no 24), de lo contrario el impuesto saldría incorrecto.
        """
        ppy = int(periods_per_year) or 24
        annual = period_income * Decimal(ppy)
        annual_ir = cls.calculate_annual_ir(config=config, annual_income=annual)
        return (annual_ir / Decimal(ppy)).quantize(Decimal("0.01"))

    @classmethod
    def calculate_quincenal_ir(cls, *, config: "NominaConfig", quincenal_income: Decimal) -> Decimal:
        """Compat: IR quincenal (×24). Preferir calculate_period_ir con la frecuencia real."""
        return cls.calculate_period_ir(config=config, period_income=quincenal_income, periods_per_year=24)


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

    def compute_all(self, *, config: "NominaConfig | None" = None, worker_count: int = 999) -> None:
        """
        Recalcula todos los campos usando la NominaConfig activa.
        Si no se pasa config, usa los defaults de Nicaragua.

        Args:
            config: NominaConfig activa para la empresa. Si None usa defaults.
            worker_count: Número de trabajadores activos (para elegir tasa patronal).
        """
        from decimal import ROUND_HALF_UP

        Q2 = Decimal("0.01")
        Q6 = Decimal("0.000001")

        def _r2(x): return Decimal(str(x)).quantize(Q2, rounding=ROUND_HALF_UP)
        def _r6(x): return Decimal(str(x)).quantize(Q6, rounding=ROUND_HALF_UP)

        # Tasas — desde config o defaults
        if config:
            inss_laboral_rate = config.inss_laboral_rate
            inss_patronal_rate = config.get_inss_patronal_rate(worker_count=worker_count)
            inatec_rate = config.inatec_rate
            vacation_rate = config.vacation_rate
            thirteenth_rate = config.thirteenth_month_rate
            overtime_rate = config.overtime_rate
            sunday_rate = config.sunday_bonus_rate
            subsidy_inss_rate = config.subsidy_inss_rate
        else:
            inss_laboral_rate = DEFAULT_INSS_LABORAL
            inss_patronal_rate = DEFAULT_INSS_PATRONAL_LARGE
            inatec_rate = DEFAULT_INATEC
            vacation_rate = DEFAULT_VACATION_RATE
            thirteenth_rate = DEFAULT_THIRTEENTH_RATE
            overtime_rate = DEFAULT_OVERTIME_RATE
            sunday_rate = DEFAULT_SUNDAY_RATE
            subsidy_inss_rate = DEFAULT_SUBSIDY_INSS_RATE

        # 1. Salario base mensual en NIO
        if self.base_salary_usd and self.exchange_rate:
            monthly_nio = _r2(self.base_salary_usd * self.exchange_rate)
            self.base_salary_nio = monthly_nio
        else:
            monthly_nio = self.base_salary_nio

        # 2. Salario diario (base: mes de 30 días)
        self.daily_rate_nio = _r6(monthly_nio / Decimal("30"))

        # 3. Salario quincenal proporcional a días trabajados
        period_days = Decimal(str(self.days_in_period or 15))
        worked = Decimal(str(self.days_worked))
        quincenal_base = _r2(monthly_nio / 2)

        self.quincenal_salary = _r2(self.daily_rate_nio * worked) if worked < period_days else quincenal_base

        # 4. Subsidio INSS (empresa paga 100% días 1-N, INSS paga 60% desde día N+1)
        subsidy_days = Decimal(str(self.days_subsidy))
        if subsidy_days > 0:
            if not self.subsidy_daily_rate or self.subsidy_daily_rate == 0:
                self.subsidy_daily_rate = self.daily_rate_nio
            self.subsidy_amount = _r2(self.subsidy_daily_rate * subsidy_days * subsidy_inss_rate)
        else:
            self.subsidy_amount = Decimal("0.00")

        # 5. Horas extra
        hourly_rate = _r6(self.daily_rate_nio / 8)
        self.overtime_amount = _r2(hourly_rate * overtime_rate * Decimal(str(self.overtime_hours)))

        # 6. Domingos laborados
        self.sunday_bonus_amount = _r2(self.daily_rate_nio * sunday_rate * Decimal(str(self.sunday_worked_days)))

        # 7. Provisiones (sobre salario mensual proporcional a días trabajados)
        monthly_proportional = _r2(self.daily_rate_nio * worked * 2)
        self.vacation_provision = _r2(monthly_proportional * vacation_rate)
        self.thirteenth_month_provision = _r2(monthly_proportional * thirteenth_rate)

        # 8. Total ingresos
        self.total_income = _r2(
            self.quincenal_salary + self.subsidy_amount +
            self.overtime_amount + self.sunday_bonus_amount +
            self.vacation_provision + self.thirteenth_month_provision +
            self.other_income
        )

        # 9. IR — calculado si hay config con tabla IR, si no = 0.
        # Anualiza por la frecuencia REAL del pago (catorcena ×26, no ×24).
        if config and not self.ir_amount:
            self.ir_amount = IRBracket.calculate_period_ir(
                config=config,
                period_income=self.quincenal_salary,
                periods_per_year=periods_per_year(self.payment_frequency),
            )

        # 10. Retenciones
        if self.has_inss:
            self.inss_laboral = _r2(self.quincenal_salary * inss_laboral_rate)
        else:
            self.inss_laboral = Decimal("0.00")

        self.total_deductions = _r2(
            self.inss_laboral + self.ir_amount + self.loan_payment +
            self.food_deduction + self.advance_deduction +
            self.store_credit_deduction + self.other_deductions
        )

        # 11. Neto
        self.total_devengado = _r2(
            self.quincenal_salary + self.subsidy_amount +
            self.overtime_amount + self.sunday_bonus_amount
        )
        self.net_to_pay = _r2(self.total_devengado - self.total_deductions)

        # 12. Costos patronales
        if self.has_inss:
            self.inss_patronal = _r2(self.quincenal_salary * inss_patronal_rate)
            self.inatec = _r2(self.quincenal_salary * inatec_rate)
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
        employee = self.employee if self.employee_id else None
        name = self.employee_name
        if employee is not None and not name:
            name = f"{employee.first_name} {employee.last_name}".strip()
        return f"{name} | {self.period} [{self.source}]"


# ---------------------------------------------------------------------------
# Field Attendance — Control diario de asistencia de campo
# ---------------------------------------------------------------------------

class FieldWorkDay(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="field_work_days_company")
    branch = models.ForeignKey(
        "iam.OrgUnit", null=True, blank=True,
        on_delete=models.PROTECT, related_name="field_work_days_branch"
    )
    payroll_period = models.ForeignKey(
        PayrollPeriod, null=True, blank=True,
        on_delete=models.PROTECT, related_name="field_work_days"
    )
    work_date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=24, choices=FieldWorkDayStatus.choices,
        default=FieldWorkDayStatus.OPEN, db_index=True
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="field_work_days_opened"
    )
    opened_at = models.DateTimeField(default=timezone.now, editable=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="field_work_days_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "work_date"],
                condition=models.Q(branch__isnull=True),
                name="uq_fwd_c_date_null_branch",
            ),
            models.UniqueConstraint(
                fields=["company", "branch", "work_date"],
                condition=models.Q(branch__isnull=False),
                name="uq_fwd_c_branch_date",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "work_date"], name="ix_fwd_c_b_date"),
            models.Index(fields=["company", "status"], name="ix_fwd_c_status"),
            models.Index(fields=["payroll_period", "status"], name="ix_fwd_period_status"),
        ]

    def __str__(self) -> str:
        branch = f" / {self.branch}" if self.branch_id else ""
        return f"{self.company}{branch} | {self.work_date}"


class FieldRollCall(models.Model):
    work_day = models.OneToOneField(FieldWorkDay, on_delete=models.PROTECT, related_name="rollcall")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="field_rollcalls_submitted"
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        indexes = [
            models.Index(fields=["submitted_by", "submitted_at"], name="ix_frc_submitter_at"),
        ]

    def __str__(self) -> str:
        return f"Rollcall {self.work_day}"


class FieldRollCallLine(models.Model):
    rollcall = models.ForeignKey(FieldRollCall, on_delete=models.CASCADE, related_name="lines")
    employee = models.ForeignKey("hr.Employee", on_delete=models.PROTECT, related_name="field_rollcall_lines")
    status = models.CharField(
        max_length=12, choices=FieldRollCallLineStatus.choices,
        default=FieldRollCallLineStatus.UNKNOWN, db_index=True
    )
    absence_reason = models.CharField(max_length=64, blank=True, default="")
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(fields=["rollcall", "employee"], name="uq_frl_rollcall_employee"),
        ]
        indexes = [
            models.Index(fields=["employee", "status"], name="ix_frl_employee_status"),
        ]


class FieldCrew(models.Model):
    work_day = models.ForeignKey(FieldWorkDay, on_delete=models.PROTECT, related_name="crews")
    name = models.CharField(max_length=160)
    supervisor_employee = models.ForeignKey(
        "hr.Employee", on_delete=models.PROTECT, related_name="field_crews_supervised"
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(fields=["work_day", "name"], name="uq_fc_workday_name"),
        ]
        indexes = [
            models.Index(fields=["work_day", "supervisor_employee"], name="ix_fc_workday_supervisor"),
        ]

    def __str__(self) -> str:
        return f"{self.name} | {self.work_day}"


class FieldCrewReport(models.Model):
    crew = models.OneToOneField(FieldCrew, on_delete=models.PROTECT, related_name="report")
    status = models.CharField(
        max_length=24, choices=FieldCrewReportStatus.choices,
        default=FieldCrewReportStatus.DRAFT, db_index=True
    )
    labor_code = models.CharField(max_length=64, blank=True, default="")
    labor_name = models.CharField(max_length=160, blank=True, default="")
    zone_label = models.CharField(max_length=160, blank=True, default="")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="field_crew_reports_submitted"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="field_crew_reports_reviewed"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        indexes = [
            models.Index(fields=["status"], name="ix_fcr_status"),
            models.Index(fields=["submitted_by", "submitted_at"], name="ix_fcr_submitter_at"),
        ]

    def __str__(self) -> str:
        return f"Report {self.crew}"


class FieldCrewReportLine(models.Model):
    report = models.ForeignKey(FieldCrewReport, on_delete=models.CASCADE, related_name="lines")
    employee = models.ForeignKey("hr.Employee", on_delete=models.PROTECT, related_name="field_crew_report_lines")
    event_type = models.CharField(
        max_length=16, choices=FieldWorkerEventType.choices,
        default=FieldWorkerEventType.PRESENT, db_index=True
    )
    day_value = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("1.00"))
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(fields=["report", "employee"], name="uq_fcrl_report_employee"),
            models.CheckConstraint(
                condition=models.Q(day_value__gte=0, day_value__lte=1),
                name="ck_fcrl_day_value_range",
            ),
        ]
        indexes = [
            models.Index(fields=["employee", "event_type"], name="ix_fcrl_emp_event"),
        ]


class FieldWorkerEvent(models.Model):
    work_day = models.ForeignKey(FieldWorkDay, on_delete=models.PROTECT, related_name="worker_events")
    crew_report = models.ForeignKey(
        FieldCrewReport, null=True, blank=True,
        on_delete=models.PROTECT, related_name="worker_events"
    )
    employee = models.ForeignKey("hr.Employee", on_delete=models.PROTECT, related_name="field_worker_events")
    event_type = models.CharField(max_length=16, choices=FieldWorkerEventType.choices, db_index=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    details = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="field_worker_events_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "nomina"
        indexes = [
            models.Index(fields=["work_day", "employee"], name="ix_fwe_workday_employee"),
            models.Index(fields=["event_type"], name="ix_fwe_type"),
        ]


class FieldTransfer(models.Model):
    work_day = models.ForeignKey(FieldWorkDay, on_delete=models.PROTECT, related_name="transfers")
    employee = models.ForeignKey("hr.Employee", on_delete=models.PROTECT, related_name="field_transfers")
    from_crew = models.ForeignKey(FieldCrew, on_delete=models.PROTECT, related_name="transfers_out")
    to_crew = models.ForeignKey(FieldCrew, on_delete=models.PROTECT, related_name="transfers_in")
    reason = models.TextField()
    transferred_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="field_transfers_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(from_crew=models.F("to_crew")),
                name="ck_ft_different_crews",
            ),
        ]
        indexes = [
            models.Index(fields=["work_day", "employee"], name="ix_ft_workday_employee"),
        ]


class FieldAttendanceConsolidation(models.Model):
    work_day = models.ForeignKey(FieldWorkDay, on_delete=models.PROTECT, related_name="consolidations")
    payroll_period = models.ForeignKey(
        PayrollPeriod, null=True, blank=True,
        on_delete=models.PROTECT, related_name="field_attendance_consolidations"
    )
    employee = models.ForeignKey("hr.Employee", on_delete=models.PROTECT, related_name="field_attendance_consolidations")
    status = models.CharField(
        max_length=24, choices=FieldAttendanceConsolidationStatus.choices,
        default=FieldAttendanceConsolidationStatus.OK, db_index=True
    )
    day_value = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.00"))
    primary_event_type = models.CharField(max_length=16, choices=FieldWorkerEventType.choices, blank=True, default="")
    conflict_codes = models.JSONField(default=list, blank=True)
    source_summary = models.JSONField(default=dict, blank=True)
    has_inss_snapshot = models.BooleanField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="field_consolidations_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(fields=["work_day", "employee"], name="uq_fac_workday_employee"),
            models.CheckConstraint(
                condition=models.Q(day_value__gte=0, day_value__lte=1),
                name="ck_fac_day_value_range",
            ),
        ]
        indexes = [
            models.Index(fields=["work_day", "status"], name="ix_fac_workday_status"),
            models.Index(fields=["employee", "status"], name="ix_fac_employee_status"),
        ]


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
