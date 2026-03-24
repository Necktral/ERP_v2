#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_PERCENT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)%")
_HTTP_REQS_RATE_RE = re.compile(r"http_reqs[.]+:\s*[0-9]+\s+([0-9]+(?:\.[0-9]+)?)/s")
_AUTH_LOGIN_P95_RE = re.compile(
    r"\{[^}]*name:auth_login[^}]*\}[.]+:.*p\(95\)=([0-9]+(?:\.[0-9]+)?(?:ms|s|us|µs))"
)
_AUTH_ME_P95_RE = re.compile(
    r"\{[^}]*name:auth_me[^}]*\}[.]+:.*p\(95\)=([0-9]+(?:\.[0-9]+)?(?:ms|s|us|µs|0s))"
)
_AUTH_ACL_P95_RE = re.compile(
    r"\{[^}]*name:auth_acl[^}]*\}[.]+:.*p\(95\)=([0-9]+(?:\.[0-9]+)?(?:ms|s|us|µs|0s))"
)
_DURATION_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(ms|s|us|µs|m)$")


def _last_match(pattern: re.Pattern[str], text: str) -> str | None:
    found = pattern.findall(text)
    if not found:
        return None
    value = found[-1]
    return value if isinstance(value, str) else value[-1]


def _duration_to_ms(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "0s":
        return 0.0
    match = _DURATION_RE.match(raw)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return value * 60_000.0
    if unit == "s":
        return value * 1_000.0
    if unit == "ms":
        return value
    if unit in {"us", "µs"}:
        return value / 1_000.0
    return None


def _parse_metrics(log_text: str) -> dict[str, Any]:
    failed_rate = _last_match(_PERCENT_RE, "\n".join([line for line in log_text.splitlines() if "http_req_failed" in line]))
    login_p95_raw = _last_match(_AUTH_LOGIN_P95_RE, log_text)
    me_p95_raw = _last_match(_AUTH_ME_P95_RE, log_text)
    acl_p95_raw = _last_match(_AUTH_ACL_P95_RE, log_text)
    http_reqs_rate = _last_match(_HTTP_REQS_RATE_RE, log_text)

    return {
        "http_req_failed_rate_pct": float(failed_rate) if failed_rate is not None else None,
        "auth_login_p95_ms": _duration_to_ms(login_p95_raw),
        "auth_me_p95_ms": _duration_to_ms(me_p95_raw),
        "auth_acl_p95_ms": _duration_to_ms(acl_p95_raw),
        "http_reqs_per_sec": float(http_reqs_rate) if http_reqs_rate is not None else None,
    }


def _backend_counters(backend_log_text: str) -> dict[str, int]:
    return {
        "backend_http_429_count": len(re.findall(r'HTTP/1\.1"\s+429\b', backend_log_text)),
        "backend_http_5xx_count": len(re.findall(r'HTTP/1\.1"\s+5[0-9][0-9]\b', backend_log_text)),
        "backend_traceback_count": len(re.findall(r"\bTraceback\b|\bException\b", backend_log_text)),
    }


def _classify_failure(*, profile: str, exit_code: int, metrics: dict[str, Any], backend: dict[str, int]) -> tuple[str, str]:
    # Clasificación determinística para triage:
    # - app_error: evidencia backend 5xx/traceback
    # - throttle_mismatch: 429 por perfil/carga desalineados
    # - latency_regression: p95 login excede objetivo del perfil
    # - infra_error: salida no-cero sin firma clara de aplicación
    if exit_code == 0:
        return "none", ""

    if backend["backend_http_5xx_count"] > 0 or backend["backend_traceback_count"] > 0:
        return "app_error", "backend_5xx_or_traceback_detected"

    if backend["backend_http_429_count"] > 0:
        if profile == "security":
            return "throttle_mismatch", "security_profile_hit_auth_throttle"
        return "throttle_mismatch", "performance_profile_hit_auth_throttle"

    login_limit_ms = 900.0 if profile == "performance" else 600.0
    login_p95_ms = metrics.get("auth_login_p95_ms")
    if isinstance(login_p95_ms, (int, float)) and login_p95_ms > login_limit_ms:
        return "latency_regression", f"auth_login_p95_ms>{login_limit_ms}"

    return "infra_error", "non_zero_exit_without_app_signature"


def _build_payload(*, profile: str, exit_code: int, log_text: str, backend_log_text: str) -> dict[str, Any]:
    metrics = _parse_metrics(log_text)
    backend = _backend_counters(backend_log_text)
    failure_class, reason = _classify_failure(
        profile=profile,
        exit_code=exit_code,
        metrics=metrics,
        backend=backend,
    )

    # Threshold de login por perfil (dual gate3 contract).
    login_limit_ms = 900.0 if profile == "performance" else 600.0
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "passed": exit_code == 0,
        "exit_code": exit_code,
        "failure_class": failure_class,
        "failure_reason": reason,
        "thresholds": {
            "http_req_failed_rate_pct_max": 1.0,
            "auth_login_p95_ms_max": login_limit_ms,
            "auth_me_p95_ms_max": 500.0,
            "auth_acl_p95_ms_max": 600.0,
        },
        "metrics": {
            **metrics,
            **backend,
        },
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic Gate3 summary report")
    parser.add_argument("--profile", required=True, choices=["security", "performance"])
    parser.add_argument("--exit-code", required=True, type=int)
    parser.add_argument("--log", required=True)
    parser.add_argument("--backend-log", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    log_text = Path(args.log).read_text(encoding="utf-8", errors="ignore") if Path(args.log).exists() else ""
    backend_log_text = (
        Path(args.backend_log).read_text(encoding="utf-8", errors="ignore")
        if Path(args.backend_log).exists()
        else ""
    )

    payload = _build_payload(
        profile=args.profile,
        exit_code=args.exit_code,
        log_text=log_text,
        backend_log_text=backend_log_text,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    status = "PASS" if payload["passed"] else "FAIL"
    print(
        f"[qa] gate3 summary: {status} profile={args.profile} "
        f"failure_class={payload['failure_class']} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
