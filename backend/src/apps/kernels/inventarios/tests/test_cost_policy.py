"""Tests de la política de costo versionada (invariante #8)."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.inventarios.costing import (
    get_active_cost_policy,
    resolve_active_cost_policy_version,
    resolve_costing_method,
    set_cost_policy,
)
from apps.kernels.inventarios.models import CostingMethod, InventoryCostPolicy
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _scope():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    user = User.objects.create_user(username=f"u_{t}", email=f"u_{t}@test.local", password="Secret123!")
    return company, branch, user


@pytest.mark.django_db
def test_default_method_is_weighted_average_when_no_policy():
    company, branch, _ = _scope()
    assert resolve_costing_method(company=company, branch=branch) == CostingMethod.WEIGHTED_AVERAGE
    assert resolve_active_cost_policy_version(company=company, branch=branch) == 0
    assert get_active_cost_policy(company=company, branch=branch) is None


@pytest.mark.django_db
def test_set_policy_creates_v1_and_resolves():
    company, _, user = _scope()
    policy = set_cost_policy(actor=user, company=company, method=CostingMethod.STANDARD, params={"x": 1})
    assert policy.version == 1
    assert policy.is_active is True
    assert resolve_costing_method(company=company) == CostingMethod.STANDARD
    assert resolve_active_cost_policy_version(company=company) == 1


@pytest.mark.django_db
def test_changing_policy_versions_and_closes_previous():
    company, _, user = _scope()
    v1 = set_cost_policy(actor=user, company=company, method=CostingMethod.WEIGHTED_AVERAGE)
    v2 = set_cost_policy(actor=user, company=company, method=CostingMethod.FIFO)
    v1.refresh_from_db()
    assert v1.is_active is False
    assert v1.effective_to is not None
    assert v2.version == 2 and v2.is_active is True
    # Una sola política activa por scope.
    assert InventoryCostPolicy.objects.filter(company=company, branch__isnull=True, is_active=True).count() == 1
    assert resolve_costing_method(company=company) == CostingMethod.FIFO


@pytest.mark.django_db
def test_branch_policy_overrides_company_with_fallback():
    company, branch, user = _scope()
    other_branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B2_{uuid.uuid4().hex[:4]}"
    )
    set_cost_policy(actor=user, company=company, branch=None, method=CostingMethod.WEIGHTED_AVERAGE)
    set_cost_policy(actor=user, company=company, branch=branch, method=CostingMethod.STANDARD)

    # La sucursal con política propia resuelve la suya...
    assert resolve_costing_method(company=company, branch=branch) == CostingMethod.STANDARD
    # ...otra sucursal sin política propia cae al fallback de empresa.
    assert resolve_costing_method(company=company, branch=other_branch) == CostingMethod.WEIGHTED_AVERAGE


@pytest.mark.django_db
def test_invalid_method_raises():
    company, _, user = _scope()
    with pytest.raises(ValueError):
        set_cost_policy(actor=user, company=company, method="NOT_A_METHOD")
