from rest_framework import serializers
from .models import Role, Permission, RoleAssignment


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "description", "is_active"]


class AssignmentCreateIn(serializers.Serializer):
    user_id = serializers.IntegerField()
    role_id = serializers.IntegerField()
    org_unit_id = serializers.IntegerField()
    origin = serializers.ChoiceField(
        choices=[c[0] for c in RoleAssignment.Origin.choices], required=False, default=RoleAssignment.Origin.MANUAL
    )


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "code", "description", "is_active"]
