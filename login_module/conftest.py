from __future__ import annotations

import pytest
from rest_framework.settings import api_settings


@pytest.fixture(scope="session", autouse=True)
def _disable_throttling_for_tests(django_db_setup, django_db_blocker):
    from django.conf import settings

    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (),
        "DEFAULT_THROTTLE_RATES": {},
    }
    api_settings.reload()
