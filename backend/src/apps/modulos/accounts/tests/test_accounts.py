"""
Tests del módulo accounts — usuario, validador de contraseña, cookies y auth API.

Validador de complejidad (longitud y clases de caracteres), helpers de cookies
de autenticación (set/clear/csrf), invariantes del modelo User y endpoints de
auth (login ok/ko, bootstrap status público, me protegido).
"""
from __future__ import annotations

import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from rest_framework.test import APIClient

from apps.modulos.accounts.cookies import clear_auth_cookies, issue_csrf_token, set_auth_cookies
from apps.modulos.accounts.password_validators import PasswordComplexityValidator
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RolePermission, UserRole

User = get_user_model()


# ---------------------------------------------------------------------------
# PasswordComplexityValidator
# ---------------------------------------------------------------------------

def test_password_validator_rejects_too_short():
    with pytest.raises(ValidationError) as exc:
        PasswordComplexityValidator(min_length=10, min_classes=3).validate("Ab1!")
    assert exc.value.code == "password_too_short"


def test_password_validator_rejects_low_complexity():
    # 12 chars pero solo minúsculas => 1 clase.
    with pytest.raises(ValidationError) as exc:
        PasswordComplexityValidator(min_length=10, min_classes=3).validate("abcdefghijkl")
    assert exc.value.code == "password_not_complex_enough"


def test_password_validator_accepts_strong_password():
    PasswordComplexityValidator(min_length=10, min_classes=3).validate("Abcdef123!")  # no levanta


def test_password_validator_help_text_mentions_bounds():
    text = PasswordComplexityValidator(min_length=12, min_classes=4).get_help_text()
    assert "12" in text and "4" in text


def test_password_validator_custom_thresholds():
    v = PasswordComplexityValidator(min_length=4, min_classes=2)
    v.validate("ab12")  # cumple longitud 4 y 2 clases
    with pytest.raises(ValidationError):
        v.validate("abcd")  # 1 sola clase


# ---------------------------------------------------------------------------
# Cookies de autenticación
# ---------------------------------------------------------------------------

def test_issue_csrf_token_is_nonempty_and_unique():
    a = issue_csrf_token()
    b = issue_csrf_token()
    assert a and b and a != b


def test_set_auth_cookies_sets_three_cookies_with_flags():
    resp = HttpResponse()
    csrf = set_auth_cookies(resp, access="acc", refresh="ref")
    assert csrf
    assert settings.AUTH_COOKIE_ACCESS_NAME in resp.cookies
    assert settings.AUTH_COOKIE_REFRESH_NAME in resp.cookies
    assert settings.AUTH_COOKIE_CSRF_NAME in resp.cookies
    # access/refresh httponly; csrf legible por el cliente.
    assert resp.cookies[settings.AUTH_COOKIE_ACCESS_NAME]["httponly"]
    assert resp.cookies[settings.AUTH_COOKIE_REFRESH_NAME]["httponly"]
    assert resp.cookies[settings.AUTH_COOKIE_CSRF_NAME]["httponly"] == ""
    assert resp.cookies[settings.AUTH_COOKIE_ACCESS_NAME].value == "acc"


def test_clear_auth_cookies_resets_values():
    resp = HttpResponse()
    set_auth_cookies(resp, access="acc", refresh="ref")
    clear_auth_cookies(resp)
    assert resp.cookies[settings.AUTH_COOKIE_ACCESS_NAME].value == ""


# ---------------------------------------------------------------------------
# Modelo User
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_user_defaults():
    user = User.objects.create_user(
        username=f"u_{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex[:8]}@test.local", password="Abcdef123!"
    )
    assert user.must_change_password is False
    assert user.is_setup_complete is False
    assert user.totp_enabled is False


@pytest.mark.django_db
def test_user_email_unique():
    email = f"{uuid.uuid4().hex[:8]}@test.local"
    User.objects.create_user(username=f"a_{uuid.uuid4().hex[:6]}", email=email, password="Abcdef123!")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(username=f"b_{uuid.uuid4().hex[:6]}", email=email, password="Abcdef123!")


# ---------------------------------------------------------------------------
# API de autenticación
# ---------------------------------------------------------------------------

def _mk_user():
    username = f"acc_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(
        username=username, email=f"{username}@test.local", password="pass12345"
    )


@pytest.mark.django_db
def test_login_success_returns_access_token():
    user = _mk_user()
    resp = APIClient().post(
        "/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json"
    )
    assert resp.status_code == 200, resp.data
    assert resp.data.get("access")


@pytest.mark.django_db
def test_login_wrong_password_is_rejected():
    user = _mk_user()
    resp = APIClient().post(
        "/api/auth/login/", {"username": user.username, "password": "WRONG-pass"}, format="json"
    )
    assert resp.status_code in (400, 401)


@pytest.mark.django_db
def test_bootstrap_status_is_public():
    resp = APIClient().get("/api/auth/bootstrap/status/")
    assert resp.status_code == 200
    assert "setup_required" in resp.data


@pytest.mark.django_db
def test_me_requires_authentication():
    resp = APIClient().get("/api/auth/me/")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_me_returns_user_when_authenticated():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    user = _mk_user()
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)

    resp = client.get("/api/auth/me/")
    assert resp.status_code == 200
    assert resp.data.get("username") == user.username


@pytest.mark.django_db
def test_me_does_not_expose_legacy_global_userrole():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    user = _mk_user()
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"legacy_{s}", is_active=True)
    permission = Permission.objects.create(code=f"legacy.global_{s}", is_active=True)
    RolePermission.objects.create(role=role, permission=permission)
    UserRole.objects.create(user=user, role=role)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)

    resp = client.get("/api/auth/me/")
    assert resp.status_code == 200
    assert role.name not in set(resp.data.get("roles") or [])
    assert permission.code not in set(resp.data.get("permissions") or [])
