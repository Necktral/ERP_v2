#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _test_secret_b64() -> str:
    return base64.b64encode(b"pos-edge-secret-test-key-001").decode("utf-8")


def _build_expected_signature(
    *,
    secret_b64: str,
    challenge_id: str,
    nonce: str,
    company_id: int,
    branch_id: int,
    connector_id: str,
) -> str:
    secret = base64.b64decode(secret_b64.encode("utf-8"), validate=True)
    msg = f"{challenge_id}.{nonce}.{company_id}.{branch_id}.{connector_id}".encode("utf-8")
    digest = hmac.new(secret, msg, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _run_simulator(*, root: Path, profile: str) -> dict[str, Any]:
    script = root / "qa" / "simulate_retail_pos_edge.py"
    args = [
        sys.executable,
        str(script),
        "--challenge-id",
        "00000000-0000-0000-0000-000000000001",
        "--nonce",
        "nonce-edge-001",
        "--company-id",
        "101",
        "--branch-id",
        "7",
        "--connector-id",
        "edge-ci-01",
        "--connector-version",
        "0.2.0",
        "--secret-b64",
        _test_secret_b64(),
        "--profile",
        profile,
    ]
    proc = subprocess.run(args, cwd=str(root), check=True, capture_output=True, text=True)
    return json.loads(proc.stdout)


def _validate_payload(*, payload: dict[str, Any], profile: str) -> list[str]:
    errors: list[str] = []
    required_top = {
        "challenge_id",
        "connector_id",
        "connector_version",
        "signature",
        "capability_registry",
        "devices",
        "metadata",
    }
    missing_top = sorted(required_top - set(payload.keys()))
    if missing_top:
        errors.append(f"{profile}: missing top-level keys: {missing_top}")
        return errors

    expected_signature = _build_expected_signature(
        secret_b64=_test_secret_b64(),
        challenge_id=str(payload["challenge_id"]),
        nonce="nonce-edge-001",
        company_id=101,
        branch_id=7,
        connector_id=str(payload["connector_id"]),
    )
    if str(payload["signature"]) != expected_signature:
        errors.append(f"{profile}: signature mismatch")

    capability_registry = payload["capability_registry"]
    devices = payload["devices"]
    if not isinstance(capability_registry, dict):
        errors.append(f"{profile}: capability_registry must be object")
    if not isinstance(devices, list) or not devices:
        errors.append(f"{profile}: devices must be non-empty list")
        return errors

    required_device_fields = {"device_key", "device_kind", "capability_level", "status", "metadata"}
    allowed_levels = {"supported", "experimental", "unsupported"}
    allowed_status = {"ONLINE", "DEGRADED", "OFFLINE"}

    seen_kinds: set[str] = set()
    for row in devices:
        if not isinstance(row, dict):
            errors.append(f"{profile}: each device must be object")
            continue
        missing_fields = sorted(required_device_fields - set(row.keys()))
        if missing_fields:
            errors.append(f"{profile}: device missing fields: {missing_fields}")
            continue
        level = str(row["capability_level"])
        status = str(row["status"])
        kind = str(row["device_kind"])
        if level not in allowed_levels:
            errors.append(f"{profile}: invalid capability_level for {kind}: {level}")
        if status not in allowed_status:
            errors.append(f"{profile}: invalid status for {kind}: {status}")
        if kind in seen_kinds:
            errors.append(f"{profile}: duplicate device_kind: {kind}")
        seen_kinds.add(kind)
        if capability_registry.get(kind) != level:
            errors.append(f"{profile}: capability_registry mismatch for {kind}")

    if profile == "minimal" and len(devices) != 2:
        errors.append("minimal: expected exactly 2 devices")
    if profile == "fuel" and len(devices) != 4:
        errors.append("fuel: expected exactly 4 devices")
    if str(payload.get("metadata", {}).get("profile")) != profile:
        errors.append(f"{profile}: metadata.profile mismatch")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida contrato del simulador Edge de Retail POS.")
    parser.add_argument("--root", default=".", help="Raiz del repo")
    parser.add_argument("--output", required=True, help="Ruta del artefacto JSON")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    checks: list[dict[str, Any]] = []
    all_errors: list[str] = []
    for profile in ("minimal", "fuel"):
        payload = _run_simulator(root=root, profile=profile)
        errors = _validate_payload(payload=payload, profile=profile)
        checks.append(
            {
                "profile": profile,
                "status": "passed" if not errors else "failed",
                "devices_count": len(payload.get("devices", [])),
                "errors": errors,
            }
        )
        all_errors.extend(errors)

    summary = {
        "status": "passed" if not all_errors else "failed",
        "checks": checks,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not all_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
