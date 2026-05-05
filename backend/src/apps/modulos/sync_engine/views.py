"""Vistas del motor de sync (precedente).

Precedente:
- Enrollment: requiere JWT + contexto (X-Company-Id) y deja trazas de auditoría.
- Batch: usa autenticación por dispositivo (X-Device-Id) + firma Ed25519 por comando.
"""

from __future__ import annotations

import copy
import logging
import time
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.db.models import Q
import uuid
from rest_framework import status
from rest_framework.exceptions import NotFound, ParseError, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.audit.writer import write_event
from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit
from config.metrics import record_sync_batch
from config.error_envelope import build_error_envelope

from .models import Device, DeviceEnrollmentChallenge, DeviceRequestNonce
from .serializers import EnrollmentChallengeCreateIn, DeviceEnrollIn, SyncBatchIn, SyncV2BatchIn
from .signing import (
    build_request_signing_message,
    canon_json,
    public_key_from_b64,
    verify_ed25519_signature,
    verify_hmac_signature_b64,
)
from .services import process_batch, resolve_device

trace_logger = logging.getLogger("apps.modulos.sync.trace")


def _write_sync_auth_rejected_event(
    *,
    request,
    reason_code: str,
    wire_reason: str,
    channel: str,
    failure_stage: str,
    device: Device | None = None,
    challenge: DeviceEnrollmentChallenge | None = None,
    presented_device_id: str = "",
    extra_metadata: dict[str, Any] | None = None,
):
    metadata: dict[str, Any] = {
        "channel": channel,
        "failure_stage": failure_stage,
        "wire_reason": wire_reason,
    }
    if device is not None:
        metadata["device_id"] = str(device.id)
        metadata["company_id"] = device.company_id
        metadata["branch_id"] = device.branch_id
        metadata["device_status"] = device.status
    elif presented_device_id:
        metadata["presented_device_id"] = str(presented_device_id)
    if challenge is not None:
        metadata["challenge_id"] = str(challenge.id)
        metadata["company_id"] = challenge.company_id
        metadata["branch_id"] = challenge.branch_id
    if extra_metadata:
        metadata.update(extra_metadata)

    subject_id = str(device.id) if device is not None else ""
    device_id = str(device.id) if device is not None else ""
    return write_event(
        request=request,
        event_type="SYNC_AUTH_REJECTED",
        reason_code=reason_code,
        actor_user=None,
        subject_type="DEVICE",
        subject_id=subject_id,
        device_id=device_id,
        offline_mode=True,
        metadata=metadata,
    )


def _sync_enrollment_links(code_plain: str) -> tuple[str, str]:
    code_param = quote(code_plain, safe="")
    deep_link = f"necktral-sync://enroll?code={code_param}"
    web_base = str(getattr(settings, "SYNC_ENROLL_WEB_BASE_URL", "") or "").strip().rstrip("/")
    if not web_base:
        return deep_link, deep_link
    web_link = f"{web_base}/#/device/enroll?code={code_param}"
    return web_link, deep_link


def _sync_trace_payload(
    request,
    *,
    channel: str | None = None,
    audit_event_id: str | None = None,
    legacy_wrapper: bool | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"request_id": str(getattr(request, "request_id", "") or "")}
    if channel is not None:
        payload["channel"] = channel
    if audit_event_id is not None:
        payload["audit_event_id"] = audit_event_id
    if legacy_wrapper is not None:
        payload["legacy_wrapper"] = legacy_wrapper
    return payload


def _sync_trace_log(
    *,
    level: int,
    message: str,
    request,
    reason: str,
    company_id: int | None = None,
    branch_id: int | None = None,
    device_id: str | None = None,
    challenge_id: str | None = None,
    channel: str | None = None,
    audit_event_id: str | None = None,
) -> None:
    extra: dict[str, object] = {
        "request_id": str(getattr(request, "request_id", "") or ""),
        "path": str(getattr(request, "path", "") or ""),
        "method": str(getattr(request, "method", "") or ""),
        "reason": reason,
        "view_name": "sync_engine",
    }
    if company_id is not None:
        extra["company_id"] = company_id
    if branch_id is not None:
        extra["branch_id"] = branch_id
    if device_id is not None:
        extra["device_id"] = device_id
    if challenge_id is not None:
        extra["challenge_id"] = challenge_id
    if channel is not None:
        extra["channel"] = channel
    if audit_event_id is not None:
        extra["audit_event_id"] = audit_event_id
    trace_logger.log(level, message, extra=extra)


class EnrollmentChallengeCreateView(APIView):
    """
    POST /api/sync/enrollment/challenges/
    Requiere JWT + contexto (X-Company-Id) porque usa rbac_permission.
    """

    permission_classes = [rbac_permission("sync.device.enroll")]
    throttle_scope = "admin_writes"

    def post(self, request):
        ser = EnrollmentChallengeCreateIn(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # Contexto activo (inyectado por tu JWTAuthWithOrgContext)
        company = getattr(request, "company", None)
        if company is None:
            raise ParseError("Falta contexto company (X-Company-Id).")

        company_id = int(data.get("company_id") or company.id)
        if company_id != company.id:
            raise ParseError("company_id debe coincidir con X-Company-Id en esta fase.")

        request_branch = getattr(request, "branch", None)
        branch_id = data.get("branch_id", None)
        branch = None
        if request_branch is not None:
            if branch_id is not None and int(branch_id) != int(request_branch.id):
                raise PermissionDenied("Sucursal fuera del alcance efectivo.")
            branch = request_branch
        elif branch_id is not None:
            branch = OrgUnit.objects.filter(
                id=int(branch_id),
                unit_type=OrgUnit.UnitType.BRANCH,
                parent=company,
                is_active=True,
            ).first()
            if not branch:
                raise NotFound("Sucursal no encontrada o inactiva.")

        expires_in = int(data.get("expires_in_minutes") or 15)
        expires_at = timezone.now() + timedelta(minutes=expires_in)

        code_plain = DeviceEnrollmentChallenge.generate_code()
        code_hash = DeviceEnrollmentChallenge.sha256_hex(code_plain)

        ch = DeviceEnrollmentChallenge.objects.create(
            company=company,
            branch=branch,
            enrollment_code_hash=code_hash,
            expires_at=expires_at,
            created_by_user=request.user,
            label_hint=str(data.get("label_hint") or ""),
        )

        audit_event = write_event(
            request=request,
            event_type="SYNC_ENROLL_CHALLENGE_CREATED",
            reason_code="SYNC_OK",
            actor_user=request.user,
            subject_type="DEVICE",
            subject_id="",
            device_id="",
            offline_mode=False,
            metadata={"challenge_id": str(ch.id), "company_id": company.id, "branch_id": getattr(branch, "id", None)},
        )
        _sync_trace_log(
            level=logging.INFO,
            message="sync_enroll_challenge_created",
            request=request,
            reason="SYNC_OK",
            company_id=company.id,
            branch_id=getattr(branch, "id", None),
            challenge_id=str(ch.id),
            audit_event_id=str(audit_event.event_id),
        )

        enrollment_uri, enrollment_deep_link = _sync_enrollment_links(code_plain)
        return Response(
            {
                "challenge_id": str(ch.id),
                "enrollment_code": code_plain,  # solo se entrega aquí
                "enrollment_uri": enrollment_uri,
                "enrollment_deep_link": enrollment_deep_link,
                "expires_at": ch.expires_at.isoformat(),
                "company_id": company.id,
                "branch_id": getattr(branch, "id", None),
                "trace": _sync_trace_payload(
                    request=request,
                    audit_event_id=str(audit_event.event_id),
                ),
            },
            status=201,
        )


class DeviceEnrollView(APIView):
    """
    POST /api/sync/enroll/
    No requiere JWT: el secreto es el enrollment_code (one-time).
    """

    permission_classes = [AllowAny]
    throttle_scope = "auth_sensitive"

    def post(self, request):
        ser = DeviceEnrollIn(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        code_plain = str(data["enrollment_code"])
        code_hash = DeviceEnrollmentChallenge.sha256_hex(code_plain)
        try:
            pk_raw = public_key_from_b64(data["public_key_b64"])
        except Exception as e:
            audit_event = _write_sync_auth_rejected_event(
                request=request,
                reason_code="SYNC_INVALID_PUBLIC_KEY",
                wire_reason="INVALID_PUBLIC_KEY",
                channel="sync_enrollment",
                failure_stage="enrollment",
            )
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_device_enroll_rejected",
                request=request,
                reason="SYNC_INVALID_PUBLIC_KEY",
                audit_event_id=str(audit_event.event_id),
            )
            raise ParseError(str(e))

        reject_reason = ""
        reject_message = ""
        reject_ch: DeviceEnrollmentChallenge | None = None
        device: Device | None = None
        ch: DeviceEnrollmentChallenge | None = None
        with transaction.atomic():
            # Lock row directly without outer-join on nullable relations (PostgreSQL restriction).
            ch = (
                DeviceEnrollmentChallenge.objects.select_for_update()
                .filter(enrollment_code_hash=code_hash)
                .first()
            )
            if not ch:
                reject_reason = "SYNC_ENROLL_INVALID_CODE"
                reject_message = "Código inválido."
            elif not ch.is_valid_now():
                reject_reason = "SYNC_ENROLL_USED_CODE" if ch.used_at is not None else "SYNC_ENROLL_EXPIRED_CODE"
                reject_message = "Código expirado o ya usado."
                reject_ch = ch
            else:
                label = str(data.get("label") or ch.label_hint or "")
                meta = data.get("meta") or {}

                device = Device.objects.create(
                    company_id=ch.company_id,
                    branch_id=ch.branch_id,
                    label=label,
                    status=Device.Status.ACTIVE,
                    public_key=bytes(pk_raw),
                    meta=meta,
                    enrolled_by_user_id=ch.created_by_user_id,
                )

                ch.used_at = timezone.now()
                ch.used_by_device = device
                ch.save(update_fields=["used_at", "used_by_device"])

        if reject_reason:
            audit_event = _write_sync_auth_rejected_event(
                request=request,
                reason_code=reject_reason,
                wire_reason=reject_reason,
                channel="sync_enrollment",
                failure_stage="enrollment",
                challenge=reject_ch,
            )
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_device_enroll_rejected",
                request=request,
                reason=reject_reason,
                company_id=getattr(reject_ch, "company_id", None),
                branch_id=getattr(reject_ch, "branch_id", None),
                challenge_id=str(reject_ch.id) if reject_ch is not None else None,
                audit_event_id=str(audit_event.event_id),
            )
            raise PermissionDenied(reject_message)
        if device is None or ch is None:
            raise PermissionDenied("Código inválido.")

        audit_event = write_event(
            request=request,
            event_type="SYNC_DEVICE_ENROLLED",
            reason_code="SYNC_OK",
            actor_user=None,
            subject_type="DEVICE",
            subject_id=str(device.id),
            device_id=str(device.id),
            offline_mode=True,
            metadata={
                "company_id": device.company_id,
                "branch_id": device.branch_id,
                "label": device.label,
            },
        )
        _sync_trace_log(
            level=logging.INFO,
            message="sync_device_enrolled",
            request=request,
            reason="SYNC_OK",
            company_id=device.company_id,
            branch_id=device.branch_id,
            device_id=str(device.id),
            challenge_id=str(ch.id),
            audit_event_id=str(audit_event.event_id),
        )

        from apps.modulos.sync_engine.services import get_policy

        policy = get_policy()
        return Response(
            {
                "device_id": str(device.id),
                "device_status": device.status,
                "company_id": device.company_id,
                "branch_id": device.branch_id,
                "server_time": timezone.now().isoformat(),
                "policy": {
                    "max_commands_per_batch": policy.max_commands_per_batch,
                    "max_payload_bytes": policy.max_payload_bytes,
                    "max_device_clock_skew_seconds": policy.max_device_clock_skew_seconds,
                    "seq_tolerant": policy.seq_tolerant,
                },
                "trace": _sync_trace_payload(
                    request=request,
                    audit_event_id=str(audit_event.event_id),
                ),
            },
            status=201,
        )


class DeviceRevokeView(APIView):
    """
    POST /api/sync/devices/<device_id>/revoke/
    Requiere JWT + permiso.
    """

    permission_classes = [rbac_permission("sync.device.revoke")]
    throttle_scope = "admin_writes"

    def post(self, request, device_id: str):
        company = getattr(request, "company", None)
        if company is None:
            raise ParseError("Falta contexto company (X-Company-Id).")

        qs = Device.objects.filter(id=device_id, company=company)
        request_branch = getattr(request, "branch", None)
        if request_branch is not None:
            qs = qs.filter(branch=request_branch)
        device = qs.first()
        if not device:
            raise NotFound("Device no encontrado en esta company.")

        device.revoke()

        write_event(
            request=request,
            event_type="SYNC_DEVICE_REVOKED",
            reason_code="SYNC_OK",
            actor_user=request.user,
            subject_type="DEVICE",
            subject_id=str(device.id),
            device_id=str(device.id),
            offline_mode=False,
            metadata={"company_id": device.company_id, "branch_id": device.branch_id},
        )

        return Response({"device_id": str(device.id), "status": device.status}, status=200)


class DeviceListView(APIView):
    """
    GET /api/sync/devices/
    Requiere JWT + permiso.
    Política: quien puede revocar, puede listar.
    """

    permission_classes = [rbac_permission("sync.device.revoke")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        company = getattr(request, "company", None)
        if company is None:
            raise ParseError("Falta contexto company (X-Company-Id).")

        qs = Device.objects.filter(company=company)
        request_branch = getattr(request, "branch", None)
        if request_branch is not None:
            qs = qs.filter(branch=request_branch)
        qs = qs.order_by("-created_at")

        status_param = (request.query_params.get("status") or "").strip()
        if status_param:
            qs = qs.filter(status=status_param)

        q = (request.query_params.get("q") or "").strip()
        if q:
            filt = Q(label__icontains=q)
            try:
                filt |= Q(id=uuid.UUID(q))
            except Exception:
                pass
            qs = qs.filter(filt)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        results = [
            {
                "id": str(d.id),
                "label": d.label,
                "status": d.status,
                "company_id": d.company_id,
                "branch_id": d.branch_id,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "revoked_at": d.revoked_at.isoformat() if d.revoked_at else None,
                "last_seen_at": d.last_seen_at.isoformat() if getattr(d, "last_seen_at", None) else None,
                "last_accepted_sequence": getattr(d, "last_accepted_sequence", None),
            }
            for d in rows
        ]

        return Response({"count": total, "limit": limit, "offset": offset, "results": results}, status=200)


class SyncBatchView(APIView):
    """
    POST /api/sync/batch/
    Device-auth (X-Device-Id) + firma por comando.
    """

    permission_classes = [AllowAny]
    throttle_scope = "sync_batch"

    def _error_response(self, request, *, status_code: int, reason: str, details: dict | None = None) -> Response:
        payload = build_error_envelope(
            request=request,
            status_code=status_code,
            exc=None,
            details={"detail": reason, **(details or {})},
        )
        return Response(payload, status=status_code)

    @staticmethod
    def _record_batch_metric(*, channel: str, started_at: float, ok: bool, error_code: str = "") -> None:
        duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
        record_sync_batch(
            channel=channel,
            status="OK" if ok else "ERROR",
            duration_ms=duration_ms,
            error_code=error_code,
        )

    def _normalize_v2_commands(self, data: dict) -> list[dict]:
        commands: list[dict] = []
        for row in data.get("batch", []):
            scope = row["scope"]
            commands.append(
                {
                    "command_id": row["command_id"],
                    "command_type": row["type"],
                    "company_id": scope["company_id"],
                    "branch_id": scope.get("branch_id"),
                    "occurred_at": row["occurred_at"],
                    "sequence": row.get("sequence"),
                    "payload": row.get("payload") or {},
                    "payload_hash": row.get("payload_hash") or "",
                    "prev_hash": row.get("prev_hash") or "",
                    "signature": row.get("command_sig") or "",
                }
            )
        return commands

    def _request_signing_body(self, payload: dict) -> bytes:
        canonical_payload = copy.deepcopy(payload)
        auth = canonical_payload.get("auth")
        if isinstance(auth, dict):
            auth["signature"] = ""
            canonical_payload["auth"] = auth
        return canon_json(canonical_payload).encode("utf-8")

    def _validate_v2_request_auth(self, *, request, device: Device, payload_raw: dict, payload_v2: dict) -> Response | None:
        max_skew_seconds = int(getattr(settings, "SYNC_V2_MAX_SKEW_SECONDS", 300))
        ts = int(payload_v2["ts"])
        now = int(timezone.now().timestamp())
        ts_delta_seconds = abs(now - ts)
        if ts_delta_seconds > max_skew_seconds:
            audit_event = _write_sync_auth_rejected_event(
                request=request,
                reason_code="SYNC_TS_OUT_OF_WINDOW",
                wire_reason="TS_OUT_OF_WINDOW",
                channel="sync_v2",
                failure_stage="request_auth",
                device=device,
                extra_metadata={
                    "ts_delta_seconds": ts_delta_seconds,
                    "max_skew_seconds": max_skew_seconds,
                },
            )
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_batch_auth_rejected",
                request=request,
                reason="TS_OUT_OF_WINDOW",
                company_id=device.company_id,
                branch_id=device.branch_id,
                device_id=str(device.id),
                channel="sync_v2",
                audit_event_id=str(audit_event.event_id),
            )
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="TS_OUT_OF_WINDOW",
            )

        auth = payload_v2["auth"]
        signing_body = self._request_signing_body(payload_raw)
        msg = build_request_signing_message(
            ts=ts,
            nonce=str(payload_v2["nonce"]),
            canonical_body_bytes=signing_body,
        )
        scheme = str(auth["scheme"]).strip().lower()
        signature = str(auth["signature"]).strip()

        if scheme == "hmac":
            secret = str(getattr(device, "hmac_secret_b64", "") or "").strip()
            if not secret:
                audit_event = _write_sync_auth_rejected_event(
                    request=request,
                    reason_code="SYNC_DEVICE_NO_HMAC_SECRET",
                    wire_reason="SYNC_DEVICE_NO_HMAC_SECRET",
                    channel="sync_v2",
                    failure_stage="request_auth",
                    device=device,
                    extra_metadata={"scheme": scheme},
                )
                _sync_trace_log(
                    level=logging.WARNING,
                    message="sync_batch_auth_rejected",
                    request=request,
                    reason="SYNC_DEVICE_NO_HMAC_SECRET",
                    company_id=device.company_id,
                    branch_id=device.branch_id,
                    device_id=str(device.id),
                    channel="sync_v2",
                    audit_event_id=str(audit_event.event_id),
                )
                return self._error_response(
                    request,
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    reason="SYNC_DEVICE_NO_HMAC_SECRET",
                )
            ok = verify_hmac_signature_b64(
                secret_b64=secret,
                message=msg,
                signature_b64=signature,
            )
        else:
            pk_raw = bytes(device.public_key or b"")
            if not pk_raw:
                audit_event = _write_sync_auth_rejected_event(
                    request=request,
                    reason_code="SYNC_DEVICE_NO_PUBLIC_KEY",
                    wire_reason="SYNC_DEVICE_NO_PUBLIC_KEY",
                    channel="sync_v2",
                    failure_stage="request_auth",
                    device=device,
                    extra_metadata={"scheme": scheme},
                )
                _sync_trace_log(
                    level=logging.WARNING,
                    message="sync_batch_auth_rejected",
                    request=request,
                    reason="SYNC_DEVICE_NO_PUBLIC_KEY",
                    company_id=device.company_id,
                    branch_id=device.branch_id,
                    device_id=str(device.id),
                    channel="sync_v2",
                    audit_event_id=str(audit_event.event_id),
                )
                return self._error_response(
                    request,
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    reason="SYNC_DEVICE_NO_PUBLIC_KEY",
                )
            ok = verify_ed25519_signature(
                public_key_raw=pk_raw,
                signature_b64=signature,
                message=msg,
            )

        if not ok:
            audit_event = _write_sync_auth_rejected_event(
                request=request,
                reason_code="SYNC_BAD_SIGNATURE",
                wire_reason="BAD_SIGNATURE",
                channel="sync_v2",
                failure_stage="request_auth",
                device=device,
                extra_metadata={"scheme": scheme},
            )
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_batch_auth_rejected",
                request=request,
                reason="BAD_SIGNATURE",
                company_id=device.company_id,
                branch_id=device.branch_id,
                device_id=str(device.id),
                channel="sync_v2",
                audit_event_id=str(audit_event.event_id),
            )
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="BAD_SIGNATURE",
            )

        try:
            with transaction.atomic():
                DeviceRequestNonce.objects.create(
                    device=device,
                    nonce=str(payload_v2["nonce"]),
                    ts=ts,
                )
        except IntegrityError:
            audit_event = _write_sync_auth_rejected_event(
                request=request,
                reason_code="SYNC_REPLAY_DETECTED",
                wire_reason="REPLAY_DETECTED",
                channel="sync_v2",
                failure_stage="request_auth",
                device=device,
                extra_metadata={"scheme": scheme},
            )
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_batch_auth_rejected",
                request=request,
                reason="REPLAY_DETECTED",
                company_id=device.company_id,
                branch_id=device.branch_id,
                device_id=str(device.id),
                channel="sync_v2",
                audit_event_id=str(audit_event.event_id),
            )
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="REPLAY_DETECTED",
            )
        return None

    def post(self, request):
        started_at = time.perf_counter()
        channel = "sync_legacy"
        raw_data = request.data if isinstance(request.data, dict) else {}
        protocol_version = str(raw_data.get("protocol_version") or "").strip()
        v2_accept_enabled = bool(getattr(settings, "SYNC_V2_ACCEPT_ENABLED", True))
        v2_request_auth_enforced = bool(getattr(settings, "SYNC_V2_REQUEST_AUTH_ENFORCED", True))

        if protocol_version == "2":
            channel = "sync_v2"
            if not v2_accept_enabled:
                self._record_batch_metric(channel=channel, started_at=started_at, ok=False, error_code="SYNC_V2_DISABLED")
                return self._error_response(
                    request,
                    status_code=status.HTTP_400_BAD_REQUEST,
                    reason="SYNC_V2_DISABLED",
                )

            ser_v2 = SyncV2BatchIn(data=request.data)
            ser_v2.is_valid(raise_exception=True)
            data_v2 = ser_v2.validated_data

            hdr_device_id = (request.headers.get("X-Device-Id") or "").strip()
            body_device_id = str(data_v2["device_id"])
            if hdr_device_id and hdr_device_id != body_device_id:
                audit_event = _write_sync_auth_rejected_event(
                    request=request,
                    reason_code="SYNC_DEVICE_ID_MISMATCH",
                    wire_reason="DEVICE_ID_MISMATCH",
                    channel=channel,
                    failure_stage="request_auth",
                    presented_device_id=hdr_device_id,
                    extra_metadata={
                        "header_device_id": hdr_device_id,
                        "body_device_id": body_device_id,
                    },
                )
                _sync_trace_log(
                    level=logging.WARNING,
                    message="sync_batch_auth_rejected",
                    request=request,
                    reason="DEVICE_ID_MISMATCH",
                    device_id=hdr_device_id,
                    channel=channel,
                    audit_event_id=str(audit_event.event_id),
                )
                self._record_batch_metric(channel=channel, started_at=started_at, ok=False, error_code="DEVICE_ID_MISMATCH")
                return self._error_response(
                    request,
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    reason="DEVICE_ID_MISMATCH",
                )
            device_id = hdr_device_id or body_device_id
            try:
                device = resolve_device(device_id=device_id)
            except PermissionDenied:
                audit_event = _write_sync_auth_rejected_event(
                    request=request,
                    reason_code="SYNC_UNKNOWN_DEVICE",
                    wire_reason="SYNC_UNKNOWN_DEVICE",
                    channel=channel,
                    failure_stage="device_lookup",
                    presented_device_id=device_id,
                )
                _sync_trace_log(
                    level=logging.WARNING,
                    message="sync_batch_auth_rejected",
                    request=request,
                    reason="SYNC_UNKNOWN_DEVICE",
                    device_id=device_id,
                    channel=channel,
                    audit_event_id=str(audit_event.event_id),
                )
                self._record_batch_metric(channel=channel, started_at=started_at, ok=False, error_code="SYNC_UNKNOWN_DEVICE")
                raise

            if v2_request_auth_enforced:
                auth_error = self._validate_v2_request_auth(
                    request=request,
                    device=device,
                    payload_raw=raw_data,
                    payload_v2=data_v2,
                )
                if auth_error is not None:
                    err_payload = getattr(auth_error, "data", {}) or {}
                    err_code = str((err_payload.get("error") or {}).get("message") or "AUTH_ERROR")
                    self._record_batch_metric(channel=channel, started_at=started_at, ok=False, error_code=err_code)
                    return auth_error

            out = process_batch(
                request=request._request if hasattr(request, "_request") else request,
                actor_user=getattr(request, "user", None),
                device=device,
                batch_id=data_v2["batch_id"],
                sent_at=None,
                commands=self._normalize_v2_commands(data_v2),
                enforce_command_signature=not v2_request_auth_enforced,
            )
            out["trace"] = _sync_trace_payload(request=request, channel=channel)
            self._record_batch_metric(channel=channel, started_at=started_at, ok=True)
            return Response(out, status=200)

        ser = SyncBatchIn(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        hdr_device_id = request.headers.get("X-Device-Id")
        body_device_id = data.get("device_id")
        if hdr_device_id:
            device_id = hdr_device_id.strip()
        elif body_device_id:
            device_id = str(body_device_id)
        else:
            raise PermissionDenied("X-Device-Id requerido.")

        try:
            device = resolve_device(device_id=device_id)
        except PermissionDenied:
            audit_event = _write_sync_auth_rejected_event(
                request=request,
                reason_code="SYNC_UNKNOWN_DEVICE",
                wire_reason="SYNC_UNKNOWN_DEVICE",
                channel=channel,
                failure_stage="device_lookup",
                presented_device_id=device_id,
            )
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_batch_auth_rejected",
                request=request,
                reason="SYNC_UNKNOWN_DEVICE",
                device_id=device_id,
                channel=channel,
                audit_event_id=str(audit_event.event_id),
            )
            self._record_batch_metric(channel=channel, started_at=started_at, ok=False, error_code="SYNC_UNKNOWN_DEVICE")
            raise
        out = process_batch(
            request=request._request if hasattr(request, "_request") else request,
            actor_user=getattr(request, "user", None),
            device=device,
            batch_id=data["batch_id"],
            sent_at=data.get("sent_at"),
            commands=data["commands"],
            enforce_command_signature=True,
        )
        out["trace"] = _sync_trace_payload(request=request, channel=channel)
        self._record_batch_metric(channel=channel, started_at=started_at, ok=True)
        return Response(out, status=200)
