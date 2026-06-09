from __future__ import annotations

from rest_framework import serializers

from .models import DevicePlatform


class DeviceTokenSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=DevicePlatform.choices)
    token = serializers.CharField(max_length=512)
