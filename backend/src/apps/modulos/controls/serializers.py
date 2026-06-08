from __future__ import annotations

from rest_framework import serializers

from .models import ControlFinding, SegregationRule


class SegregationRuleOut(serializers.ModelSerializer):
    is_global = serializers.SerializerMethodField()

    class Meta:
        model = SegregationRule
        fields = [
            "id",
            "company",
            "is_global",
            "code",
            "name",
            "permission_a",
            "permission_b",
            "event_a",
            "event_b",
            "severity",
            "rationale",
            "is_active",
        ]

    def get_is_global(self, obj) -> bool:
        return obj.company_id is None


class ControlFindingOut(serializers.ModelSerializer):
    rule_code = serializers.CharField(source="rule.code", default=None)

    class Meta:
        model = ControlFinding
        fields = [
            "id",
            "control_code",
            "rule_id",
            "rule_code",
            "severity",
            "actor_user_id",
            "subject_type",
            "subject_id",
            "status",
            "detail",
            "detected_at",
            "resolved_by_id",
            "resolved_at",
            "resolution_note",
        ]


class FindingResolveIn(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            ControlFinding.Status.ACKNOWLEDGED,
            ControlFinding.Status.RESOLVED,
            ControlFinding.Status.DISMISSED,
        ]
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")


class ScanIn(serializers.Serializer):
    window_days = serializers.IntegerField(required=False, min_value=1, max_value=3650, default=90)
