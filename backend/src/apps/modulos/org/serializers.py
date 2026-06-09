from __future__ import annotations

from typing import Any

from rest_framework import serializers


class CompanyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    legal_name = serializers.CharField(required=False, allow_blank=True, default="")
    tax_id = serializers.CharField(required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")


class BranchCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")


class BranchUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    code = serializers.CharField(max_length=64, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    address = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)


class CompanyProfileUpdateSerializer(serializers.Serializer):
    legal_name = serializers.CharField(required=False, allow_blank=True)
    tax_id = serializers.CharField(required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)


class ModuleStateOut(serializers.Serializer):
    code = serializers.CharField()
    category = serializers.CharField()
    core = serializers.BooleanField()
    is_enabled = serializers.BooleanField()

    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)
        data["label"] = instance.get("label", "") if isinstance(instance, dict) else getattr(instance, "label", "")
        return data


class _ModuleChangeIn(serializers.Serializer):
    code = serializers.CharField()
    is_enabled = serializers.BooleanField()


class ModulesUpdateIn(serializers.Serializer):
    modules = _ModuleChangeIn(many=True)
