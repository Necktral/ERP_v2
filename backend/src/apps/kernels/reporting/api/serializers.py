from __future__ import annotations

from rest_framework import serializers

from ..enums import SnapshotStatus


class DatasetRunIn(serializers.Serializer):
    filters = serializers.DictField(required=False, default=dict)
    consumer_ref = serializers.CharField(required=False, allow_blank=True, default="")


class RunsListIn(serializers.Serializer):
    dataset_key = serializers.CharField(required=False, allow_blank=True, default="")


class RunExportIn(serializers.Serializer):
    format = serializers.ChoiceField(choices=("json", "csv", "xlsx"))


class SnapshotsListIn(serializers.Serializer):
    dataset_key = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(
        choices=[("", "Any")] + [(choice.value, choice.label) for choice in SnapshotStatus],
        required=False,
        default="",
    )


class SnapshotGenerateIn(serializers.Serializer):
    dataset_key = serializers.CharField()
    filters = serializers.DictField(required=False, default=dict)
    force_refresh = serializers.BooleanField(required=False, default=False)
    consumer_ref = serializers.CharField(required=False, allow_blank=True, default="")


class SavedViewsListIn(serializers.Serializer):
    dataset_key = serializers.CharField(required=False, allow_blank=True, default="")


class SavedViewCreateIn(serializers.Serializer):
    name = serializers.CharField(max_length=160, allow_blank=False)
    dataset_key = serializers.CharField(max_length=128)
    filters = serializers.DictField(required=False, default=dict)
    render_state = serializers.DictField(required=False, default=dict)
    is_shared = serializers.BooleanField(required=False, default=False)
