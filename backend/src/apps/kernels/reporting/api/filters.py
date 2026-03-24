from __future__ import annotations

from typing import Any


def sanitize_filters(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        return {}
    return dict(payload)

