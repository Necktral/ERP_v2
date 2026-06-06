from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Crew(models.Model):
    crew_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_field_crews_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_field_crews_branch")
    code = models.CharField(max_length=64, blank=True, default="")
    name = models.CharField(max_length=160)
    foreman = models.ForeignKey(
        "hr.Employee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="field_crews_led",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uq_nom_field_crew_company_name"),
        ]
        indexes = [
            models.Index(fields=["company", "is_active"], name="ix_nom_field_crew_c_a"),
            models.Index(fields=["branch", "is_active"], name="ix_nom_field_crew_b_a"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.branch_id and self.company_id and self.branch.parent_id != self.company_id:
            raise ValidationError({"branch": "Crew.branch debe pertenecer a Crew.company."})
        foreman = self.foreman
        if self.foreman_id and self.company_id and foreman is not None and foreman.company_id != self.company_id:
            raise ValidationError({"foreman": "Crew.foreman debe pertenecer a Crew.company."})

    def __str__(self) -> str:
        return self.name


class CrewMembership(models.Model):
    crew = models.ForeignKey(Crew, on_delete=models.PROTECT, related_name="memberships")
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="field_crew_memberships",
    )
    active_from = models.DateField(default=timezone.localdate)
    active_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(
                fields=["crew", "employee"],
                condition=models.Q(is_active=True),
                name="uq_nom_field_membership_active",
            ),
        ]
        indexes = [
            models.Index(fields=["crew", "is_active"], name="ix_nom_field_member_crew_a"),
            models.Index(fields=["employee", "is_active"], name="ix_nom_field_member_emp_a"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.employee_id and self.crew_id and self.employee.company_id != self.crew.company_id:
            raise ValidationError({"employee": "CrewMembership.employee debe pertenecer a Crew.company."})
        if self.active_to and self.active_to < self.active_from:
            raise ValidationError({"active_to": "active_to debe ser posterior a active_from."})


class FieldCaptureWorkDay(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        SUBMITTED = "SUBMITTED", "Enviado"
        APPROVAL_PENDING = "APPROVAL_PENDING", "Aprobación pendiente"
        APPROVED = "APPROVED", "Aprobado"

    work_day_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_field_work_days_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_field_work_days_branch")
    period = models.ForeignKey("nomina.PayrollPeriod", on_delete=models.PROTECT, related_name="field_capture_work_days")
    crew = models.ForeignKey(Crew, on_delete=models.PROTECT, related_name="work_days")
    work_date = models.DateField(db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="field_capture_work_days_submitted",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.UniqueConstraint(fields=["crew", "work_date"], name="uq_nom_field_workday_crew_date"),
        ]
        indexes = [
            models.Index(fields=["company", "work_date"], name="ix_nom_field_workday_c_d"),
            models.Index(fields=["period", "status"], name="ix_nom_field_workday_p_st"),
            models.Index(fields=["crew", "status"], name="ix_nom_field_workday_crew_st"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.branch_id and self.company_id and self.branch.parent_id != self.company_id:
            raise ValidationError({"branch": "FieldCaptureWorkDay.branch debe pertenecer a company."})
        if self.period_id and self.company_id and self.period.company_id != self.company_id:
            raise ValidationError({"period": "FieldCaptureWorkDay.period debe pertenecer a company."})
        if self.crew_id and self.company_id and self.crew.company_id != self.company_id:
            raise ValidationError({"crew": "FieldCaptureWorkDay.crew debe pertenecer a company."})
        if self.work_date and self.period_id and not (self.period.start_date <= self.work_date <= self.period.end_date):
            raise ValidationError({"work_date": "work_date debe caer dentro del período de nómina."})


class FieldCaptureReport(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Borrador"
        SUBMITTED = "SUBMITTED", "Enviado"
        APPROVAL_PENDING = "APPROVAL_PENDING", "Aprobación pendiente"
        APPROVED = "APPROVED", "Aprobado"

    report_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_field_reports_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_field_reports_branch")
    period = models.ForeignKey("nomina.PayrollPeriod", on_delete=models.PROTECT, related_name="field_capture_reports")
    work_day = models.OneToOneField(FieldCaptureWorkDay, on_delete=models.PROTECT, related_name="crew_report")
    crew = models.ForeignKey(Crew, on_delete=models.PROTECT, related_name="field_reports")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="field_capture_reports_reported",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="field_capture_reports_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_request = models.ForeignKey(
        "iam.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="field_capture_reports",
    )
    observations = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        indexes = [
            models.Index(fields=["company", "status"], name="ix_nom_field_report_c_st"),
            models.Index(fields=["period", "status"], name="ix_nom_field_report_p_st"),
            models.Index(fields=["crew", "status"], name="ix_nom_field_report_crew_st"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.branch_id and self.company_id and self.branch.parent_id != self.company_id:
            raise ValidationError({"branch": "FieldCaptureReport.branch debe pertenecer a company."})
        if self.period_id and self.company_id and self.period.company_id != self.company_id:
            raise ValidationError({"period": "FieldCaptureReport.period debe pertenecer a company."})
        if self.crew_id and self.company_id and self.crew.company_id != self.company_id:
            raise ValidationError({"crew": "FieldCaptureReport.crew debe pertenecer a company."})
        if self.work_day_id and self.crew_id and self.work_day.crew_id != self.crew_id:
            raise ValidationError({"work_day": "FieldCaptureReport.work_day debe pertenecer a la misma crew."})


class FieldCaptureEvent(models.Model):
    class EventType(models.TextChoices):
        PRESENT = "PRESENT", "Presente"
        ABSENT = "ABSENT", "Ausente"
        SICK = "SICK", "Enfermo"
        SUBSIDY = "SUBSIDY", "Subsidio INSS"
        ACCIDENT = "ACCIDENT", "Accidente laboral"
        TRANSFER = "TRANSFER", "Traslado"
        VACATION = "VACATION", "Vacaciones"

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_field_events_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="nomina_field_events_branch")
    period = models.ForeignKey("nomina.PayrollPeriod", on_delete=models.PROTECT, related_name="field_capture_events")
    work_day = models.ForeignKey(FieldCaptureWorkDay, on_delete=models.PROTECT, related_name="worker_events")
    report = models.ForeignKey(FieldCaptureReport, on_delete=models.PROTECT, related_name="worker_events")
    crew = models.ForeignKey(Crew, on_delete=models.PROTECT, related_name="worker_events")
    employee = models.ForeignKey(
        "hr.Employee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="field_capture_events",
    )
    cedula = models.CharField(max_length=20, blank=True, default="")
    employee_name = models.CharField(max_length=160, blank=True, default="")
    event_type = models.CharField(max_length=16, choices=EventType.choices, db_index=True)
    day_value = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("1.00"))
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    sunday_worked_days = models.PositiveSmallIntegerField(default=0)
    from_crew = models.ForeignKey(
        Crew,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="worker_events_transferred_from",
    )
    to_crew = models.ForeignKey(
        Crew,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="worker_events_transferred_to",
    )
    notes = models.TextField(blank=True, default="")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="field_capture_events_recorded",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "nomina"
        constraints = [
            models.CheckConstraint(condition=models.Q(day_value__gte=0), name="ck_nom_field_event_day_nonneg"),
            models.UniqueConstraint(
                fields=["report", "employee", "event_type"],
                condition=models.Q(employee__isnull=False),
                name="uq_nom_field_event_emp_type",
            ),
            models.UniqueConstraint(
                fields=["report", "cedula", "event_type"],
                condition=models.Q(employee__isnull=True) & ~models.Q(cedula=""),
                name="uq_nom_field_event_ced_type",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "event_type"], name="ix_nom_field_event_c_type"),
            models.Index(fields=["work_day", "event_type"], name="ix_nom_field_event_day_type"),
            models.Index(fields=["employee", "period"], name="ix_nom_field_event_emp_p"),
            models.Index(fields=["cedula", "period"], name="ix_nom_field_event_ced_p"),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.employee_id and not self.cedula:
            raise ValidationError({"cedula": "cedula es requerida cuando employee es null."})
        employee = self.employee
        if self.employee_id and self.company_id and employee is not None and employee.company_id != self.company_id:
            raise ValidationError({"employee": "FieldCaptureEvent.employee debe pertenecer a company."})
        if self.event_type == self.EventType.TRANSFER and not self.to_crew_id:
            raise ValidationError({"to_crew": "to_crew es requerido para traslado."})
        to_crew = self.to_crew
        if self.to_crew_id and self.company_id and to_crew is not None and to_crew.company_id != self.company_id:
            raise ValidationError({"to_crew": "to_crew debe pertenecer a company."})
        if self.crew_id and self.company_id and self.crew.company_id != self.company_id:
            raise ValidationError({"crew": "FieldCaptureEvent.crew debe pertenecer a company."})
