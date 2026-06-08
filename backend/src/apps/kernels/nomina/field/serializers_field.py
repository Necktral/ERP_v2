from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.kernels.nomina.models import AttendanceReport

from .models_field import Crew, FieldCaptureEvent, FieldCaptureReport, FieldCaptureWorkDay


class CrewOut(serializers.ModelSerializer):
    class Meta:
        model = Crew
        fields = [
            "id",
            "crew_id",
            "company",
            "branch",
            "code",
            "name",
            "foreman",
            "is_active",
            "created_at",
            "updated_at",
        ]


class CrewCreateIn(serializers.Serializer):
    branch_id = serializers.IntegerField()
    name = serializers.CharField(max_length=160)
    code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    foreman_id = serializers.IntegerField(required=False, allow_null=True)


class FieldCaptureWorkDayOut(serializers.ModelSerializer):
    class Meta:
        model = FieldCaptureWorkDay
        fields = [
            "id",
            "work_day_id",
            "company",
            "branch",
            "period",
            "crew",
            "work_date",
            "status",
            "submitted_by",
            "submitted_at",
            "notes",
            "created_at",
            "updated_at",
        ]


class FieldCaptureWorkDayCreateIn(serializers.Serializer):
    period_id = serializers.IntegerField()
    crew_id = serializers.IntegerField()
    work_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    observations = serializers.CharField(required=False, allow_blank=True, default="")


class FieldCaptureReportOut(serializers.ModelSerializer):
    event_count = serializers.IntegerField(source="worker_events.count", read_only=True)

    class Meta:
        model = FieldCaptureReport
        fields = [
            "id",
            "report_id",
            "company",
            "branch",
            "period",
            "work_day",
            "crew",
            "status",
            "reported_by",
            "submitted_at",
            "approved_by",
            "approved_at",
            "approval_request",
            "observations",
            "event_count",
            "created_at",
            "updated_at",
        ]


class FieldCaptureEventOut(serializers.ModelSerializer):
    class Meta:
        model = FieldCaptureEvent
        fields = [
            "id",
            "event_id",
            "company",
            "branch",
            "period",
            "work_day",
            "report",
            "crew",
            "employee",
            "cedula",
            "employee_name",
            "event_type",
            "day_value",
            "overtime_hours",
            "sunday_worked_days",
            "from_crew",
            "to_crew",
            "notes",
            "recorded_by",
            "recorded_at",
            "created_at",
            "updated_at",
        ]


class FieldCaptureEventCreateIn(serializers.Serializer):
    employee_id = serializers.IntegerField(required=False, allow_null=True)
    cedula = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    employee_name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    event_type = serializers.ChoiceField(choices=[choice for choice, _ in FieldCaptureEvent.EventType.choices])
    day_value = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=Decimal("1.00"))
    overtime_hours = serializers.DecimalField(max_digits=6, decimal_places=2, required=False, default=Decimal("0.00"))
    sunday_worked_days = serializers.IntegerField(min_value=0, required=False, default=0)
    to_crew_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class FieldReportApprovalRequestIn(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class FieldReportApproveIn(serializers.Serializer):
    approval_request_id = serializers.UUIDField()
    note = serializers.CharField(required=False, allow_blank=True, default="")


class AttendanceReportOut(serializers.ModelSerializer):
    class Meta:
        model = AttendanceReport
        fields = [
            "id",
            "report_id",
            "company",
            "branch",
            "period",
            "employee",
            "employee_name",
            "inss_number",
            "cedula",
            "source",
            "status",
            "days_worked",
            "days_absent",
            "days_sick",
            "days_subsidy",
            "days_accident",
            "days_transferred",
            "days_vacation",
            "overtime_hours",
            "sunday_worked_days",
            "observations",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        ]
