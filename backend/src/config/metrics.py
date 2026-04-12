from __future__ import annotations

import threading
import time
from collections import Counter, deque
from typing import Any


_start_time = time.time()
_lock = threading.Lock()
_status_counts: Counter[str] = Counter()
_method_counts: Counter[str] = Counter()
_path_counts: Counter[str] = Counter()
_legacy_prefix_counts: Counter[str] = Counter()
_latency_sum_ms = 0
_latency_max_ms = 0
_total_requests = 0
_sync_channel_counts: Counter[str] = Counter()
_sync_error_counts: Counter[str] = Counter()
_sync_replay_rejected = 0
_sync_batch_latency_ms: deque[int] = deque(maxlen=5000)
_pos_checkout_total = 0
_pos_checkout_ok = 0
_pos_checkout_error = 0
_pos_checkout_error_by_reason: Counter[str] = Counter()
_pos_checkout_latency_ms: deque[int] = deque(maxlen=5000)


def _normalize_path(path: str) -> str:
    if not path:
        return ""
    if path.startswith("/api/"):
        parts = path.strip("/").split("/")
        if len(parts) >= 2:
            return f"/api/{parts[1]}"
        return "/api"
    return path


def record_request(request, *, status_code: int | None, duration_ms: int) -> None:
    global _latency_sum_ms
    global _latency_max_ms
    global _total_requests

    code = int(status_code or 0)
    family = f"{code // 100}xx" if code else "0xx"
    method = (getattr(request, "method", "") or "").upper()
    path = _normalize_path(getattr(request, "path", "") or "")
    legacy_prefix = str(getattr(request, "_legacy_api_prefix", "") or "").strip()

    with _lock:
        _total_requests += 1
        _latency_sum_ms += int(duration_ms)
        _latency_max_ms = max(_latency_max_ms, int(duration_ms))
        _status_counts[family] += 1
        _status_counts[str(code)] += 1
        if method:
            _method_counts[method] += 1
        if path:
            _path_counts[path] += 1
        if legacy_prefix:
            _legacy_prefix_counts[legacy_prefix] += 1


def _top(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [{"key": k, "count": v} for k, v in counter.most_common(limit)]


def _percentile(values: list[int], q: float) -> float | None:
    if not values:
        return None
    if q <= 0:
        return float(min(values))
    if q >= 1:
        return float(max(values))
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * q))
    idx = max(0, min(idx, len(ordered) - 1))
    return float(ordered[idx])


def record_sync_batch(
    *,
    channel: str,
    status: str,
    duration_ms: int,
    error_code: str = "",
) -> None:
    global _sync_replay_rejected
    ch = str(channel or "").strip() or "unknown"
    st = str(status or "").strip().upper() or "UNKNOWN"
    err = str(error_code or "").strip()
    with _lock:
        _sync_channel_counts[ch] += 1
        _sync_channel_counts[f"status:{st}"] += 1
        _sync_batch_latency_ms.append(int(duration_ms))
        if err:
            _sync_error_counts[err] += 1
            if err == "REPLAY_DETECTED":
                _sync_replay_rejected += 1


def record_pos_checkout(*, ok: bool, reason: str, started_at) -> None:
    global _pos_checkout_total
    global _pos_checkout_ok
    global _pos_checkout_error
    if hasattr(started_at, "timestamp"):
        duration_ms = max(0, int((time.time() - float(started_at.timestamp())) * 1000))
    else:
        duration_ms = max(0, int((time.perf_counter() - float(started_at)) * 1000))
    with _lock:
        _pos_checkout_total += 1
        if ok:
            _pos_checkout_ok += 1
        else:
            _pos_checkout_error += 1
            if reason:
                _pos_checkout_error_by_reason[str(reason)] += 1
        _pos_checkout_latency_ms.append(duration_ms)


def snapshot() -> dict:
    with _lock:
        total = _total_requests
        avg_ms = int(_latency_sum_ms / total) if total else 0
        sync_total = int(_sync_channel_counts.get("sync_v2", 0) + _sync_channel_counts.get("sync_legacy", 0))
        sync_v2 = int(_sync_channel_counts.get("sync_v2", 0))
        sync_legacy = int(_sync_channel_counts.get("sync_legacy", 0))
        sync_v2_pct = round((sync_v2 * 100.0 / sync_total), 2) if sync_total else 0.0
        return {
            "uptime_seconds": int(time.time() - _start_time),
            "total_requests": total,
            "latency_ms_avg": avg_ms,
            "latency_ms_max": int(_latency_max_ms),
            "status_counts": dict(_status_counts),
            "method_counts": dict(_method_counts),
            "top_paths": _top(_path_counts, limit=15),
            "legacy_api_counts": dict(_legacy_prefix_counts),
            "sync": {
                "requests_total": sync_total,
                "requests_v2": sync_v2,
                "requests_legacy": sync_legacy,
                "v2_share_pct": sync_v2_pct,
                "replay_rejected": int(_sync_replay_rejected),
                "errors_by_code": dict(_sync_error_counts),
                "batch_latency_p95_ms": _percentile(list(_sync_batch_latency_ms), 0.95),
            },
            "retail_pos": {
                "checkout_total": int(_pos_checkout_total),
                "checkout_ok": int(_pos_checkout_ok),
                "checkout_error": int(_pos_checkout_error),
                "checkout_error_by_reason": dict(_pos_checkout_error_by_reason),
                "checkout_latency_p95_ms": _percentile(list(_pos_checkout_latency_ms), 0.95),
            },
        }
