#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canon_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _build_request_signing_message(*, ts: int, nonce: str, canonical_body_bytes: bytes) -> bytes:
    body_hash = hashlib.sha256(canonical_body_bytes).hexdigest()
    return f"{int(ts)}.{str(nonce)}.{body_hash}".encode("utf-8")


def _json_or_none(resp: requests.Response) -> dict[str, Any] | None:
    try:
        data = resp.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None


@dataclass
class CheckResult:
    name: str
    ok: bool
    http_status: int
    request_id: str
    reason: str
    trace: dict[str, Any] | None


def _request(
    *,
    session: requests.Session,
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 20,
) -> tuple[requests.Response, dict[str, Any] | None]:
    response = session.request(
        method=method,
        url=url,
        json=payload,
        headers=headers,
        timeout=timeout_seconds,
    )
    return response, _json_or_none(response)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe reproducible de enrolamiento/batch para sync_engine.")
    parser.add_argument("--base-url", default="http://localhost:8000/api", help="Base URL API sin slash final.")
    parser.add_argument("--username", required=True, help="Usuario con permiso sync.device.enroll (y revoke opcional).")
    parser.add_argument("--password", required=True, help="Password del usuario.")
    parser.add_argument("--company-id", required=True, type=int, help="Company scope efectivo para challenge.")
    parser.add_argument("--branch-id", required=True, type=int, help="Branch scope para challenge/enroll/batch.")
    parser.add_argument("--label", default="QA-Sync-Probe-Device", help="Label del dispositivo.")
    parser.add_argument("--expires-minutes", default=15, type=int, help="TTL del challenge.")
    parser.add_argument("--message", default="qa-sync-device-probe", help="Mensaje DEMO_PING.")
    parser.add_argument("--revoke", action="store_true", help="Ejecuta revoke al final del flujo.")
    parser.add_argument("--timeout-seconds", default=20, type=int, help="Timeout por request.")
    parser.add_argument("--output", default="", help="Ruta opcional para guardar evidencia JSON.")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    checks: list[CheckResult] = []
    evidence: dict[str, Any] = {}
    ids: dict[str, str] = {}
    session = requests.Session()

    def push_check(*, name: str, response: requests.Response, ok: bool, reason: str, data: dict[str, Any] | None) -> None:
        checks.append(
            CheckResult(
                name=name,
                ok=ok,
                http_status=int(response.status_code),
                request_id=str(response.headers.get("X-Request-Id", "")),
                reason=reason,
                trace=(data.get("trace") if isinstance(data, dict) and isinstance(data.get("trace"), dict) else None),
            )
        )

    # 1) Login
    login_resp, login_data = _request(
        session=session,
        method="POST",
        url=f"{base}/auth/login/",
        payload={"username": args.username, "password": args.password},
        headers={"X-Auth-Transport": "header"},
        timeout_seconds=args.timeout_seconds,
    )
    login_ok = login_resp.status_code == 200 and isinstance(login_data, dict) and isinstance(login_data.get("access"), str)
    login_reason = "" if login_ok else str((login_data or {}).get("error", {}).get("message") or "LOGIN_FAILED")
    push_check(name="login", response=login_resp, ok=login_ok, reason=login_reason, data=login_data)
    if not login_ok:
        report = {
            "timestamp": _now_iso(),
            "overall_status": "FAIL",
            "context": {"base_url": base, "company_id": args.company_id, "branch_id": args.branch_id},
            "ids": ids,
            "checks": [asdict(c) for c in checks],
            "evidence": evidence,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    access = str(login_data["access"])
    auth_headers = {
        "Authorization": f"Bearer {access}",
        "X-Auth-Transport": "header",
        "X-Company-Id": str(args.company_id),
    }

    # 2) Challenge
    challenge_resp, challenge_data = _request(
        session=session,
        method="POST",
        url=f"{base}/sync/enrollment/challenges/",
        payload={
            "company_id": args.company_id,
            "branch_id": args.branch_id,
            "label_hint": args.label,
            "expires_in_minutes": int(args.expires_minutes),
        },
        headers=auth_headers,
        timeout_seconds=args.timeout_seconds,
    )
    challenge_ok = challenge_resp.status_code == 201 and isinstance(challenge_data, dict) and isinstance(challenge_data.get("enrollment_code"), str)
    challenge_reason = "" if challenge_ok else str((challenge_data or {}).get("error", {}).get("message") or "CHALLENGE_FAILED")
    push_check(name="challenge", response=challenge_resp, ok=challenge_ok, reason=challenge_reason, data=challenge_data)
    if not challenge_ok:
        report = {
            "timestamp": _now_iso(),
            "overall_status": "FAIL",
            "context": {"base_url": base, "company_id": args.company_id, "branch_id": args.branch_id},
            "ids": ids,
            "checks": [asdict(c) for c in checks],
            "evidence": {"challenge": challenge_data},
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    enrollment_code = str(challenge_data["enrollment_code"])
    ids["challenge_id"] = str(challenge_data.get("challenge_id", ""))
    evidence["challenge"] = {
        "challenge_id": ids["challenge_id"],
        "expires_at": challenge_data.get("expires_at"),
        "trace": challenge_data.get("trace"),
    }

    # 3) Enroll
    private_key = Ed25519PrivateKey.generate()
    public_key_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key_b64 = base64.b64encode(public_key_raw).decode("utf-8")
    enroll_resp, enroll_data = _request(
        session=session,
        method="POST",
        url=f"{base}/sync/enroll/",
        payload={
            "enrollment_code": enrollment_code,
            "public_key_b64": public_key_b64,
            "label": args.label,
            "meta": {"probe": "sync_device_enroll_probe"},
        },
        headers={"X-Request-Id": f"sync-probe-{uuid.uuid4().hex[:20]}"},
        timeout_seconds=args.timeout_seconds,
    )
    enroll_ok = enroll_resp.status_code == 201 and isinstance(enroll_data, dict) and isinstance(enroll_data.get("device_id"), str)
    enroll_reason = "" if enroll_ok else str((enroll_data or {}).get("error", {}).get("message") or "ENROLL_FAILED")
    push_check(name="enroll", response=enroll_resp, ok=enroll_ok, reason=enroll_reason, data=enroll_data)
    if not enroll_ok:
        report = {
            "timestamp": _now_iso(),
            "overall_status": "FAIL",
            "context": {"base_url": base, "company_id": args.company_id, "branch_id": args.branch_id},
            "ids": ids,
            "checks": [asdict(c) for c in checks],
            "evidence": {"challenge": evidence.get("challenge"), "enroll": enroll_data},
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    ids["device_id"] = str(enroll_data["device_id"])
    evidence["enroll"] = {
        "device_id": ids["device_id"],
        "device_status": enroll_data.get("device_status"),
        "trace": enroll_data.get("trace"),
    }

    # 4) Batch signed DEMO_PING
    ts = int(time.time())
    nonce = f"sync-probe-{uuid.uuid4().hex[:20]}"
    batch_id = str(uuid.uuid4())
    command_id = str(uuid.uuid4())
    batch_payload: dict[str, Any] = {
        "protocol_version": "2",
        "device_id": ids["device_id"],
        "ts": ts,
        "nonce": nonce,
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": batch_id,
        "batch": [
            {
                "command_id": command_id,
                "type": "DEMO_PING",
                "scope": {"company_id": args.company_id, "branch_id": args.branch_id},
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {"msg": args.message},
            }
        ],
    }
    sign_payload = copy.deepcopy(batch_payload)
    sign_payload["auth"]["signature"] = ""
    canonical_body = _canon_json(sign_payload).encode("utf-8")
    signing_message = _build_request_signing_message(ts=ts, nonce=nonce, canonical_body_bytes=canonical_body)
    signature = base64.b64encode(private_key.sign(signing_message)).decode("utf-8")
    batch_payload["auth"]["signature"] = signature
    batch_resp, batch_data = _request(
        session=session,
        method="POST",
        url=f"{base}/sync/batch/",
        payload=batch_payload,
        headers={"X-Device-Id": ids["device_id"]},
        timeout_seconds=args.timeout_seconds,
    )
    batch_ok = batch_resp.status_code == 200 and isinstance(batch_data, dict)
    batch_reason = ""
    if batch_ok:
        first = ((batch_data.get("results") or [{}])[0] if isinstance(batch_data.get("results"), list) else {})
        batch_ok = isinstance(first, dict) and str(first.get("status")) in {"APPLIED", "DUPLICATE"}
        batch_reason = str(first.get("reason") or "")
    else:
        batch_reason = str((batch_data or {}).get("error", {}).get("message") or "BATCH_FAILED")
    push_check(name="batch_signed_demo_ping", response=batch_resp, ok=batch_ok, reason=batch_reason, data=batch_data)
    ids["batch_id"] = batch_id
    evidence["batch"] = {
        "batch_id": batch_id,
        "command_id": command_id,
        "trace": (batch_data or {}).get("trace") if isinstance(batch_data, dict) else None,
        "summary": (batch_data or {}).get("summary") if isinstance(batch_data, dict) else None,
    }

    # 5) Optional revoke
    if args.revoke and "device_id" in ids:
        revoke_resp, revoke_data = _request(
            session=session,
            method="POST",
            url=f"{base}/sync/devices/{ids['device_id']}/revoke/",
            payload={},
            headers=auth_headers,
            timeout_seconds=args.timeout_seconds,
        )
        revoke_ok = revoke_resp.status_code == 200 and isinstance(revoke_data, dict)
        revoke_reason = "" if revoke_ok else str((revoke_data or {}).get("error", {}).get("message") or "REVOKE_FAILED")
        push_check(name="revoke", response=revoke_resp, ok=revoke_ok, reason=revoke_reason, data=revoke_data)
        evidence["revoke"] = revoke_data

    overall_ok = all(check.ok for check in checks)
    report = {
        "timestamp": _now_iso(),
        "overall_status": "PASS" if overall_ok else "FAIL",
        "classification": {
            "canonical": "/api/sync/* -> sync_engine",
            "legacy_parallel": "/api/sync-hmac/* -> sync (wrapper opcional)",
        },
        "context": {
            "base_url": base,
            "company_id": args.company_id,
            "branch_id": args.branch_id,
        },
        "ids": ids,
        "checks": [asdict(c) for c in checks],
        "evidence": evidence,
    }

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
