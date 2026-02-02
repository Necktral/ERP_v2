from __future__ import annotations

import uuid

import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.settings import api_settings
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.mark.django_db
def test_login_throttling_enveloped():
    user = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="pass12345")

    override = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),
            "auth_login": "1/min",
        },
    }

    with override_settings(REST_FRAMEWORK=override):
        api_settings.reload()
        try:
            client = APIClient()

            r1 = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
            assert r1.status_code == 200

            r2 = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
            assert r2.status_code == 429
            payload = r2.json()
            assert payload["error"]["code"] == "RATE_LIMITED"
            assert r2["X-Request-Id"] == payload["error"]["request_id"]
        finally:
            api_settings.reload()
