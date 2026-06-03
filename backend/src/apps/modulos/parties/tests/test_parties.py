"""
Tests del módulo parties — modelo Party/PartyRole y servicios de dominio.

Foco: normalización e invariantes de Party (display_name obligatorio, company
debe ser COMPANY, unicidad de tax_id/national_id por empresa), invariantes de
PartyRole (vigencias, rol activo único) y los servicios create/update/assign/
revoke (que además emiten auditoría).
"""
from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit
from apps.modulos.parties.models import Party, PartyRole
from apps.modulos.parties.services import (
    assign_party_role,
    create_party,
    revoke_party_role,
    update_party,
)


def _mk_company():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    return holding, company


# ---------------------------------------------------------------------------
# Party — modelo
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_party_save_normalizes_fields():
    _, company = _mk_company()
    party = Party(
        company=company,
        party_type=Party.PartyType.NATURAL,
        display_name="  Juan Perez  ",
        legal_name="  Juan Perez SA ",
        tax_id="  j0310  ",
        national_id=" abc123 ",
        email="  JUAN@Mail.COM ",
        phone="  88990011 ",
    )
    party.save()
    assert party.display_name == "Juan Perez"
    assert party.legal_name == "Juan Perez SA"
    assert party.tax_id == "J0310"
    assert party.national_id == "ABC123"
    assert party.email == "juan@mail.com"
    assert party.phone == "88990011"


@pytest.mark.django_db
def test_party_requires_display_name():
    _, company = _mk_company()
    party = Party(company=company, party_type=Party.PartyType.NATURAL, display_name="   ")
    with pytest.raises(ValidationError):
        party.save()


@pytest.mark.django_db
def test_party_company_must_be_company_type():
    holding, _ = _mk_company()
    party = Party(company=holding, party_type=Party.PartyType.JURIDICAL, display_name="Bad")
    with pytest.raises(ValidationError):
        party.save()


@pytest.mark.django_db
def test_party_unique_tax_id_per_company_is_case_insensitive():
    _, company = _mk_company()
    Party(company=company, party_type=Party.PartyType.JURIDICAL, display_name="A", tax_id="abc").save()
    dup = Party(company=company, party_type=Party.PartyType.JURIDICAL, display_name="B", tax_id="ABC")
    with pytest.raises(ValidationError):
        dup.save()


@pytest.mark.django_db
def test_party_empty_tax_id_allows_multiple():
    _, company = _mk_company()
    Party(company=company, party_type=Party.PartyType.NATURAL, display_name="A", tax_id="").save()
    # tax_id vacío está excluido del unique parcial → no debe colisionar.
    Party(company=company, party_type=Party.PartyType.NATURAL, display_name="B", tax_id="").save()
    assert Party.objects.filter(company=company, tax_id="").count() == 2


@pytest.mark.django_db
def test_partyrole_valid_to_before_from_raises():
    _, company = _mk_company()
    party = Party(company=company, party_type=Party.PartyType.NATURAL, display_name="P")
    party.save()
    now = timezone.now()
    role = PartyRole(
        party=party,
        role=PartyRole.Role.CUSTOMER,
        valid_from=now,
        valid_to=now - timezone.timedelta(days=1),
    )
    with pytest.raises(ValidationError):
        role.save()


# ---------------------------------------------------------------------------
# Servicios
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_party_persists_and_normalizes():
    _, company = _mk_company()
    party = create_party(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name="ACME",
        tax_id="j0310000000001",
    )
    assert party.pk is not None
    assert party.tax_id == "J0310000000001"
    assert Party.objects.filter(pk=party.pk).exists()


@pytest.mark.django_db
def test_create_party_wrong_company_type_raises():
    holding, _ = _mk_company()
    with pytest.raises(ValidationError):
        create_party(company=holding, party_type=Party.PartyType.NATURAL, display_name="Bad")


@pytest.mark.django_db
def test_update_party_changes_allowed_fields():
    _, company = _mk_company()
    party = create_party(company=company, party_type=Party.PartyType.NATURAL, display_name="Old")
    updated = update_party(party=party, display_name="New", status=Party.Status.BLOCKED)
    assert updated.display_name == "New"
    assert updated.status == Party.Status.BLOCKED
    updated.refresh_from_db()
    assert updated.display_name == "New"


@pytest.mark.django_db
def test_update_party_unknown_field_raises_value_error():
    _, company = _mk_company()
    party = create_party(company=company, party_type=Party.PartyType.NATURAL, display_name="Old")
    with pytest.raises(ValueError):
        update_party(party=party, not_a_field="x")


@pytest.mark.django_db
def test_assign_party_role_creates_and_blocks_duplicate_active():
    _, company = _mk_company()
    party = create_party(company=company, party_type=Party.PartyType.NATURAL, display_name="P")
    role = assign_party_role(party=party, role=PartyRole.Role.CUSTOMER)
    assert role.is_active is True
    with pytest.raises(ValidationError):
        assign_party_role(party=party, role=PartyRole.Role.CUSTOMER)


@pytest.mark.django_db
def test_revoke_party_role_deactivates_and_allows_reassign():
    _, company = _mk_company()
    party = create_party(company=company, party_type=Party.PartyType.NATURAL, display_name="P")
    assign_party_role(party=party, role=PartyRole.Role.SUPPLIER)
    revoked = revoke_party_role(party=party, role=PartyRole.Role.SUPPLIER)
    assert revoked.is_active is False
    assert revoked.valid_to is not None
    # Tras revocar, el rol vuelve a poder asignarse (unicidad es solo sobre activos).
    again = assign_party_role(party=party, role=PartyRole.Role.SUPPLIER)
    assert again.is_active is True
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.SUPPLIER).count() == 2


@pytest.mark.django_db
def test_revoke_without_active_role_raises():
    _, company = _mk_company()
    party = create_party(company=company, party_type=Party.PartyType.NATURAL, display_name="P")
    with pytest.raises(ValidationError):
        revoke_party_role(party=party, role=PartyRole.Role.EMPLOYEE)
