#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any


def _build_signature(*, secret_b64: str, challenge_id: str, nonce: str, company_id: int, branch_id: int, connector_id: str) -> str:
    secret = base64.b64decode(secret_b64.encode("utf-8"), validate=True)
    msg = f"{challenge_id}.{nonce}.{company_id}.{branch_id}.{connector_id}".encode("utf-8")
    digest = hmac.new(secret, msg, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _devices_for_profile(profile: str) -> list[dict[str, Any]]:
    if profile == "minimal":
        return [
            {
                "device_key": "printer-main",
                "device_kind": "THERMAL_PRINTER",
                "capability_level": "supported",
                "status": "ONLINE",
                "metadata": {"driver": "escpos"},
            },
            {
                "device_key": "scanner-main",
                "device_kind": "SCANNER",
                "capability_level": "experimental",
                "status": "ONLINE",
                "metadata": {"driver": "usb-hid"},
            },
        ]
    return [
        {
            "device_key": "printer-main",
            "device_kind": "THERMAL_PRINTER",
            "capability_level": "supported",
            "status": "ONLINE",
            "metadata": {"driver": "escpos"},
        },
        {
            "device_key": "scanner-main",
            "device_kind": "SCANNER",
            "capability_level": "supported",
            "status": "ONLINE",
            "metadata": {"driver": "usb-hid"},
        },
        {
            "device_key": "drawer-main",
            "device_kind": "DRAWER",
            "capability_level": "experimental",
            "status": "ONLINE",
            "metadata": {"driver": "escpos:pulse"},
        },
        {
            "device_key": "scale-main",
            "device_kind": "SCALE",
            "capability_level": "experimental",
            "status": "DEGRADED",
            "metadata": {"driver": "serial"},
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera payload determinista de handshake edge para QA local (no destructivo).",
    )
    parser.add_argument("--challenge-id", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--company-id", required=True, type=int)
    parser.add_argument("--branch-id", required=True, type=int)
    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--connector-version", default="0.2.0")
    parser.add_argument("--secret-b64", required=True, help="Secreto compartido en base64.")
    parser.add_argument(
        "--profile",
        choices=("minimal", "fuel"),
        default="fuel",
        help="Perfil de periféricos simulado.",
    )
    parser.add_argument("--output", default="", help="Ruta opcional para guardar JSON.")
    args = parser.parse_args()

    devices = _devices_for_profile(args.profile)
    capability_registry = {row["device_kind"]: row["capability_level"] for row in devices}
    signature = _build_signature(
        secret_b64=args.secret_b64,
        challenge_id=args.challenge_id,
        nonce=args.nonce,
        company_id=args.company_id,
        branch_id=args.branch_id,
        connector_id=args.connector_id,
    )
    payload = {
        "challenge_id": args.challenge_id,
        "connector_id": args.connector_id,
        "connector_version": args.connector_version,
        "signature": signature,
        "capability_registry": capability_registry,
        "devices": devices,
        "metadata": {"simulated_by": "qa/simulate_retail_pos_edge.py", "profile": args.profile},
    }

    output = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")
        print(str(path))
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

