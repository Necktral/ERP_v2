from __future__ import annotations

from rest_framework import serializers

from .models import AIControl, ErrorEvent, SecurityFinding

_LIST_FIELDS = [
    "error_id",
    "exception_type",
    "message_hash",
    "stack_hash",
    "file_path",
    "line_number",
    "function_name",
    "endpoint",
    "method",
    "http_status",
    "domain",
    "risk_class",
    "correlation_id",
    "company_id",
    "branch_id",
    "occurrence_count",
    "first_seen_at",
    "last_seen_at",
    "status",
    "owner",
]


class ErrorEventSerializer(serializers.ModelSerializer):
    """Vista de lista: campos NO sensibles (sin la traza, ya redactada pero voluminosa)."""

    class Meta:
        model = ErrorEvent
        fields = _LIST_FIELDS
        read_only_fields = _LIST_FIELDS


class ErrorEventDetailSerializer(serializers.ModelSerializer):
    """Detalle: agrega la traza ya redactada (solo frames, sin mensaje crudo)."""

    class Meta:
        model = ErrorEvent
        fields = [*_LIST_FIELDS, "stack_trace_redacted"]
        read_only_fields = [*_LIST_FIELDS, "stack_trace_redacted"]


_FINDING_FIELDS = [
    "finding_id",
    "source_tool",
    "vuln_id",
    "package",
    "package_version",
    "fixed_version",
    "cve_id",
    "cwe_id",
    "file_path",
    "line_start",
    "symbol",
    "domain",
    "severity_raw",
    "risk_class",
    "reachable",
    "status",
    "owner",
    "accepted_risk_reason",
    "expires_at",
    "first_seen_at",
    "last_seen_at",
]


class SecurityFindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SecurityFinding
        fields = _FINDING_FIELDS
        read_only_fields = _FINDING_FIELDS


class AIControlSerializer(serializers.ModelSerializer):
    """Estado del botón de apagado de la IA (solo lectura)."""

    class Meta:
        model = AIControl
        fields = ["ai_enabled", "reason", "updated_at", "updated_by"]
        read_only_fields = ["ai_enabled", "reason", "updated_at", "updated_by"]


class AIControlUpdateSerializer(serializers.Serializer):
    """Payload para encender/apagar la IA (el 'botón')."""

    enabled = serializers.BooleanField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
