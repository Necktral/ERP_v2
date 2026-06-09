from __future__ import annotations

import uuid
from datetime import date, timedelta
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
DEFAULT_SEVENTH_DAY_RATE = Decimal("1.0")         # séptimo día = 1 día normal pagado
DEFAULT_HOLIDAY_WORKED_RATE = Decimal("2.0")      # feriado laborado = doble
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
        PeriodType.MONTHLY.value: 12,
        PeriodType.FIRST_HALF.value: 24,
        PeriodType.SECOND_HALF.value: 24,
        PeriodType.CATORCENA.value: 26,
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
    FIELD = "FIELD", "Asistencia de campo consolidada"


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
    holiday_worked_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=DEFAULT_HOLIDAY_WORKED_RATE,
        help_text="Multiplicador feriado laborado (ej. 2.00 = doble)"
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
    seventh_day_days = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text="Séptimos días ganados (1 por semana completa; jornaleros DAILY)"
    )
    holiday_worked_days = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"),
        help_text="Días feriados laborados"
    )

    # --- INGRESOS (todos calculados, almacenados para auditoría) ---
    quincenal_salary = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    subsidy_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    overtime_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    sunday_bonus_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    seventh_day_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    holiday_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    vacation_provision = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    thirteenth_month_provision = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    other_income = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_income = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    # --- RETENCIONES ---
    inss_laboral = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    ir_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    ir_manual = models.BooleanField(
        default=False,
        help_text="IR fijado manualmente (override): si True, compute_all NO recalcula el IR.",
    )
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
            seventh_rate = config.seventh_day_rate
            holiday_rate = config.holiday_worked_rate
            subsidy_inss_rate = config.subsidy_inss_rate
            subsidy_employer_days = int(config.subsidy_employer_days or 0)
        else:
            inss_laboral_rate = DEFAULT_INSS_LABORAL
            inss_patronal_rate = DEFAULT_INSS_PATRONAL_LARGE
            inatec_rate = DEFAULT_INATEC
            vacation_rate = DEFAULT_VACATION_RATE
            thirteenth_rate = DEFAULT_THIRTEENTH_RATE
            overtime_rate = DEFAULT_OVERTIME_RATE
            sunday_rate = DEFAULT_SUNDAY_RATE
            seventh_rate = DEFAULT_SEVENTH_DAY_RATE
            holiday_rate = DEFAULT_HOLIDAY_WORKED_RATE
            subsidy_inss_rate = DEFAULT_SUBSIDY_INSS_RATE
            subsidy_employer_days = int(DEFAULT_SUBSIDY_EMPLOYER_DAYS or 0)

        # 1. Salario base mensual en NIO
        if self.base_salary_usd and self.exchange_rate:
            monthly_nio = _r2(self.base_salary_usd * self.exchange_rate)
            self.base_salary_nio = monthly_nio
        else:
            monthly_nio = self.base_salary_nio

        # 2. Salario diario (base: mes de 30 días)
        self.daily_rate_nio = _r6(monthly_nio / Decimal("30"))

        # 3. Salario del período. Jornaleros (DAILY): siempre proporcional a días
        #    trabajados (el séptimo día se paga aparte). Mensuales: prorrata o salario completo.
        period_days = Decimal(str(self.days_in_period or 15))
        worked = Decimal(str(self.days_worked))
        quincenal_base = _r2(monthly_nio / 2)

        if self.salary_type == SalaryType.DAILY:
            self.quincenal_salary = _r2(self.daily_rate_nio * worked)
        else:
            self.quincenal_salary = _r2(self.daily_rate_nio * worked) if worked < period_days else quincenal_base

        # 4. Subsidio INSS (NM-02): la empresa paga el 100% los primeros
        #    `subsidy_employer_days` días y, desde el día N+1, se reconoce la tasa
        #    de subsidio INSS (60%). Antes se aplicaba 60% a TODOS los días, lo que
        #    subestimaba el subsidio de los primeros días (el tramo patronal no se usaba).
        subsidy_days = Decimal(str(self.days_subsidy))
        if subsidy_days > 0:
            if not self.subsidy_daily_rate or self.subsidy_daily_rate == 0:
                self.subsidy_daily_rate = self.daily_rate_nio
            employer_days = min(subsidy_days, Decimal(subsidy_employer_days))
            inss_days = subsidy_days - employer_days
            self.subsidy_amount = _r2(
                self.subsidy_daily_rate * employer_days
                + self.subsidy_daily_rate * inss_days * subsidy_inss_rate
            )
        else:
            self.subsidy_amount = Decimal("0.00")

        # 5. Horas extra
        hourly_rate = _r6(self.daily_rate_nio / 8)
        self.overtime_amount = _r2(hourly_rate * overtime_rate * Decimal(str(self.overtime_hours)))

        # 6. Domingos laborados
        self.sunday_bonus_amount = _r2(self.daily_rate_nio * sunday_rate * Decimal(str(self.sunday_worked_days)))

        # 6b. Séptimo día y feriados laborados (jornaleros DAILY; mensuales lo llevan embebido)
        if self.salary_type == SalaryType.DAILY:
            self.seventh_day_amount = _r2(self.daily_rate_nio * seventh_rate * Decimal(str(self.seventh_day_days)))
            self.holiday_amount = _r2(self.daily_rate_nio * holiday_rate * Decimal(str(self.holiday_worked_days)))
        else:
            self.seventh_day_amount = Decimal("0.00")
            self.holiday_amount = Decimal("0.00")

        # Salario básico devengado: base para INSS/IR/patronal (incluye séptimo/feriado).
        basic_earned = _r2(self.quincenal_salary + self.seventh_day_amount + self.holiday_amount)

        # 7. Provisiones (sobre salario mensual proporcional a días trabajados)
        monthly_proportional = _r2(self.daily_rate_nio * worked * 2)
        self.vacation_provision = _r2(monthly_proportional * vacation_rate)
        self.thirteenth_month_provision = _r2(monthly_proportional * thirteenth_rate)

        # 8. Total ingresos
        self.total_income = _r2(
            self.quincenal_salary + self.seventh_day_amount + self.holiday_amount +
            self.subsidy_amount + self.overtime_amount + self.sunday_bonus_amount +
            self.vacation_provision + self.thirteenth_month_provision +
            self.other_income
        )

        # 9. IR — recalculado SIEMPRE que haya config con tabla IR (salvo override manual).
        # Antes el guard era `not self.ir_amount`, que confundía "ya calculado" con
        # "fijado a mano": en cualquier recompute (asistencia, reclasificación CON/SIN
        # INSS, cambio de días/salario) el IR quedaba obsoleto. Ahora solo se respeta un
        # override explícito (`ir_manual`); si no, se anualiza por la frecuencia REAL
        # del pago (catorcena ×26, no ×24) y se recalcula contra la base gravable vigente.
        if config and not self.ir_manual:
            self.ir_amount = IRBracket.calculate_period_ir(
                config=config,
                period_income=basic_earned,
                periods_per_year=periods_per_year(self.payment_frequency),
            )

        # 10. Retenciones (INSS sobre el salario básico devengado, incluye séptimo/feriado)
        if self.has_inss:
            self.inss_laboral = _r2(basic_earned * inss_laboral_rate)
        else:
            self.inss_laboral = Decimal("0.00")

        self.total_deductions = _r2(
            self.inss_laboral + self.ir_amount + self.loan_payment +
            self.food_deduction + self.advance_deduction +
            self.store_credit_deduction + self.other_deductions
        )

        # 11. Neto — el devengado en efectivo incluye `other_income` (NM-03): antes
        #     entraba a total_income pero NO al devengado/neto, así que un ingreso en
        #     efectivo (bono/viático) no se le pagaba al trabajador.
        self.total_devengado = _r2(
            self.quincenal_salary + self.seventh_day_amount + self.holiday_amount +
            self.subsidy_amount + self.overtime_amount + self.sunday_bonus_amount +
            self.other_income
        )
        self.net_to_pay = _r2(self.total_devengado - self.total_deductions)

        # 12. Costos patronales (sobre el salario básico devengado)
        if self.has_inss:
            self.inss_patronal = _r2(basic_earned * inss_patronal_rate)
            self.inatec = _r2(basic_earned * inatec_rate)
        else:
            self.inss_patronal = Decimal("0.00")
            self.inatec = Decimal("0.00")

        self.vacation_cost = self.vacation_provision
        self.thirteenth_month_cost = self.thirteenth_month_provision
        self.total_employer_cost = _r2(
            self.inss_patronal + self.inatec +
            self.vacation_cost + self.thirteenth_month_cost
        )
        # NM-07: el costo total parte del DEVENGADO bruto (no del neto). Las retenciones
        # de ley (INSS laboral / IR) que la empresa remite a terceros son parte del costo;
        # usar el neto las omitía y subestimaba el costo patronal real.
        self.total_payroll_cost = _r2(self.total_devengado + self.total_employer_cost)


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
        constraints = [
            # Un reporte por (período, empleado, fuente): hace idempotente el rollup
            # de la asistencia de campo. Solo aplica a reportes con empleado HR.
            models.UniqueConstraint(
                fields=["period", "employee", "source"],
                condition=models.Q(employee__isnull=False),
                name="uq_attreport_period_emp_source",
            ),
        ]
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
    # NM-06: monto realmente abonado al crédito en portfolio. El abono es best-effort
    # (fuera de la txn): si falla, `abono_applied` < `amount_deducted` marca la deducción
    # como "abono pendiente" → reconciliable (la conciliación deja de ser silenciosa).
    abono_applied = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
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


# ---------------------------------------------------------------------------
# Régimen INSS — afiliación maestra fechada + elección por período
# (el "dolor de cabeza": trabajadores que cotizan un período y al siguiente no)
# ---------------------------------------------------------------------------

class InssRegime(models.TextChoices):
    AFFILIATED = "AFFILIATED", "Cotiza INSS"
    NOT_AFFILIATED = "NOT_AFFILIATED", "No cotiza INSS"


class EmployeeInssEnrollment(models.Model):
    """Afiliación INSS del empleado, fechada (effective-dated). Verdad maestra del régimen."""

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="inss_enrollments_company")
    employee = models.ForeignKey("hr.Employee", on_delete=models.PROTECT, related_name="inss_enrollments")
    regime = models.CharField(max_length=16, choices=InssRegime.choices, default=InssRegime.AFFILIATED)
    effective_from = models.DateField(db_index=True)
    effective_to = models.DateField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="inss_enrollments_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(fields=["employee", "effective_from"], name="uq_inss_enroll_emp_from"),
        ]
        indexes = [
            models.Index(fields=["employee", "effective_from"], name="ix_inss_enroll_emp_from"),
            models.Index(fields=["company", "regime"], name="ix_inss_enroll_c_regime"),
        ]

    def __str__(self) -> str:
        return f"emp:{self.employee_id} {self.regime} desde {self.effective_from}"

    @classmethod
    def resolve_for(cls, employee, on_date) -> str:
        """Régimen vigente del empleado en la fecha; AFFILIATED por defecto si no hay afiliación."""
        enrollment = (
            cls.objects.filter(employee=employee, effective_from__lte=on_date)
            .filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=on_date))
            .order_by("-effective_from")
            .first()
        )
        return enrollment.regime if enrollment is not None else InssRegime.AFFILIATED


class InssElectionSource(models.TextChoices):
    ENROLLMENT = "ENROLLMENT", "Desde afiliación"
    OVERRIDE = "OVERRIDE", "Override del período"


class PayrollInssElection(models.Model):
    """Elección INSS efectiva para un período (resuelta desde afiliación o por override auditado)."""

    period = models.ForeignKey(PayrollPeriod, on_delete=models.CASCADE, related_name="inss_elections")
    employee = models.ForeignKey(
        "hr.Employee", null=True, blank=True,
        on_delete=models.PROTECT, related_name="inss_elections"
    )
    cedula = models.CharField(max_length=20, blank=True, default="")
    elected_has_inss = models.BooleanField()
    source = models.CharField(max_length=16, choices=InssElectionSource.choices, default=InssElectionSource.ENROLLMENT)
    reason = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="inss_elections_created"
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(
                fields=["period", "employee"],
                condition=models.Q(employee__isnull=False),
                name="uq_inss_election_period_emp",
            ),
            models.UniqueConstraint(
                fields=["period", "cedula"],
                condition=models.Q(employee__isnull=True) & ~models.Q(cedula=""),
                name="uq_inss_election_period_cedula",
            ),
        ]
        indexes = [
            models.Index(fields=["period", "source"], name="ix_inss_elec_period_src"),
        ]

    def __str__(self) -> str:
        who = self.employee_id or self.cedula
        return f"{who} period:{self.period_id} INSS={self.elected_has_inss}"


# ---------------------------------------------------------------------------
# Calendario de feriados (catálogo precargado a nivel Nicaragua)
# ---------------------------------------------------------------------------

def easter_sunday(year: int) -> date:
    """Domingo de Resurrección (Pascua) para un año del calendario gregoriano.

    Algoritmo anónimo gregoriano (Meeus/Jones/Butcher). Base para los feriados
    móviles de Nicaragua: Jueves Santo = Pascua − 3, Viernes Santo = Pascua − 2.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month = (h + el - 7 * m + 114) // 31
    day = ((h + el - 7 * m + 114) % 31) + 1
    return date(year, month, day)


class HolidayLegalType(models.TextChoices):
    """Naturaleza legal del feriado → define cómo paga y si obliga al sector privado."""
    NACIONAL_OBLIGATORIO = "NACIONAL_OBLIGATORIO", "Nacional obligatorio (Código del Trabajo)"
    ASUETO_ESTATAL = "ASUETO_ESTATAL", "Asueto estatal (sector público)"
    LOCAL = "LOCAL", "Local / fiesta patronal"
    EMPRESA = "EMPRESA", "De empresa"


class HolidayDateKind(models.TextChoices):
    """Recurrencia de la fecha."""
    FIXED = "FIXED", "Fija (mes/día, todos los años)"
    EASTER = "EASTER", "Móvil (offset de días respecto a Pascua)"
    ONE_OFF = "ONE_OFF", "Puntual (fecha exacta de un año)"


class Holiday(models.Model):
    """Catálogo de feriados, precargado a nivel Nicaragua.

    Diseñado en 3 ejes ortogonales (ver memoria de diseño):
      - ``legal_type``: naturaleza legal → cómo paga y si aplica al sector privado.
      - ``date_kind``: recurrencia → fija (mes/día), móvil (offset de Pascua) o puntual.
      - ``applies_to_payroll``: si por defecto cuenta para la planilla. Los obligatorios
        sí; los asuetos estatales no (la empresa privada no está obligada).

    Geografía GENERAL: ``locality`` es texto informativo ("Managua", "Nacional"…). No
    hay auto-resolución por finca/departamento — el revisor de la planilla ubica los
    días que aplican entre los feriados precargados.
    """
    company = models.ForeignKey(
        "iam.OrgUnit", null=True, blank=True, on_delete=models.CASCADE,
        related_name="holidays",
        help_text="NULL = catálogo nacional compartido; no-NULL = feriado propio de la empresa.",
    )
    code = models.CharField(
        max_length=64, blank=True, default="",
        help_text="Identificador estable (slug) para precarga idempotente y referencia.",
    )
    name = models.CharField(max_length=200)
    legal_type = models.CharField(max_length=24, choices=HolidayLegalType.choices)
    date_kind = models.CharField(max_length=8, choices=HolidayDateKind.choices)

    # FIXED → mes/día
    month = models.PositiveSmallIntegerField(null=True, blank=True)
    day = models.PositiveSmallIntegerField(null=True, blank=True)
    # EASTER → días respecto al Domingo de Resurrección (Jueves Santo = -3, Viernes Santo = -2)
    easter_offset = models.SmallIntegerField(null=True, blank=True)
    # ONE_OFF → fecha exacta
    specific_date = models.DateField(null=True, blank=True)

    locality = models.CharField(
        max_length=120, blank=True, default="",
        help_text="Etiqueta geográfica informativa (general). P.ej. 'Nacional', 'Managua'.",
    )
    applies_to_payroll = models.BooleanField(
        default=True,
        help_text="Si por defecto cuenta para la planilla. Asuetos estatales = False.",
    )
    pays_premium = models.BooleanField(
        default=True,
        help_text="Si laborado paga prima (doble). Feriado obligatorio = True.",
    )
    premium_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Multiplicador del día si se labora. NULL = usar NominaConfig.holiday_worked_rate.",
    )

    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"],
                condition=~models.Q(code=""),
                name="uq_holiday_company_code",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(month__isnull=True)
                    | models.Q(month__gte=1, month__lte=12)
                ),
                name="ck_holiday_month_range",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(day__isnull=True)
                    | models.Q(day__gte=1, day__lte=31)
                ),
                name="ck_holiday_day_range",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "is_active"], name="ix_holiday_company_active"),
            models.Index(fields=["date_kind"], name="ix_holiday_date_kind"),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.legal_type}]"

    def clean(self) -> None:
        super().clean()
        if self.date_kind == HolidayDateKind.FIXED:
            if self.month is None or self.day is None:
                raise ValidationError("Feriado FIXED requiere mes y día.")
            if self.easter_offset is not None or self.specific_date is not None:
                raise ValidationError("Feriado FIXED no debe llevar easter_offset ni specific_date.")
        elif self.date_kind == HolidayDateKind.EASTER:
            if self.easter_offset is None:
                raise ValidationError("Feriado EASTER requiere easter_offset.")
            if self.month is not None or self.day is not None or self.specific_date is not None:
                raise ValidationError("Feriado EASTER solo lleva easter_offset.")
        elif self.date_kind == HolidayDateKind.ONE_OFF:
            if self.specific_date is None:
                raise ValidationError("Feriado ONE_OFF requiere specific_date.")
            if self.month is not None or self.day is not None or self.easter_offset is not None:
                raise ValidationError("Feriado ONE_OFF solo lleva specific_date.")

    def date_for_year(self, year: int) -> date | None:
        """Materializa la fecha concreta de este feriado para un año dado.

        Devuelve ``None`` si no aplica a ese año (puntual de otro año) o si la
        combinación mes/día es inválida.
        """
        if self.date_kind == HolidayDateKind.FIXED:
            if self.month is None or self.day is None:
                return None
            try:
                return date(year, self.month, self.day)
            except ValueError:
                return None
        if self.date_kind == HolidayDateKind.EASTER:
            if self.easter_offset is None:
                return None
            return easter_sunday(year) + timedelta(days=self.easter_offset)
        if self.date_kind == HolidayDateKind.ONE_OFF:
            if self.specific_date is not None and self.specific_date.year == year:
                return self.specific_date
            return None
        return None


from .field.models_field import (  # noqa: E402,F401
    Crew,
    CrewMembership,
    FieldCaptureEvent,
    FieldCaptureReport,
    FieldCaptureWorkDay,
)
