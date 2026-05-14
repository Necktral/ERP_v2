from __future__ import annotations

import os
import sys

import pytest
from django.conf import settings
from django.core.cache import caches

collect_ignore = ["src/tests/test_auth_throttling.py"]

EXPECTED_DJANGO_SETTINGS_MODULE = "config.settings.test"
ALLOW_NON_TEST_SETTINGS_ENV = "ALLOW_NON_TEST_DJANGO_SETTINGS_FOR_PYTEST"


def pytest_sessionstart(session):
    current_settings = os.environ.get("DJANGO_SETTINGS_MODULE") or "<unset>"
    if current_settings == EXPECTED_DJANGO_SETTINGS_MODULE:
        return

    message = (
        "Backend pytest must run with DJANGO_SETTINGS_MODULE=config.settings.test. "
        "Use: make backend-pytest PYTEST_ARGS='...'. "
        f"Current value: {current_settings}"
    )
    if os.environ.get(ALLOW_NON_TEST_SETTINGS_ENV) == "1":
        warning = f"WARNING: {message}; opt-out env {ALLOW_NON_TEST_SETTINGS_ENV}=1 is active."
        print(warning, file=sys.stderr, flush=True)
        return

    pytest.exit(message, returncode=4)


@pytest.fixture(scope="session", autouse=True)
def _log_test_db_target():
    default_db = settings.DATABASES.get("default", {})
    test_name = (default_db.get("TEST") or {}).get("NAME") or default_db.get("NAME")
    slot = os.getenv("PYTEST_DB_SLOT", "")
    worker = os.getenv("PYTEST_XDIST_WORKER", "")
    print(
        f"[pytest-db] default_test_db={test_name} "
        f"slot={slot or '<auto>'} worker={worker or '<none>'}",
        flush=True,
    )


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker:
        default_cache = settings.CACHES.get("default", {})
        settings.CACHES = {
            **settings.CACHES,
            "default": {
                **default_cache,
                "KEY_PREFIX": f"throttle:{worker}",
            },
        }
        try:
            caches._caches = {}
        except Exception:
            pass

    cache = caches["default"]
    try:
        cache.clear()
    except Exception:
        pass
    yield
    try:
        cache.clear()
    except Exception:
        pass
