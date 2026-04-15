import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership

User = get_user_model()


def _authenticated_client(*, username: str = "u_bootstrap") -> tuple[APIClient, OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

    user = User.objects.create_user(username=username, password="pass12345")
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    access = login.data.get("access")
    assert isinstance(access, str)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client, company, branch


@pytest.mark.django_db
def test_bootstrap_session_requires_authentication():
    client = APIClient()
    response = client.get("/api/auth/bootstrap/session/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_bootstrap_session_returns_canonical_shape_for_authenticated_user():
    client, company, branch = _authenticated_client()
    response = client.get(
        "/api/auth/bootstrap/session/",
        HTTP_X_DEVICE_CLASS="mobile",
        HTTP_X_SOURCE_DEVICE="web-mobile-test",
        HTTP_X_CHANNEL="web",
    )
    assert response.status_code == 200

    data = response.data
    assert data["shell_mode"] == "mobile"
    assert "dashboard" in data["allowed_modules"]

    user_payload = data["user"]
    assert user_payload["username"] == "u_bootstrap"
    assert user_payload["is_setup_complete"] is True

    device_payload = data["device"]
    assert device_payload["device_class"] == "mobile"
    assert device_payload["source_device"] == "web-mobile-test"

    context_payload = data["effective_context"]
    assert context_payload["recommended_company_id"] == str(company.id)
    assert context_payload["recommended_branch_id"] == str(branch.id)

    capabilities = data["capabilities"]["acl_snapshot"]
    assert capabilities["recommended_company_id"] == str(company.id)
    assert capabilities["recommended_branch_id"] == str(branch.id)
    assert isinstance(capabilities["companies"], list)

    trace_payload = data["trace"]
    assert isinstance(trace_payload["request_id"], str)
    assert trace_payload["channel"] == "web"
    assert trace_payload["source_device"] == "web-mobile-test"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("header_device", "expected_shell"),
    [
        ("desktop", "desktop"),
        ("mobile", "mobile"),
    ],
)
def test_bootstrap_session_shell_mode_honors_explicit_device_class(
    header_device: str,
    expected_shell: str,
):
    client, _, _ = _authenticated_client(username=f"u_{header_device}")
    response = client.get("/api/auth/bootstrap/session/", HTTP_X_DEVICE_CLASS=header_device)
    assert response.status_code == 200
    assert response.data["device"]["device_class"] == header_device
    assert response.data["shell_mode"] == expected_shell


@pytest.mark.django_db
def test_bootstrap_session_shell_mode_falls_back_to_ua_when_header_invalid():
    client, _, _ = _authenticated_client(username="u_invalid_header")
    response = client.get(
        "/api/auth/bootstrap/session/",
        HTTP_X_DEVICE_CLASS="tablet",
        HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit",
    )
    assert response.status_code == 200
    assert response.data["device"]["device_class"] == "mobile"
    assert response.data["shell_mode"] == "mobile"


@pytest.mark.django_db
def test_bootstrap_session_shell_mode_defaults_to_desktop_without_valid_hints():
    client, _, _ = _authenticated_client(username="u_desktop_fallback")
    response = client.get("/api/auth/bootstrap/session/", HTTP_X_DEVICE_CLASS="invalid")
    assert response.status_code == 200
    assert response.data["device"]["device_class"] == "desktop"
    assert response.data["shell_mode"] == "desktop"
