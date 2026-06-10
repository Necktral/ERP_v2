import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _demo_pwd(label: str) -> str:
    return f"Aa!9_{label}_Zx7"


@pytest.mark.django_db
def test_bootstrap_status_fresh_when_no_users():
    client = APIClient()
    r = client.get("/api/auth/bootstrap/status/")
    assert r.status_code == 200
    assert r.data["is_fresh"] is True


@pytest.mark.django_db
def test_bootstrap_init_creates_first_admin():
    client = APIClient()
    root_pwd = _demo_pwd("root")
    r = client.post(
        "/api/auth/bootstrap/init/",
        {
            "username": "root",
            "email": "root@test.com",
            "password": root_pwd,
            "password_confirm": root_pwd,
        },
        format="json",
    )
    assert r.status_code == 201
    u = User.objects.get(username="root")
    assert u.is_superuser is True
    assert u.is_staff is True
    assert u.must_change_password is False

    r2 = client.get("/api/auth/bootstrap/status/")
    assert r2.status_code == 200
    assert r2.data["is_fresh"] is False


@pytest.mark.django_db
def test_bootstrap_init_rejects_password_mismatch():
    client = APIClient()
    r = client.post(
        "/api/auth/bootstrap/init/",
        {
            "username": "root",
            "email": "root@test.com",
            "password": _demo_pwd("ok"),
            "password_confirm": _demo_pwd("different"),
        },
        format="json",
    )
    assert r.status_code == 400
    # La API envuelve los errores de validación en {"error": {"details": {...}}}.
    assert "password_confirm" in r.data["error"]["details"]
    assert not User.objects.filter(username="root").exists()


@pytest.mark.django_db
@override_settings(
    AUTH_PASSWORD_VALIDATORS=[
        {
            "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
            "OPTIONS": {"min_length": 10},
        },
        {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
        {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
        {
            "NAME": "apps.modulos.accounts.password_validators.PasswordComplexityValidator",
            "OPTIONS": {"min_length": 10, "min_classes": 3},
        },
    ]
)
def test_bootstrap_status_exposes_password_policy():
    # El settings de test vacía los validadores; forzamos los reales (como en base/prod)
    # para verificar que _password_policy() los deriva correctamente (fuente única).
    r = APIClient().get("/api/auth/bootstrap/status/")
    assert r.status_code == 200
    policy = r.data["password_policy"]
    assert policy["min_length"] == 10
    assert policy["min_classes"] == 3
    assert policy["disallow_common"] is True
    assert policy["disallow_numeric_only"] is True
    assert "minúsculas" in policy["classes"]


@pytest.mark.django_db
def test_bootstrap_org_requires_auth_but_no_company_context_header():
    # 1) bootstrap init
    c = APIClient()
    root_pwd = _demo_pwd("root2")
    c.post(
        "/api/auth/bootstrap/init/",
        {
            "username": "root",
            "email": "root2@test.com",
            "password": root_pwd,
            "password_confirm": root_pwd,
        },
        format="json",
    )

    # 2) login
    login = c.post("/api/auth/login/", {"username": "root", "password": root_pwd}, format="json")
    assert login.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    # 3) bootstrap org (sin X-Company-Id)
    r = c.post(
        "/api/auth/bootstrap/org/",
        {
            "holding_name": "HOLDING",
            "company_name": "ACME",
            "company_tax_id": "J-123",
            "branch_name": "ACME-1",
            "branch_address": "Main street",
        },
        format="json",
    )
    assert r.status_code == 200
    assert OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING).exists()
    assert OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY).exists()
    assert OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.BRANCH).exists()

    # 4) /me refleja setup complete
    me = c.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["is_setup_complete"] is True


@pytest.mark.django_db
def test_password_change_clears_must_change_password():
    temp_pwd = _demo_pwd("temp")
    new_pwd = _demo_pwd("new")
    u = User.objects.create_user(username="emp", password=temp_pwd, email="emp@test.com")
    u.must_change_password = True
    u.save(update_fields=["must_change_password"])

    c = APIClient()
    login = c.post("/api/auth/login/", {"username": "emp", "password": temp_pwd}, format="json")
    assert login.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = c.post(
        "/api/auth/password/",
        {
            "old_password": temp_pwd,
            "new_password": new_pwd,
            "confirm_password": new_pwd,
        },
        format="json",
    )
    assert r.status_code == 200
    u.refresh_from_db()
    assert u.must_change_password is False

    # login with new password works
    c2 = APIClient()
    login2 = c2.post("/api/auth/login/", {"username": "emp", "password": new_pwd}, format="json")
    assert login2.status_code == 200
