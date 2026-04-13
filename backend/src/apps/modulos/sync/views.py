from __future__ import annotations

import logging
import uuid
import time

from django.conf import settings
from django.utils import timezone
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.sync_engine.models import Device as CoreSyncDevice
from apps.modulos.sync_engine.services import process_batch as process_core_batch

from config.error_envelope import build_error_envelope
from config.metrics import record_sync_batch
from .handlers import Command, CommandError, apply_command_idempotent
from .models import DeviceEnrollment, DeviceRequestNonce
from .serializers import SyncBatchSerializer
from .signing import canonical_string, verify_hmac_signature

MAX_SKEW_SECONDS = 300  # 5 minutos
trace_logger = logging.getLogger("apps.modulos.sync.trace")


def _sync_trace_payload(
    request,
    *,
    channel: str,
    legacy_wrapper: bool,
) -> dict[str, object]:
    return {
        "request_id": str(getattr(request, "request_id", "") or ""),
        "channel": channel,
        "legacy_wrapper": legacy_wrapper,
    }


def _sync_trace_log(
    *,
    level: int,
    message: str,
    request,
    reason: str,
    device_id: str | None = None,
    company_id: int | None = None,
    branch_id: int | None = None,
    legacy_wrapper: bool | None = None,
) -> None:
    extra: dict[str, object] = {
        "request_id": str(getattr(request, "request_id", "") or ""),
        "path": str(getattr(request, "path", "") or ""),
        "method": str(getattr(request, "method", "") or ""),
        "reason": reason,
        "channel": "sync_legacy",
        "view_name": "sync_hmac",
    }
    if device_id is not None:
        extra["device_id"] = device_id
    if company_id is not None:
        extra["company_id"] = company_id
    if branch_id is not None:
        extra["branch_id"] = branch_id
    if legacy_wrapper is not None:
        extra["legacy_wrapper"] = legacy_wrapper
    trace_logger.log(level, message, extra=extra)


class SyncBatchView(APIView):
    authentication_classes = []  # autenticación propia por firma
    permission_classes = []
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
    def _record_batch_metric(*, started_at: float, ok: bool, error_code: str = "") -> None:
        duration_ms = max(0, int((time.perf_counter() - started_at) * 1000))
        record_sync_batch(
            channel="sync_legacy",
            status="OK" if ok else "ERROR",
            duration_ms=duration_ms,
            error_code=error_code,
        )

    @staticmethod
    def _legacy_command_to_core_type(command_type: str) -> str:
        if command_type == "PING":
            return "DEMO_PING"
        return command_type

    @staticmethod
    def _apply_deprecation_headers(response: Response) -> None:
        response["Deprecation"] = "true"
        response["Sunset"] = str(getattr(settings, "SYNC_LEGACY_HMAC_SUNSET", "2026-03-31T00:00:00Z"))
        response["Link"] = "</docs/CONTRACT_PACK_v2.0.md>; rel=\"deprecation\""

    def _resolve_core_device(self, *, legacy_device: DeviceEnrollment) -> CoreSyncDevice | None:
        core_device = (
            CoreSyncDevice.objects.select_related("company", "branch")
            .filter(id=legacy_device.id, status=CoreSyncDevice.Status.ACTIVE)
            .first()
        )
        if core_device:
            return core_device
        return (
            CoreSyncDevice.objects.select_related("company", "branch")
            .filter(hmac_secret_b64=legacy_device.secret_b64, status=CoreSyncDevice.Status.ACTIVE)
            .order_by("-created_at")
            .first()
        )

    def _legacy_to_core_commands(self, *, core_device: CoreSyncDevice, commands: list[dict]) -> list[dict]:
        occurred_at = timezone.now()
        normalized: list[dict] = []
        for cmd in commands:
            payload = dict(cmd.get("payload") or {})
            normalized.append(
                {
                    "command_id": cmd["command_id"],
                    "command_type": self._legacy_command_to_core_type(str(cmd["type"])),
                    "company_id": int(core_device.company_id),
                    "branch_id": int(core_device.branch_id) if core_device.branch_id is not None else None,
                    "occurred_at": occurred_at,
                    "sequence": None,
                    "payload": payload,
                    "payload_hash": "",
                    "prev_hash": "",
                    "signature": "",
                }
            )
        return normalized

    @staticmethod
    def _core_to_legacy_response(*, legacy_device: DeviceEnrollment, core_out: dict) -> dict:
        mapped_results: list[dict] = []
        for row in core_out.get("results", []):
            command_id = str(row.get("command_id") or "")
            status_v2 = str(row.get("status") or "")
            if status_v2 in {"APPLIED", "DUPLICATE"}:
                data = dict(row.get("refs") or {})
                if status_v2 == "DUPLICATE":
                    data["duplicate"] = True
                mapped = {"status": "OK", "data": data}
            else:
                mapped = {"status": "ERROR", "error": str(row.get("reason") or "SYNC_REJECTED")}
            mapped_results.append({"command_id": command_id, "result": mapped})
        return {"device_id": str(legacy_device.id), "results": mapped_results}

    def post(self, request):
        started_at = time.perf_counter()
        # 1) Headers
        device_id = request.headers.get("X-Device-Id")
        ts_raw = request.headers.get("X-Device-Ts")
        nonce = request.headers.get("X-Device-Nonce")
        sig = request.headers.get("X-Device-Signature")

        if not (device_id and ts_raw and nonce and sig):
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_hmac_batch_auth_rejected",
                request=request,
                reason="MISSING_HEADERS",
            )
            self._record_batch_metric(started_at=started_at, ok=False, error_code="MISSING_HEADERS")
            return self._error_response(
                request,
                status_code=status.HTTP_400_BAD_REQUEST,
                reason="MISSING_HEADERS",
                details={
                    "required": [
                        "X-Device-Id",
                        "X-Device-Ts",
                        "X-Device-Nonce",
                        "X-Device-Signature",
                    ]
                },
            )

        try:
            ts = int(ts_raw)
        except ValueError:
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_hmac_batch_auth_rejected",
                request=request,
                reason="INVALID_TS",
                device_id=str(device_id or ""),
            )
            self._record_batch_metric(started_at=started_at, ok=False, error_code="INVALID_TS")
            return self._error_response(
                request,
                status_code=status.HTTP_400_BAD_REQUEST,
                reason="INVALID_TS",
            )

        now = int(timezone.now().timestamp())
        if abs(now - ts) > MAX_SKEW_SECONDS:
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_hmac_batch_auth_rejected",
                request=request,
                reason="TS_OUT_OF_WINDOW",
                device_id=str(device_id),
            )
            self._record_batch_metric(started_at=started_at, ok=False, error_code="TS_OUT_OF_WINDOW")
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="TS_OUT_OF_WINDOW",
            )

        # 2) Device
        device = DeviceEnrollment.objects.filter(id=device_id, is_active=True).first()
        if not device:
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_hmac_batch_auth_rejected",
                request=request,
                reason="UNKNOWN_OR_INACTIVE_DEVICE",
                device_id=str(device_id),
            )
            self._record_batch_metric(started_at=started_at, ok=False, error_code="UNKNOWN_OR_INACTIVE_DEVICE")
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="UNKNOWN_OR_INACTIVE_DEVICE",
            )

        # 3) Firma
        raw_body = request.body or b""
        canonical = canonical_string(ts=ts, nonce=nonce, raw_body=raw_body)
        if not verify_hmac_signature(device.secret_b64, canonical, sig):
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_hmac_batch_auth_rejected",
                request=request,
                reason="BAD_SIGNATURE",
                device_id=str(device.id),
            )
            self._record_batch_metric(started_at=started_at, ok=False, error_code="BAD_SIGNATURE")
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="BAD_SIGNATURE",
            )

        # 4) Anti-replay nonce
        try:
            # Usamos savepoint para que un nonce duplicado no rompa la transacción del request.
            with transaction.atomic():
                DeviceRequestNonce.objects.create(device=device, nonce=nonce, ts=ts)
        except IntegrityError:
            # unique constraint => replay
            _sync_trace_log(
                level=logging.WARNING,
                message="sync_hmac_batch_auth_rejected",
                request=request,
                reason="REPLAY_DETECTED",
                device_id=str(device.id),
            )
            self._record_batch_metric(started_at=started_at, ok=False, error_code="REPLAY_DETECTED")
            return self._error_response(
                request,
                status_code=status.HTTP_401_UNAUTHORIZED,
                reason="REPLAY_DETECTED",
            )

        # 5) Parse + apply
        serializer = SyncBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if bool(getattr(settings, "SYNC_HMAC_WRAPPER_ENABLED", False)):
            core_device = self._resolve_core_device(legacy_device=device)
            if not core_device:
                self._record_batch_metric(started_at=started_at, ok=False, error_code="UNKNOWN_OR_INACTIVE_DEVICE")
                return self._error_response(
                    request,
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    reason="UNKNOWN_OR_INACTIVE_DEVICE",
                )

            core_out = process_core_batch(
                request=request._request if hasattr(request, "_request") else request,
                actor_user=getattr(request, "user", None),
                device=core_device,
                batch_id=uuid.uuid4(),
                sent_at=timezone.now(),
                commands=self._legacy_to_core_commands(
                    core_device=core_device,
                    commands=serializer.validated_data["commands"],
                ),
                enforce_command_signature=False,
            )
            response = Response(
                self._core_to_legacy_response(legacy_device=device, core_out=core_out),
                status=status.HTTP_200_OK,
            )
            if isinstance(response.data, dict):
                response.data["trace"] = _sync_trace_payload(
                    request=request,
                    channel="sync_legacy",
                    legacy_wrapper=True,
                )
            self._apply_deprecation_headers(response)
            _sync_trace_log(
                level=logging.INFO,
                message="sync_hmac_batch_processed",
                request=request,
                reason="SYNC_OK",
                device_id=str(device.id),
                company_id=core_device.company_id,
                branch_id=core_device.branch_id,
                legacy_wrapper=True,
            )
            self._record_batch_metric(started_at=started_at, ok=True)
            return response

        results = []
        for c in serializer.validated_data["commands"]:
            cmd = Command(
                command_id=str(c["command_id"]),
                type=c["type"],
                payload=c.get("payload") or {},
            )
            try:
                r = apply_command_idempotent(device, cmd)
                results.append({"command_id": cmd.command_id, "result": r})
            except CommandError as e:
                results.append({"command_id": cmd.command_id, "result": {"status": "ERROR", "error": str(e)}})

        payload = {"device_id": str(device.id), "results": results}
        payload["trace"] = _sync_trace_payload(
            request=request,
            channel="sync_legacy",
            legacy_wrapper=False,
        )
        _sync_trace_log(
            level=logging.INFO,
            message="sync_hmac_batch_processed",
            request=request,
            reason="SYNC_OK",
            device_id=str(device.id),
            legacy_wrapper=False,
        )
        self._record_batch_metric(started_at=started_at, ok=True)
        return Response(payload, status=status.HTTP_200_OK)
