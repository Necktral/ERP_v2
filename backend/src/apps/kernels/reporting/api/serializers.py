from __future__ import annotations

from rest_framework import serializers


class DatasetRunIn(serializers.Serializer):
    filters = serializers.DictField(required=False, default=dict)
    consumer_ref = serializers.CharField(required=False, allow_blank=True, default="")


class RunsListIn(serializers.Serializer):
    dataset_key = serializers.CharField(required=False, allow_blank=True, default="")

