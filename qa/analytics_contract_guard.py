#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def _service_block(content: str, service_name: str) -> str:
    lines = content.splitlines()
    start_idx: int | None = None
    end_idx = len(lines)
    service_header = f"  {service_name}:"
    service_re = re.compile(r"^  [a-zA-Z0-9_-]+:\s*$")

    for idx, line in enumerate(lines):
        if line.startswith(service_header):
            start_idx = idx
            break
    if start_idx is None:
        return ""

    for idx in range(start_idx + 1, len(lines)):
        if service_re.match(lines[idx]):
            end_idx = idx
            break

    return "\n".join(lines[start_idx:end_idx]) + "\n"


def _require_pattern(content: str, pattern: str, message: str, failures: list[str]) -> None:
    if not re.search(pattern, content, flags=re.MULTILINE):
        failures.append(message)


def _validate_compose_dev(root: Path, failures: list[str]) -> None:
    path = root / "compose.yaml"
    if not path.exists():
        failures.append("compose.yaml missing")
        return
    content = path.read_text(encoding="utf-8", errors="ignore")
    block = _service_block(content, "dash_analytics")
    if not block:
        failures.append("compose.yaml: service dash_analytics missing")
        return

    _require_pattern(
        block,
        r"\s+DASH_URL_PREFIX:\s*/analytics",
        "compose.yaml: dash_analytics must set DASH_URL_PREFIX=/analytics",
        failures,
    )
    _require_pattern(
        block,
        r"\s+DASH_INTERNAL_PORT:\s*\"8050\"",
        "compose.yaml: dash_analytics must set DASH_INTERNAL_PORT=\"8050\"",
        failures,
    )
    _require_pattern(
        block,
        r"\s+ports:\n\s*-\s*\"8050:8050\"",
        "compose.yaml: dash_analytics must publish 8050:8050 in dev",
        failures,
    )
    _require_pattern(
        block,
        r"http://localhost:8050/analytics/health",
        "compose.yaml: dash_analytics healthcheck must target http://localhost:8050/analytics/health",
        failures,
    )


def _validate_compose_prod(root: Path, failures: list[str]) -> None:
    path = root / "compose.prod.yaml"
    if not path.exists():
        failures.append("compose.prod.yaml missing")
        return
    content = path.read_text(encoding="utf-8", errors="ignore")
    block = _service_block(content, "dash_analytics")
    if not block:
        failures.append("compose.prod.yaml: service dash_analytics missing")
        return

    _require_pattern(
        block,
        r"\s+DASH_URL_PREFIX:\s*/analytics",
        "compose.prod.yaml: dash_analytics must set DASH_URL_PREFIX=/analytics",
        failures,
    )
    _require_pattern(
        block,
        r"\s+DASH_INTERNAL_PORT:\s*\"8050\"",
        "compose.prod.yaml: dash_analytics must set DASH_INTERNAL_PORT=\"8050\"",
        failures,
    )
    _require_pattern(
        block,
        r"\s+expose:\n\s*-\s*\"8050\"",
        "compose.prod.yaml: dash_analytics must expose 8050 internally",
        failures,
    )
    if re.search(r"\s+ports:\n", block, flags=re.MULTILINE):
        failures.append("compose.prod.yaml: dash_analytics must not publish host ports (same-origin only)")
    _require_pattern(
        block,
        r"http://localhost:8050/analytics/health",
        "compose.prod.yaml: dash_analytics healthcheck must target http://localhost:8050/analytics/health",
        failures,
    )


def _validate_proxy_and_dash(root: Path, failures: list[str]) -> None:
    nginx_path = root / "docker" / "nginx" / "default.conf"
    if not nginx_path.exists():
        failures.append("docker/nginx/default.conf missing")
    else:
        nginx = nginx_path.read_text(encoding="utf-8", errors="ignore")
        _require_pattern(
            nginx,
            r"location\s+\^~\s+/analytics/",
            "nginx default.conf: must proxy /analytics/ location",
            failures,
        )
        _require_pattern(
            nginx,
            r"proxy_pass\s+http://dash_analytics:8050;",
            "nginx default.conf: /analytics/ must proxy to dash_analytics:8050",
            failures,
        )

    dash_app_path = root / "dash_analytics" / "app.py"
    if not dash_app_path.exists():
        failures.append("dash_analytics/app.py missing")
    else:
        dash_app = dash_app_path.read_text(encoding="utf-8", errors="ignore")
        _require_pattern(
            dash_app,
            r"DASH_URL_PREFIX\s*=\s*os\.getenv\(\"DASH_URL_PREFIX\",\s*\"/analytics\"\)",
            "dash_analytics/app.py: DASH_URL_PREFIX default must be /analytics",
            failures,
        )
        _require_pattern(
            dash_app,
            r"DASH_INTERNAL_PORT\s*=\s*int\(os\.getenv\(\"DASH_INTERNAL_PORT\"\)\s*or\s*os\.getenv\(\"DASH_PORT\",\s*\"8050\"\)\)",
            "dash_analytics/app.py: DASH_INTERNAL_PORT must default to 8050 (with DASH_PORT fallback)",
            failures,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate frozen analytics contract (port/prefix/proxy).")
    parser.add_argument("--root", default=".", help="Repository root path")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    failures: list[str] = []
    _validate_compose_dev(root, failures)
    _validate_compose_prod(root, failures)
    _validate_proxy_and_dash(root, failures)

    if failures:
        print("[qa] analytics contract guard failed")
        for failure in failures:
            print(f" - {failure}")
        return 2

    print("[qa] analytics contract guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
