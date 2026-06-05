"""
Tests del módulo org — perfiles de empresa/sucursal y preferencias UoM.

Foco: validación de tipo de OrgUnit en clean()/full_clean() — debe levantar
ValidationError (no ValueError) para que Django/DRF lo recojan correctamente.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.modulos.iam.models import OrgUnit
from apps.modulos.org.models import (
    BranchProfile,
    CompanyProfile,
    UserFuelUoMPreference,
)

User = get_user_model()


def _mk_scope(suffix=""):
    s = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


# ---------------------------------------------------------------------------
# CompanyProfile
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_company_profile_valid():
    _, company, _ = _mk_scope()
    profile = CompanyProfile(company=company, legal_name="ACME S.A.", tax_id="J0310000000001")
    profile.full_clean()  # no debe levantar
    profile.save()
    assert profile.pk is not None


@pytest.mark.django_db
def test_company_profile_wrong_unit_type_raises_validation_error():
    holding, _, branch = _mk_scope()
    # Asignar un BRANCH donde se espera COMPANY
    profile = CompanyProfile(company=branch, legal_name="Mala")
    with pytest.raises(ValidationError):
        profile.full_clean()


@pytest.mark.django_db
def test_company_profile_holding_rejected():
    holding, _, _ = _mk_scope()
    profile = CompanyProfile(company=holding)
    with pytest.raises(ValidationError):
        profile.full_clean()


# ---------------------------------------------------------------------------
# BranchProfile
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_branch_profile_valid():
    _, _, branch = _mk_scope()
    profile = BranchProfile(branch=branch)
    profile.full_clean()
    profile.save()
    assert profile.pk is not None
    # Defaults de UoM de Nicaragua
    assert profile.fuel_default_volume_uom_gasoline == "LITER"
    assert profile.fuel_default_volume_uom_diesel == "GALLON"


@pytest.mark.django_db
def test_branch_profile_wrong_unit_type_raises_validation_error():
    _, company, _ = _mk_scope()
    profile = BranchProfile(branch=company)
    with pytest.raises(ValidationError):
        profile.full_clean()


# ---------------------------------------------------------------------------
# UserFuelUoMPreference
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_user_fuel_pref_valid():
    _, _, branch = _mk_scope()
    user = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")
    pref = UserFuelUoMPreference(user=user, branch=branch, gasoline_volume_uom="GALLON")
    pref.full_clean()
    pref.save()
    assert pref.pk is not None


@pytest.mark.django_db
def test_user_fuel_pref_wrong_unit_type_raises_validation_error():
    holding, company, _ = _mk_scope()
    user = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")
    pref = UserFuelUoMPreference(user=user, branch=company)
    with pytest.raises(ValidationError):
        pref.full_clean()


@pytest.mark.django_db
def test_user_fuel_pref_unique_per_user_branch():
    from django.db import IntegrityError, transaction
    _, _, branch = _mk_scope()
    user = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")
    UserFuelUoMPreference.objects.create(user=user, branch=branch)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            UserFuelUoMPreference.objects.create(user=user, branch=branch)
