from __future__ import annotations

from rest_framework import serializers


class EmbedTokenIn(serializers.Serializer):
    workspace_key = serializers.CharField(max_length=64)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    require_compose = serializers.BooleanField(required=False, default=False)


class RedeemEmbedTokenIn(serializers.Serializer):
    token = serializers.CharField()
