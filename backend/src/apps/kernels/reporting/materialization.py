from __future__ import annotations

from typing import Any


def resolve_materialization_strategy(*, freshness_mode: str, materialization_policy: str) -> dict[str, Any]:
    # R0-R2: ejecución live/online sobre kernels fuente. Snapshot/cache se implementa en R4.
    return {
        "freshness_mode": freshness_mode,
        "materialization_policy": materialization_policy,
        "strategy": "LIVE_EXECUTION",
    }

