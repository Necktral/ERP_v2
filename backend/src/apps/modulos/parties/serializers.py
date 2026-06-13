from __future__ import annotations

from rest_framework import serializers

from .models import Party, PartyRole


class PartyCreateIn(serializers.Serializer):
    party_type = serializers.ChoiceField(choices=Party.PartyType.choices)
    display_name = serializers.CharField(max_length=200)
    legal_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    tax_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    national_id = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=PartyRole.Role.choices),
        required=False,
        default=list,
    )


class PartyUpdateIn(serializers.Serializer):
    party_type = serializers.ChoiceField(choices=Party.PartyType.choices, required=False)
    display_name = serializers.CharField(max_length=200, required=False)
    legal_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    tax_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    national_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=64, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=Party.Status.choices, required=False)


class PartyRoleActionIn(serializers.Serializer):
    role = serializers.ChoiceField(choices=PartyRole.Role.choices)


def party_out(party: Party, *, active_roles: list[str] | None = None) -> dict:
    if active_roles is None:
        active_roles = [r.role for r in party.roles.all() if r.is_active]
    return {
        "id": party.id,
        "party_type": party.party_type,
        "display_name": party.display_name,
        "legal_name": party.legal_name,
        "tax_id": party.tax_id,
        "national_id": party.national_id,
        "email": party.email,
        "phone": party.phone,
        "status": party.status,
        "roles": sorted(active_roles),
        "created_at": party.created_at.isoformat(),
    }
