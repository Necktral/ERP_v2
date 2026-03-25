from __future__ import annotations

import os

import pytest
from django.conf import settings
from django.core.cache import caches

collect_ignore = ["src/tests/test_auth_throttling.py"]


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
