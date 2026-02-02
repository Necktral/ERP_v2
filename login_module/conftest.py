from __future__ import annotations

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    try:
        cache.clear()
    except Exception:
        pass
    yield
    try:
        cache.clear()
    except Exception:
        pass
