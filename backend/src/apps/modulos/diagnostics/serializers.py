from __future__ import annotations

from rest_framework import serializers

from .models import ErrorEvent

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
