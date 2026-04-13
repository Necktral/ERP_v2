#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest


VOL_Q = Decimal("0.0001")


class StepFailure(RuntimeError):
    """Error de validación de un paso de simulación."""


@dataclass
class StepRecord:
    module: str
    key: str
    action: str
    expected: str
    actual: str
    passed: bool
    http_status: int | None = None
    detail: str = ""


class ProductLifecycleSimulation:
    def __init__(
        self,
        *,
        base_url: str,
        out_dir: Path,
        seed: int,
        admin_username: str,
        admin_password: str,
        contract_path: Path,
        timezone_name: str,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.out_dir = out_dir
        self.seed = int(seed)
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.contract = self._load_json(contract_path)
        self.timezone_name = timezone_name

        self.random = random.Random(self.seed)
        self.started_at = datetime.now(timezone.utc)

        self.access_token = ""
        self.refresh_token = ""

        self.company_a_id: int | None = None
        self.company_b_id: int | None = None
        self.branch_a1_id: int | None = None
        self.branch_a2_id: int | None = None
        self.branch_b1_id: int | None = None
        self.admin_user_id: int | None = None

        self.steps: list[StepRecord] = []
        self.global_error = ""
        self.intercompany_consistency: dict[str, Any] = {}
        self.orphan_checks: dict[str, Any] = {}
        self.warnings: list[str] = []

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Contrato inválido (no objeto JSON): {path}")
        return payload

    def _allowed_statuses(self, key: str, fallback: list[int] | None = None) -> list[int]:
        overrides = self.contract.get("status_overrides") or {}
        if key in overrides:
            raw = overrides[key]
            return [int(x) for x in raw]
        if fallback is not None:
            return [int(x) for x in fallback]
        return [int(x) for x in (self.contract.get("default_allowed_statuses") or [200, 201])]

    def _record_http_step(
        self,
        *,
        module: str,
        key: str,
        action: str,
        expected: str,
        status_code: int,
        body: Any,
        allowed_statuses: list[int] | None = None,
    ) -> Any:
        allowed = self._allowed_statuses(key, fallback=allowed_statuses)
        passed = int(status_code) in allowed
        actual = f"HTTP {status_code}"
        detail = ""
        if isinstance(body, dict) and body:
            if "detail" in body and isinstance(body.get("detail"), str):
                detail = str(body["detail"])
            elif "error_code" in body and isinstance(body.get("error_code"), str):
                detail = str(body["error_code"])
        self.steps.append(
            StepRecord(
                module=module,
                key=key,
                action=action,
                expected=f"{expected} [{allowed}]",
                actual=actual,
                passed=bool(passed),
                http_status=int(status_code),
                detail=detail,
            )
        )
        if not passed:
            raise StepFailure(f"Paso HTTP falló: {module}/{key} status={status_code} allowed={allowed} detail={detail}")
        return body

    def _record_check_step(
        self,
        *,
        module: str,
        key: str,
        action: str,
        expected: str,
        passed: bool,
        actual: str,
        detail: str = "",
    ) -> None:
        self.steps.append(
            StepRecord(
                module=module,
                key=key,
                action=action,
                expected=expected,
                actual=actual,
                passed=bool(passed),
                http_status=None,
                detail=detail,
            )
        )
        if not passed:
            raise StepFailure(f"Paso de validación falló: {module}/{key} actual={actual} detail={detail}")

    def _api_json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        token: str | None = None,
        company_id: int | None = None,
        branch_id: int | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout_sec: int = 40,
        retry_attempts: int = 8,
        retry_delay_sec: float = 1.0,
    ) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if company_id is not None:
            headers["X-Company-Id"] = str(company_id)
        if branch_id is not None:
            headers["X-Branch-Id"] = str(branch_id)
        if extra_headers:
            headers.update(extra_headers)

        raw_payload = None
        if payload is not None:
            raw_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urlrequest.Request(url=url, data=raw_payload, headers=headers, method=method.upper())
        status_code = 0
        body_raw = ""
        last_exc: Exception | None = None
        for attempt in range(1, max(1, int(retry_attempts)) + 1):
            try:
                with urlrequest.urlopen(req, timeout=timeout_sec) as resp:
                    status_code = int(resp.getcode())
                    body_raw = resp.read().decode("utf-8", errors="replace")
                last_exc = None
                break
            except urlerror.HTTPError as exc:
                status_code = int(exc.code)
                body_raw = exc.read().decode("utf-8", errors="replace")
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= int(retry_attempts):
                    break
                time.sleep(float(retry_delay_sec))
                continue

        if last_exc is not None:
            raise StepFailure(f"HTTP request error {method} {path}: {last_exc}") from last_exc

        body = {}
        if body_raw.strip():
            try:
                body = json.loads(body_raw)
            except Exception:
                body = {"raw": body_raw[:2000]}
        return status_code, body

    @staticmethod
    def _totp_code(secret_b32: str, *, for_epoch: int | None = None, digits: int = 6, interval: int = 30) -> str:
        epoch = int(time.time()) if for_epoch is None else int(for_epoch)
        key = base64.b32decode(str(secret_b32).strip().upper(), casefold=True)
        counter = int(epoch // interval)
        msg = counter.to_bytes(8, byteorder="big", signed=False)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        dbc = (
            ((digest[offset] & 0x7F) << 24)
            | ((digest[offset + 1] & 0xFF) << 16)
            | ((digest[offset + 2] & 0xFF) << 8)
            | (digest[offset + 3] & 0xFF)
        )
        code = dbc % (10**digits)
        return f"{code:0{digits}d}"

    def _totp_candidates(self, secret_b32: str) -> list[str]:
        now = int(time.time())
        return [
            self._totp_code(secret_b32, for_epoch=now - 30),
            self._totp_code(secret_b32, for_epoch=now),
            self._totp_code(secret_b32, for_epoch=now + 30),
        ]

    def _resolve_edge_secret_b64(self) -> str:
        env_val = str(os.getenv("POS_EDGE_CONNECTOR_SHARED_SECRET", "")).strip()
        if env_val:
            return env_val

        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("POS_EDGE_CONNECTOR_SHARED_SECRET="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value

        return "ZWRnZS1zZWNyZXQ="

    @staticmethod
    def _run_cmd(cmd: list[str], *, timeout_sec: int = 600) -> tuple[int, str, str]:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        return int(proc.returncode), proc.stdout, proc.stderr

    def _run_backend_manage_shell_json(self, code: str, *, label: str) -> dict[str, Any]:
        cmd = [
            "docker",
            "compose",
            "exec",
            "-T",
            "backend",
            "bash",
            "-lc",
            "cd /app/backend && python manage.py shell",
        ]
        proc = subprocess.run(
            cmd,
            input=code,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0:
            raise StepFailure(f"manage shell failed [{label}] rc={proc.returncode}: {stderr or stdout}")

        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        for line in reversed(lines):
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                return obj
        raise StepFailure(f"No JSON de salida en manage shell [{label}]. stdout={stdout[:2000]}")

    def _auth_context(self) -> tuple[int, int]:
        if self.company_a_id is None or self.branch_a1_id is None:
            raise StepFailure("Contexto company_a/branch_a1 no inicializado")
        return int(self.company_a_id), int(self.branch_a1_id)

    def _run_iam(self) -> None:
        module = "iam"

        status_code, body = self._api_json("GET", "/auth/bootstrap/status/")
        body = self._record_http_step(
            module=module,
            key="iam.bootstrap_status",
            action="Bootstrap status",
            expected="sistema fresh=true",
            status_code=status_code,
            body=body,
        )
        is_fresh = bool(body.get("is_fresh")) if isinstance(body, dict) else False
        self._record_check_step(
            module=module,
            key="iam.bootstrap_fresh_assert",
            action="Validar estado fresh",
            expected="is_fresh=true",
            passed=is_fresh,
            actual=f"is_fresh={is_fresh}",
        )

        init_payload = {
            "username": self.admin_username,
            "email": f"{self.admin_username}@local.test",
            "password": self.admin_password,
            "first_name": "Lifecycle",
            "last_name": "Admin",
        }
        status_code, body = self._api_json("POST", "/auth/bootstrap/init/", payload=init_payload)
        body = self._record_http_step(
            module=module,
            key="iam.bootstrap_init",
            action="Bootstrap init admin",
            expected="admin creado",
            status_code=status_code,
            body=body,
        )
        self.admin_user_id = int(body.get("id")) if isinstance(body, dict) and body.get("id") else None

        status_code, body = self._api_json(
            "POST",
            "/auth/login/",
            payload={"username": self.admin_username, "password": self.admin_password},
            extra_headers={"X-Auth-Transport": "header"},
        )
        body = self._record_http_step(
            module=module,
            key="iam.login_plain",
            action="Login inicial",
            expected="token header emitido",
            status_code=status_code,
            body=body,
        )
        self.access_token = str(body.get("access") or "")
        self.refresh_token = str(body.get("refresh") or "")
        if not self.access_token or not self.refresh_token:
            raise StepFailure("Login inicial sin access/refresh")

        org_payload = {
            "holding_name": "NECKTRAL HOLDING",
            "company_name": "NECKTRAL MAIN",
            "company_tax_id": "J-030123-001",
            "branch_name": "MAIN-01",
            "branch_address": "Managua",
        }
        status_code, body = self._api_json(
            "POST",
            "/auth/bootstrap/org/",
            payload=org_payload,
            token=self.access_token,
        )
        body = self._record_http_step(
            module=module,
            key="iam.bootstrap_org",
            action="Bootstrap organización base",
            expected="holding/company/branch creados",
            status_code=status_code,
            body=body,
        )
        self.company_a_id = int(body.get("company_id"))
        self.branch_a1_id = int(body.get("branch_id"))

        company_a, branch_a1 = self._auth_context()

        status_code, body = self._api_json(
            "POST",
            "/auth/2fa/enable/",
            payload={},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="iam.2fa_enable",
            action="Habilitar setup 2FA",
            expected="secret TOTP emitido",
            status_code=status_code,
            body=body,
        )
        secret = str(body.get("secret") or "")
        if not secret:
            raise StepFailure("2FA enable sin secret")

        confirmed = False
        for candidate in self._totp_candidates(secret):
            c_status, c_body = self._api_json(
                "POST",
                "/auth/2fa/confirm/",
                payload={"code": candidate},
                token=self.access_token,
                company_id=company_a,
                branch_id=branch_a1,
            )
            if c_status == 200:
                self._record_http_step(
                    module=module,
                    key="iam.2fa_confirm",
                    action="Confirmar 2FA",
                    expected="2FA activo",
                    status_code=c_status,
                    body=c_body,
                )
                confirmed = True
                break
        if not confirmed:
            raise StepFailure("No fue posible confirmar 2FA con códigos TOTP válidos")

        status_code, body = self._api_json(
            "POST",
            "/auth/login/",
            payload={"username": self.admin_username, "password": self.admin_password},
            extra_headers={"X-Auth-Transport": "header"},
        )
        body = self._record_http_step(
            module=module,
            key="iam.login_2fa_challenge",
            action="Login con challenge 2FA",
            expected="challenge one-time",
            status_code=status_code,
            body=body,
        )
        challenge = str(body.get("challenge") or "")
        if not challenge:
            raise StepFailure("Login 2FA sin challenge")

        status_code, body = self._api_json(
            "POST",
            "/auth/2fa/verify/",
            payload={"challenge": challenge, "code": "000000"},
            extra_headers={"X-Auth-Transport": "header"},
        )
        self._record_http_step(
            module=module,
            key="iam.2fa_verify_denied",
            action="Verificar denegación sin segundo factor válido",
            expected="acceso denegado",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            "/auth/login/",
            payload={"username": self.admin_username, "password": self.admin_password},
            extra_headers={"X-Auth-Transport": "header"},
        )
        body = self._record_http_step(
            module=module,
            key="iam.login_2fa_challenge_retry",
            action="Login 2FA (retry tras denegación)",
            expected="challenge one-time",
            status_code=status_code,
            body=body,
        )
        challenge = str(body.get("challenge") or "")
        if not challenge:
            raise StepFailure("Login 2FA retry sin challenge")

        verified = False
        for candidate in self._totp_candidates(secret):
            v_status, v_body = self._api_json(
                "POST",
                "/auth/2fa/verify/",
                payload={"challenge": challenge, "code": candidate},
                extra_headers={"X-Auth-Transport": "header"},
            )
            if v_status == 200:
                v_body = self._record_http_step(
                    module=module,
                    key="iam.2fa_verify",
                    action="Verificar challenge 2FA",
                    expected="tokens emitidos",
                    status_code=v_status,
                    body=v_body,
                )
                self.access_token = str(v_body.get("access") or "")
                self.refresh_token = str(v_body.get("refresh") or "")
                verified = True
                break
        if not verified:
            raise StepFailure("No fue posible completar verify 2FA")

        status_code, body = self._api_json(
            "POST",
            "/auth/refresh/",
            payload={"refresh": self.refresh_token},
            token=None,
            company_id=None,
            branch_id=None,
            extra_headers={"X-Auth-Transport": "header"},
        )
        body = self._record_http_step(
            module=module,
            key="iam.refresh",
            action="Refresh token",
            expected="rotación de tokens",
            status_code=status_code,
            body=body,
        )
        self.access_token = str(body.get("access") or self.access_token)
        self.refresh_token = str(body.get("refresh") or self.refresh_token)

        status_code, body = self._api_json(
            "POST",
            "/auth/logout/",
            payload={"refresh": self.refresh_token},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
            extra_headers={"X-Auth-Transport": "header"},
        )
        self._record_http_step(
            module=module,
            key="iam.logout",
            action="Logout",
            expected="sesión invalidada",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            "/auth/login/",
            payload={"username": self.admin_username, "password": self.admin_password},
            extra_headers={"X-Auth-Transport": "header"},
        )
        body = self._record_http_step(
            module=module,
            key="iam.login_2fa_challenge",
            action="Re-login operativo",
            expected="challenge 2FA",
            status_code=status_code,
            body=body,
        )
        challenge = str(body.get("challenge") or "")
        if not challenge:
            raise StepFailure("Re-login sin challenge")

        relogin_ok = False
        for candidate in self._totp_candidates(secret):
            s_code, s_body = self._api_json(
                "POST",
                "/auth/2fa/verify/",
                payload={"challenge": challenge, "code": candidate},
                extra_headers={"X-Auth-Transport": "header"},
            )
            if s_code == 200:
                s_body = self._record_http_step(
                    module=module,
                    key="iam.2fa_verify",
                    action="Verify 2FA operativo",
                    expected="tokens activos para ciclo completo",
                    status_code=s_code,
                    body=s_body,
                )
                self.access_token = str(s_body.get("access") or "")
                self.refresh_token = str(s_body.get("refresh") or "")
                relogin_ok = True
                break
        if not relogin_ok:
            raise StepFailure("No se pudo completar re-login operativo 2FA")

    def _run_organization(self) -> None:
        module = "organization"
        company_a, branch_a1 = self._auth_context()

        comp_payload = {
            "name": "NECKTRAL AUXILIAR",
            "code": "NTAUX",
            "legal_name": "Necktral Auxiliar S.A.",
            "tax_id": "J-030123-002",
            "address": "Leon",
            "phone": "2222-0001",
            "email": "aux@necktral.local",
        }
        status_code, body = self._api_json(
            "POST",
            "/org/companies/",
            payload=comp_payload,
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="org.create_company",
            action="Crear segunda compañía",
            expected="company para intercompany",
            status_code=status_code,
            body=body,
            allowed_statuses=[201],
        )
        self.company_b_id = int(body.get("id"))

        status_code, body = self._api_json(
            "POST",
            "/org/branches/",
            payload={"name": "MAIN-02", "code": "MAIN02", "address": "Masaya"},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="org.create_branch",
            action="Crear sucursal #2 en compañía principal",
            expected="branch adicional",
            status_code=status_code,
            body=body,
        )
        self.branch_a2_id = int(body.get("id"))

        if self.company_b_id is None:
            raise StepFailure("company_b_id no inicializado")
        status_code, body = self._api_json(
            "POST",
            "/org/branches/",
            payload={"name": "AUX-01", "code": "AUX01", "address": "Chinandega"},
            token=self.access_token,
            company_id=int(self.company_b_id),
            branch_id=None,
        )
        body = self._record_http_step(
            module=module,
            key="org.create_branch",
            action="Crear sucursal en compañía auxiliar",
            expected="branch operativa intercompany",
            status_code=status_code,
            body=body,
        )
        self.branch_b1_id = int(body.get("id"))

    def _run_hr(self) -> None:
        module = "hr"
        company_a, branch_a1 = self._auth_context()

        status_code, body = self._api_json(
            "POST",
            "/hr/positions/",
            payload={"name": "Cajero POS", "code": "POS_CASHIER"},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="hr.create_position",
            action="Crear puesto Cajero POS",
            expected="position creada",
            status_code=status_code,
            body=body,
        )
        cashier_position_id = int(body.get("id"))

        status_code, body = self._api_json(
            "POST",
            "/hr/positions/",
            payload={"name": "Contador", "code": "ACCOUNTANT"},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="hr.create_position",
            action="Crear puesto Contador",
            expected="position creada",
            status_code=status_code,
            body=body,
        )
        accountant_position_id = int(body.get("id"))

        status_code, body = self._api_json(
            "POST",
            "/hr/employees/",
            payload={
                "employee_code": "EMP-POS-001",
                "first_name": "Caja",
                "last_name": "Operador",
                "email": "caja.operador@necktral.local",
            },
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="hr.create_employee",
            action="Crear empleado Cajero",
            expected="employee creada",
            status_code=status_code,
            body=body,
        )
        cashier_employee_id = int(body.get("id"))

        status_code, body = self._api_json(
            "POST",
            f"/hr/employees/{cashier_employee_id}/assignments/",
            payload={"position_id": cashier_position_id, "branch_id": branch_a1},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="hr.create_assignment",
            action="Asignar cajero a sucursal",
            expected="assignment activa",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            f"/hr/employees/{cashier_employee_id}/provision-user/",
            payload={
                "username": "cajero_pos_001",
                "email": "cajero_pos_001@necktral.local",
                "temp_password": "Tmp!POS001a",
            },
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="hr.provision_user",
            action="Provisionar usuario de cajero",
            expected="credenciales iniciales emitidas",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            f"/hr/employees/{cashier_employee_id}/reset-temp-password/",
            payload={"temp_password": "Tmp!POS002b"},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="hr.reset_temp_password",
            action="Reset temporal cajero",
            expected="password temporal rotado",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            "/hr/employees/",
            payload={
                "employee_code": "EMP-ACC-001",
                "first_name": "Conta",
                "last_name": "Analitica",
                "email": "conta.analitica@necktral.local",
            },
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="hr.create_employee",
            action="Crear empleado Contador",
            expected="employee creada",
            status_code=status_code,
            body=body,
        )
        accountant_employee_id = int(body.get("id"))

        status_code, body = self._api_json(
            "POST",
            f"/hr/employees/{accountant_employee_id}/assignments/",
            payload={"position_id": accountant_position_id, "branch_id": branch_a1},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="hr.create_assignment",
            action="Asignar contador",
            expected="assignment activa",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            f"/hr/employees/{accountant_employee_id}/provision-user/",
            payload={
                "username": "contador_001",
                "email": "contador_001@necktral.local",
                "temp_password": "Tmp!ACC001a",
            },
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="hr.provision_user",
            action="Provisionar usuario contador",
            expected="credenciales iniciales emitidas",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            f"/hr/employees/{accountant_employee_id}/revoke-access/",
            payload={"disable_user": False},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="hr.revoke_access",
            action="Revoke controlado contador",
            expected="acceso revocado de forma auditable",
            status_code=status_code,
            body=body,
        )

    def _random_checkout_line(self) -> dict[str, Any]:
        product = "DIESEL" if self.random.random() < 0.6 else "GASOLINE"
        volume_uom = "GALLON" if self.random.random() < 0.4 else "LITER"
        unit_price_uom = "PER_GALLON" if volume_uom == "GALLON" else "PER_LITER"
        volume = Decimal(str(self.random.uniform(3.0, 18.0))).quantize(VOL_Q, rounding=ROUND_HALF_UP)
        price = Decimal(str(self.random.uniform(34.0, 54.0))).quantize(VOL_Q, rounding=ROUND_HALF_UP)
        return {
            "product": product,
            "volume": f"{volume:.4f}",
            "volume_uom": volume_uom,
            "unit_price_entered": f"{price:.4f}",
            "unit_price_uom": unit_price_uom,
            "metadata": {
                "seed": self.seed,
                "strategy": "stochastic-balanced",
            },
        }

    def _load_auto_draft_validation_config(self) -> dict[str, Any]:
        config = self.contract.get("accounting_auto_draft_validation") or {}
        raw_pairs = config.get("required_event_pairs") or [
            {
                "source_module": "BILLING",
                "event_type": "DocumentIssued",
                "min_delta": 1,
            },
            {
                "source_module": "INVENTORY",
                "event_type": "InventoryMovementPosted",
                "min_delta": 1,
            },
        ]

        required_pairs: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for raw_pair in raw_pairs:
            source_module = ""
            event_type = ""
            min_delta_raw: Any = 1

            if isinstance(raw_pair, dict):
                source_module = str(raw_pair.get("source_module") or "").strip().upper()
                event_type = str(raw_pair.get("event_type") or "").strip()
                min_delta_raw = raw_pair.get("min_delta", 1)
            elif isinstance(raw_pair, str):
                parts = str(raw_pair).split(".", 1)
                if len(parts) == 2:
                    source_module = str(parts[0]).strip().upper()
                    event_type = str(parts[1]).strip()
                    min_delta_raw = 1
            else:
                raise StepFailure(
                    "Contrato inválido: accounting_auto_draft_validation.required_event_pairs contiene tipo no soportado."
                )

            if not source_module or not event_type:
                raise StepFailure(
                    "Contrato inválido: cada required_event_pair debe incluir source_module y event_type."
                )

            try:
                min_delta = int(min_delta_raw)
            except Exception as exc:  # noqa: BLE001
                raise StepFailure(
                    f"Contrato inválido: min_delta no es entero para {source_module}.{event_type}."
                ) from exc
            if min_delta < 1:
                raise StepFailure(
                    f"Contrato inválido: min_delta debe ser >= 1 para {source_module}.{event_type}."
                )

            pair_key = f"{source_module}.{event_type}"
            if pair_key in seen_keys:
                continue
            seen_keys.add(pair_key)
            required_pairs.append(
                {
                    "key": pair_key,
                    "source_module": source_module,
                    "event_type": event_type,
                    "min_delta": min_delta,
                }
            )

        if not required_pairs:
            raise StepFailure(
                "Contrato inválido: accounting_auto_draft_validation.required_event_pairs no puede estar vacío."
            )

        min_total_default = sum(int(row["min_delta"]) for row in required_pairs)
        try:
            min_total_delta = int(config.get("min_total_delta", min_total_default))
        except Exception as exc:  # noqa: BLE001
            raise StepFailure("Contrato inválido: min_total_delta debe ser entero.") from exc
        if min_total_delta < 1:
            raise StepFailure("Contrato inválido: min_total_delta debe ser >= 1.")

        try:
            max_wait_seconds = float(config.get("max_wait_seconds", 20))
        except Exception as exc:  # noqa: BLE001
            raise StepFailure("Contrato inválido: max_wait_seconds debe ser numérico.") from exc
        if max_wait_seconds < 0:
            raise StepFailure("Contrato inválido: max_wait_seconds debe ser >= 0.")

        try:
            poll_interval_seconds = float(config.get("poll_interval_seconds", 2))
        except Exception as exc:  # noqa: BLE001
            raise StepFailure("Contrato inválido: poll_interval_seconds debe ser numérico.") from exc
        if poll_interval_seconds <= 0:
            raise StepFailure("Contrato inválido: poll_interval_seconds debe ser > 0.")

        return {
            "required_pairs": required_pairs,
            "min_total_delta": int(min_total_delta),
            "max_wait_seconds": float(max_wait_seconds),
            "poll_interval_seconds": float(poll_interval_seconds),
        }

    def _collect_auto_draft_snapshot(
        self,
        *,
        company_id: int,
        required_pairs: list[dict[str, Any]],
        label: str,
    ) -> dict[str, Any]:
        compact_pairs = [
            {
                "key": str(pair["key"]),
                "source_module": str(pair["source_module"]),
                "event_type": str(pair["event_type"]),
            }
            for pair in required_pairs
        ]
        code = f"""
import json
from apps.kernels.accounting.models import JournalDraft

company_id = int({int(company_id)})
pairs = {compact_pairs!r}
by_pair = {{}}
total = 0
for pair in pairs:
    count = JournalDraft.objects.filter(
        economic_event__company_id=company_id,
        economic_event__source_module=pair["source_module"],
        economic_event__event_type=pair["event_type"],
    ).count()
    by_pair[str(pair["key"])] = int(count)
    total += int(count)
print(json.dumps({{"total": int(total), "by_pair": by_pair}}))
"""
        payload = self._run_backend_manage_shell_json(code, label=label)
        by_pair_raw = payload.get("by_pair") if isinstance(payload, dict) else {}
        by_pair = dict(by_pair_raw) if isinstance(by_pair_raw, dict) else {}
        return {
            "total": int(payload.get("total") or 0),
            "by_pair": {str(k): int(v or 0) for k, v in by_pair.items()},
        }

    @staticmethod
    def _evaluate_auto_draft_delta(
        *,
        before: dict[str, Any],
        after: dict[str, Any],
        required_pairs: list[dict[str, Any]],
        min_total_delta: int,
    ) -> dict[str, Any]:
        before_total = int(before.get("total") or 0)
        after_total = int(after.get("total") or 0)
        total_delta = int(after_total - before_total)

        before_by_pair = before.get("by_pair") if isinstance(before.get("by_pair"), dict) else {}
        after_by_pair = after.get("by_pair") if isinstance(after.get("by_pair"), dict) else {}
        delta_by_pair: dict[str, int] = {}
        coverage_rows: list[dict[str, Any]] = []
        missing_pairs: list[str] = []
        coverage_ok = True

        for pair in required_pairs:
            key = str(pair["key"])
            min_delta = int(pair["min_delta"])
            before_count = int(before_by_pair.get(key) or 0)
            after_count = int(after_by_pair.get(key) or 0)
            delta = int(after_count - before_count)
            delta_by_pair[key] = delta
            pair_ok = delta >= min_delta
            coverage_rows.append(
                {
                    "pair": key,
                    "min_delta": min_delta,
                    "before": before_count,
                    "after": after_count,
                    "delta": delta,
                    "passed": bool(pair_ok),
                }
            )
            if not pair_ok:
                coverage_ok = False
                missing_pairs.append(key)

        passed = bool(total_delta >= int(min_total_delta) and coverage_ok)
        return {
            "passed": passed,
            "before_total": before_total,
            "after_total": after_total,
            "total_delta": total_delta,
            "delta_by_pair": delta_by_pair,
            "coverage": coverage_rows,
            "missing_pairs": missing_pairs,
        }

    def _run_retail_fuel(self) -> None:
        module = "retail_fuel"
        company_a, branch_a1 = self._auth_context()
        auto_draft_cfg = self._load_auto_draft_validation_config()
        required_pairs = list(auto_draft_cfg["required_pairs"])
        min_total_delta = int(auto_draft_cfg["min_total_delta"])
        max_wait_seconds = float(auto_draft_cfg["max_wait_seconds"])
        poll_interval_seconds = float(auto_draft_cfg["poll_interval_seconds"])

        before_snapshot = self._collect_auto_draft_snapshot(
            company_id=company_a,
            required_pairs=required_pairs,
            label="drafts_before_retail_flow",
        )

        grant_payload = self._run_backend_manage_shell_json(
            """
import json
from django.contrib.auth import get_user_model
from apps.modulos.iam.models import OrgUnit
from apps.modulos.rbac.models import Role, RoleAssignment

User = get_user_model()
user = User.objects.filter(id=int(%d)).first()
company = OrgUnit.objects.filter(id=int(%d)).first()
role = Role.objects.filter(name="fuel_admin", is_active=True).first()
granted = False
if user and company and role:
    RoleAssignment.objects.get_or_create(
        user=user,
        role=role,
        org_unit=company,
        origin=RoleAssignment.Origin.MANUAL,
        defaults={"is_active": True, "origin_ref": "lifecycle"},
    )
    granted = True
print(json.dumps({"granted": bool(granted)}))
"""
            % (self.admin_user_id or 0, company_a),
            label="grant_fuel_admin",
        )
        granted = bool(grant_payload.get("granted"))
        self._record_check_step(
            module=module,
            key="fuel.grant_admin",
            action="Asignar rol fuel_admin a admin",
            expected="grant activo",
            passed=granted,
            actual=f"granted={granted}",
        )

        status_code, body = self._api_json(
            "POST",
            "/fuel/shifts/open/",
            payload={"note": "ciclo producto full"},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="fuel.shift_open",
            action="Abrir turno fuel",
            expected="turno OPEN",
            status_code=status_code,
            body=body,
        )
        shift_id = int(body.get("id"))

        status_code, body = self._api_json(
            "POST",
            "/retail/pos/sessions/open/",
            payload={"opening_amount": "200.00", "note": "apertura ciclo"},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="retail.pos_session_open",
            action="Abrir sesión POS/caja",
            expected="sesión OPEN",
            status_code=status_code,
            body=body,
        )
        pos_session_id = int(body.get("id"))

        closed_tickets: list[int] = []
        for idx in range(10):
            idem = f"lifecycle-ticket-{self.seed}-{idx + 1:02d}"
            open_payload = {
                "shift_id": shift_id,
                "idempotency_key": idem,
                "external_ref": f"LC-{idx + 1:03d}",
                "customer_name": "CONSUMIDOR FINAL",
                "sale_type": "PUBLIC",
                "payment_method": "CASH",
            }
            status_code, body = self._api_json(
                "POST",
                "/retail/pos/tickets/",
                payload=open_payload,
                token=self.access_token,
                company_id=company_a,
                branch_id=branch_a1,
            )
            body = self._record_http_step(
                module=module,
                key="retail.ticket_open",
                action=f"Abrir ticket POS #{idx + 1}",
                expected="ticket CART_OPEN",
                status_code=status_code,
                body=body,
            )
            ticket_id = int(body.get("id"))

            status_code, body = self._api_json(
                "POST",
                f"/retail/pos/tickets/{ticket_id}/checkout/",
                payload={"line": self._random_checkout_line()},
                token=self.access_token,
                company_id=company_a,
                branch_id=branch_a1,
            )
            body = self._record_http_step(
                module=module,
                key="retail.ticket_checkout",
                action=f"Checkout ticket POS #{idx + 1}",
                expected="ticket CLOSED con venta/pago",
                status_code=status_code,
                body=body,
                allowed_statuses=[200],
            )
            closed_tickets.append(int(body.get("id")))

        if not closed_tickets:
            raise StepFailure("No se cerraron tickets POS en la simulación")

        first_ticket = int(closed_tickets[0])
        status_code, body = self._api_json(
            "POST",
            f"/retail/pos/tickets/{first_ticket}/compensate/retry/",
            payload={"reason": "MANUAL_RETRY_SIM"},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="retail.ticket_comp_retry",
            action="Reintento compensación POS",
            expected="retry idempotente/resuelto",
            status_code=status_code,
            body=body,
        )

        ticket_to_void = int(closed_tickets[1] if len(closed_tickets) > 1 else closed_tickets[0])
        status_code, body = self._api_json(
            "POST",
            f"/retail/pos/voids/{ticket_to_void}/",
            payload={"reason": "SIM_VOID"},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="retail.ticket_void",
            action="Void ticket POS",
            expected="ticket VOIDED",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            f"/retail/pos/sessions/{pos_session_id}/close/",
            payload={"counted_amount": "200.00", "note": "cierre ciclo"},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="retail.pos_session_close",
            action="Cerrar sesión POS",
            expected="sesión CLOSED",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            f"/fuel/shifts/{shift_id}/close/",
            payload={"note": "cierre ciclo"},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="fuel.shift_close",
            action="Cerrar turno fuel",
            expected="turno CLOSED",
            status_code=status_code,
            body=body,
        )

        today = datetime.now(timezone.utc).date().isoformat()
        status_code, body = self._api_json(
            "GET",
            f"/fuel/reports/shift-close/{shift_id}/",
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="fuel.shift_report",
            action="Reporte cierre de turno",
            expected="reporte disponible",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "GET",
            f"/fuel/reports/daily-close/?date={today}",
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="fuel.daily_report",
            action="Reporte cierre diario",
            expected="reporte disponible",
            status_code=status_code,
            body=body,
        )

        start_ts = time.monotonic()
        attempts = 0
        after_snapshot = before_snapshot
        evaluation = self._evaluate_auto_draft_delta(
            before=before_snapshot,
            after=after_snapshot,
            required_pairs=required_pairs,
            min_total_delta=min_total_delta,
        )
        while True:
            attempts += 1
            after_snapshot = self._collect_auto_draft_snapshot(
                company_id=company_a,
                required_pairs=required_pairs,
                label=f"drafts_after_retail_flow_attempt_{attempts:02d}",
            )
            evaluation = self._evaluate_auto_draft_delta(
                before=before_snapshot,
                after=after_snapshot,
                required_pairs=required_pairs,
                min_total_delta=min_total_delta,
            )
            if evaluation["passed"]:
                break

            elapsed = float(time.monotonic() - start_ts)
            if elapsed >= max_wait_seconds:
                break
            time.sleep(poll_interval_seconds)

        elapsed_seconds = round(float(time.monotonic() - start_ts), 2)
        expected = (
            f"delta_total>={min_total_delta} y cobertura mínima por pares "
            f"{[row['key'] for row in required_pairs]}"
        )
        actual = (
            f"delta_total={evaluation['total_delta']} "
            f"(before={evaluation['before_total']}, after={evaluation['after_total']}) "
            f"delta_by_pair={json.dumps(evaluation['delta_by_pair'], ensure_ascii=False, sort_keys=True)}"
        )
        detail_payload = {
            "schema_version": 1,
            "required_pairs": [
                {
                    "pair": row["key"],
                    "source_module": row["source_module"],
                    "event_type": row["event_type"],
                    "min_delta": int(row["min_delta"]),
                }
                for row in required_pairs
            ],
            "min_total_delta": int(min_total_delta),
            "timing": {
                "attempts": int(attempts),
                "elapsed_seconds": elapsed_seconds,
                "max_wait_seconds": max_wait_seconds,
                "poll_interval_seconds": poll_interval_seconds,
            },
            "before": before_snapshot,
            "after": after_snapshot,
            "evaluation": evaluation,
        }
        self._record_check_step(
            module=module,
            key="accounting.auto_draft_from_cash_movement",
            action="Validar generación automática de borradores contables",
            expected=expected,
            passed=bool(evaluation["passed"]),
            actual=actual,
            detail=json.dumps(detail_payload, ensure_ascii=False),
        )

    def _run_sync(self) -> None:
        module = "sync"
        company_a, branch_a1 = self._auth_context()
        connector_id = f"edge-lifecycle-{self.seed}"
        connector_version = "0.3.0"

        status_code, body = self._api_json(
            "POST",
            "/retail/pos/peripherals/edge/challenge/",
            payload={
                "connector_id": connector_id,
                "connector_version": connector_version,
                "metadata": {"source": "product_lifecycle_full_cycle"},
            },
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="sync.edge_challenge",
            action="Emitir challenge edge",
            expected="challenge nonce emitido",
            status_code=status_code,
            body=body,
        )

        challenge_id = str(body.get("challenge_id") or "")
        nonce = str(body.get("nonce") or "")
        if not challenge_id or not nonce:
            raise StepFailure("Challenge edge sin challenge_id/nonce")

        secret_b64 = self._resolve_edge_secret_b64()
        try:
            secret = base64.b64decode(secret_b64.encode("utf-8"), validate=True)
        except Exception as exc:  # noqa: BLE001
            raise StepFailure(f"POS_EDGE_CONNECTOR_SHARED_SECRET inválido: {exc}") from exc

        msg = f"{challenge_id}.{nonce}.{company_a}.{branch_a1}.{connector_id}".encode("utf-8")
        signature = base64.b64encode(hmac.new(secret, msg, hashlib.sha256).digest()).decode("utf-8")

        handshake_payload = {
            "challenge_id": challenge_id,
            "connector_id": connector_id,
            "connector_version": connector_version,
            "signature": signature,
            "capability_registry": {"THERMAL_PRINTER": "supported"},
            "devices": [
                {
                    "device_key": "printer-main",
                    "device_kind": "THERMAL_PRINTER",
                    "capability_level": "supported",
                    "status": "ONLINE",
                    "metadata": {"driver": "escpos"},
                }
            ],
            "metadata": {"scope": "lifecycle"},
        }
        status_code, body = self._api_json(
            "POST",
            "/retail/pos/peripherals/edge/handshake/",
            payload=handshake_payload,
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="sync.edge_handshake",
            action="Handshake edge",
            expected="session ACTIVE con periféricos sincronizados",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "GET",
            "/retail/pos/peripherals/capabilities/",
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="sync.edge_capabilities",
            action="Consultar registry de capacidades",
            expected="registry consistente",
            status_code=status_code,
            body=body,
        )
        registry = dict(body.get("registry") or {}) if isinstance(body, dict) else {}
        has_printer = "THERMAL_PRINTER" in registry
        self._record_check_step(
            module=module,
            key="sync.edge_capabilities_assert",
            action="Validar capacidad THERMAL_PRINTER",
            expected="THERMAL_PRINTER presente",
            passed=has_printer,
            actual=f"has_printer={has_printer}",
        )

        status_code, body = self._api_json(
            "POST",
            "/retail/pos/peripherals/edge/challenge/",
            payload={"connector_id": f"{connector_id}-bad", "connector_version": connector_version},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="sync.edge_challenge",
            action="Emitir challenge para prueba BAD_SIGNATURE",
            expected="challenge emitido",
            status_code=status_code,
            body=body,
        )
        bad_challenge_id = str(body.get("challenge_id") or "")

        bad_signature_payload = {
            "challenge_id": bad_challenge_id,
            "connector_id": f"{connector_id}-bad",
            "connector_version": connector_version,
            "signature": base64.b64encode(b"bad-signature").decode("utf-8"),
            "capability_registry": {"THERMAL_PRINTER": "supported"},
            "devices": [],
        }
        status_code, body = self._api_json(
            "POST",
            "/retail/pos/peripherals/edge/handshake/",
            payload=bad_signature_payload,
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="sync.edge_bad_signature",
            action="Validar rechazo BAD_SIGNATURE",
            expected="rechazo estable de firma inválida",
            status_code=status_code,
            body=body,
        )

        cmd = [
            "docker",
            "compose",
            "exec",
            "-T",
            "backend",
            "bash",
            "-lc",
            "cd /app/backend && export DJANGO_SETTINGS_MODULE=config.settings.test && "
            "pytest -q "
            "src/tests/test_sync_v2_pos_commands.py::test_sync_v2_pos_ticket_command_happy_path "
            "src/tests/test_sync_v2_pos_commands.py::test_sync_v2_pos_compensation_retry_command",
        ]
        rc, stdout, stderr = self._run_cmd(cmd, timeout_sec=900)
        passed = rc == 0
        detail = (stdout + "\n" + stderr).strip()
        self._record_check_step(
            module=module,
            key="sync.batch_pytest",
            action="Validar batch sync command (ticket+compensación)",
            expected="pytest rc=0",
            passed=passed,
            actual=f"pytest_rc={rc}",
            detail=detail[-1500:],
        )

    def _coa_rows(self) -> list[dict[str, Any]]:
        return [
            {"code": "1101", "name": "Caja", "account_type": "ASSET", "is_postable": True, "is_active": True},
            {
                "code": "1301",
                "name": "CxC Intercompany",
                "account_type": "ASSET",
                "is_postable": True,
                "is_active": True,
            },
            {
                "code": "2109",
                "name": "CxP Intercompany",
                "account_type": "LIABILITY",
                "is_postable": True,
                "is_active": True,
            },
            {
                "code": "4101",
                "name": "Ingresos Intercompany",
                "account_type": "REVENUE",
                "is_postable": True,
                "is_active": True,
            },
            {
                "code": "5101",
                "name": "Gasto Intercompany",
                "account_type": "EXPENSE",
                "is_postable": True,
                "is_active": True,
            },
        ]

    def _seed_intercompany_grants(self) -> None:
        if self.company_a_id is None or self.company_b_id is None:
            raise StepFailure("No hay compañías para seed intercompany")

        code = """
import json
from apps.modulos.iam.models import CompanyLink, LinkGrant, OrgUnit
from apps.modulos.rbac.models import Permission

source_company = OrgUnit.objects.get(id=int(%d))
target_company = OrgUnit.objects.get(id=int(%d))
link, _ = CompanyLink.objects.get_or_create(
    from_company=target_company,
    to_company=source_company,
    defaults={"status": CompanyLink.Status.ACTIVE, "is_active": True},
)
if link.status != CompanyLink.Status.ACTIVE or not bool(link.is_active):
    link.status = CompanyLink.Status.ACTIVE
    link.is_active = True
    link.save(update_fields=["status", "is_active", "updated_at"])

perms = [
    "accounting.intercompany.write",
    "accounting.intercompany.reconcile",
    "accounting.intercompany.dispute",
    "accounting.intercompany.settle",
]
for code in perms:
    perm, _ = Permission.objects.get_or_create(
        code=code,
        defaults={"description": code, "is_active": True},
    )
    if not bool(perm.is_active):
        perm.is_active = True
        perm.save(update_fields=["is_active"])
    LinkGrant.objects.update_or_create(
        link=link,
        permission=perm,
        access_mode=LinkGrant.AccessMode.WRITE,
        scope_org_unit=None,
        defaults={"is_active": True, "valid_from": None, "valid_to": None},
    )

print(json.dumps({"ok": True, "link_id": int(link.id), "perms": perms}))
""" % (
            int(self.company_a_id),
            int(self.company_b_id),
        )
        self._run_backend_manage_shell_json(code, label="seed_intercompany_grants")

    def _seed_manual_journal_entry(self, *, company_id: int, branch_id: int) -> int:
        if self.admin_user_id is None:
            raise StepFailure("admin_user_id no inicializado")
        code = """
import json
import uuid
from decimal import Decimal
from django.contrib.auth import get_user_model
from apps.kernels.accounting.models import (
    ChartOfAccount,
    EconomicEvent,
    FiscalPeriod,
    JournalDraft,
    JournalEntry,
    JournalEntryLine,
    PostingRuleSet,
)
from apps.modulos.iam.models import OrgUnit
from django.utils import timezone

User = get_user_model()
company = OrgUnit.objects.get(id=int(%d))
branch = OrgUnit.objects.get(id=int(%d))
actor = User.objects.get(id=int(%d))

def ensure_account(code: str, name: str, account_type: str):
    row, _ = ChartOfAccount.objects.get_or_create(
        company=company,
        code=code,
        defaults={
            "name": name,
            "account_type": account_type,
            "is_postable": True,
            "is_active": True,
        },
    )
    if not bool(row.is_active):
        row.is_active = True
        row.save(update_fields=["is_active"])
    return row

cash = ensure_account("1101", "Caja", "ASSET")
revenue = ensure_account("4101", "Ingresos Intercompany", "REVENUE")
period, _ = FiscalPeriod.objects.get_or_create(
    company=company,
    year=timezone.localdate().year,
    month=timezone.localdate().month,
    defaults={"status": FiscalPeriod.Status.OPEN},
)
event = EconomicEvent.objects.create(
    source_module="ACCOUNTING",
    event_type="LifecycleSeedEntry",
    company=company,
    branch=branch,
    payload={"source": "product_lifecycle_full_cycle"},
)
rule = PostingRuleSet.objects.create(
    code=f"seed_{uuid.uuid4().hex[:8]}",
    version=1,
    status=PostingRuleSet.Status.ACTIVE,
    fiscal_mode=PostingRuleSet.FiscalMode.BOTH,
    scope_company=company,
    rules_json={"version": "1.0", "rules": []},
)
draft = JournalDraft.objects.create(
    economic_event=event,
    rule_set=rule,
    state=JournalDraft.State.POSTED,
    total_debit=Decimal("125.00"),
    total_credit=Decimal("125.00"),
    lines_json=[
        {"account": cash.code, "side": "DEBIT", "amount": "125.00"},
        {"account": revenue.code, "side": "CREDIT", "amount": "125.00"},
    ],
)
entry = JournalEntry.objects.create(
    draft=draft,
    period=period,
    company=company,
    branch=branch,
    debit_total=Decimal("125.00"),
    credit_total=Decimal("125.00"),
    posted_by=actor,
)
JournalEntryLine.objects.create(
    journal_entry=entry,
    line_no=1,
    account=cash,
    account_code_snapshot=cash.code,
    currency="NIO",
    fx_rate="1.00000000",
    amount_tx=Decimal("125.00"),
    debit_base=Decimal("125.00"),
    credit_base=Decimal("0.00"),
)
JournalEntryLine.objects.create(
    journal_entry=entry,
    line_no=2,
    account=revenue,
    account_code_snapshot=revenue.code,
    currency="NIO",
    fx_rate="1.00000000",
    amount_tx=Decimal("125.00"),
    debit_base=Decimal("0.00"),
    credit_base=Decimal("125.00"),
)
print(json.dumps({"entry_id": int(entry.id)}))
""" % (
            int(company_id),
            int(branch_id),
            int(self.admin_user_id),
        )
        payload = self._run_backend_manage_shell_json(code, label="seed_manual_journal_entry")
        return int(payload.get("entry_id"))

    def _run_accounting(self) -> None:
        module = "accounting"
        company_a, branch_a1 = self._auth_context()
        if self.company_b_id is None or self.branch_b1_id is None:
            raise StepFailure("Contexto company_b/branch_b1 no inicializado")

        coa_payload = {
            "rows": self._coa_rows(),
            "sync_deactivate": False,
            "functional_currency": "NIO",
            "phase7_enabled": True,
        }

        status_code, body = self._api_json(
            "PUT",
            "/accounting/chart-of-accounts/",
            payload=coa_payload,
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.coa_upsert",
            action="Upsert CoA compañía principal",
            expected="catálogo activo",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "PUT",
            "/accounting/chart-of-accounts/",
            payload=coa_payload,
            token=self.access_token,
            company_id=int(self.company_b_id),
            branch_id=int(self.branch_b1_id),
        )
        self._record_http_step(
            module=module,
            key="accounting.coa_upsert",
            action="Upsert CoA compañía auxiliar",
            expected="catálogo activo",
            status_code=status_code,
            body=body,
        )

        today = datetime.now(timezone.utc).date().isoformat()
        status_code, body = self._api_json(
            "POST",
            "/accounting/fx-rates/",
            payload={
                "rate_date": today,
                "from_currency": "USD",
                "to_currency": "NIO",
                "rate_type": "CLOSING",
                "rate": "36.50000000",
            },
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.fx_rate_upsert",
            action="Configurar FX",
            expected="FX rate vigente",
            status_code=status_code,
            body=body,
        )

        self._seed_intercompany_grants()
        self._record_check_step(
            module=module,
            key="accounting.intercompany_grants_seeded",
            action="Seed grants intercompany",
            expected="grants WRITE activos",
            passed=True,
            actual="ok=true",
        )

        tx_payload = {
            "target_company_id": int(self.company_b_id),
            "amount": "150.00",
            "currency": "NIO",
            "source_account_code": "4101",
            "target_account_code": "5101",
            "source_side": "CREDIT",
            "target_side": "DEBIT",
            "description": "Lifecycle intercompany",
            "reference_code": f"LC-IC-{self.seed}",
            "effective_at": datetime.now(timezone.utc).isoformat(),
        }
        status_code, body = self._api_json(
            "POST",
            "/accounting/intercompany/transactions/",
            payload=tx_payload,
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="accounting.intercompany_create",
            action="Crear transacción intercompany",
            expected="tx PENDING",
            status_code=status_code,
            body=body,
        )
        tx_id = str(body.get("tx_id") or "")
        if not tx_id:
            raise StepFailure("Creación intercompany sin tx_id")

        status_code, body = self._api_json(
            "POST",
            f"/accounting/intercompany/transactions/{tx_id}/confirm/",
            payload={"allow_same_actor": True},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.intercompany_confirm",
            action="Confirmar intercompany",
            expected="tx CONFIRMED",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            f"/accounting/intercompany/transactions/{tx_id}/reconcile/",
            payload={"source_amount": "150.00", "target_amount": "150.00", "mark_dispute": False},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.intercompany_reconcile",
            action="Conciliar intercompany",
            expected="diferencia cero",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "POST",
            f"/accounting/intercompany/transactions/{tx_id}/close/",
            payload={"allow_difference": False},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.intercompany_close",
            action="Cerrar intercompany",
            expected="tx CLOSED",
            status_code=status_code,
            body=body,
        )

        year = datetime.now(timezone.utc).year
        month = datetime.now(timezone.utc).month
        status_code, body = self._api_json(
            "POST",
            "/accounting/consolidation/run/",
            payload={"year": year, "month": month, "company_ids": [company_a, int(self.company_b_id)], "strict": True},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        body = self._record_http_step(
            module=module,
            key="accounting.consolidation_run",
            action="Correr consolidación por período efectivo",
            expected="run COMPLETED|idempotent",
            status_code=status_code,
            body=body,
        )
        run_id = str(body.get("run_id") or "")
        if not run_id:
            raise StepFailure("Consolidation run sin run_id")

        status_code, tb_body = self._api_json(
            "GET",
            f"/accounting/consolidation/reports/trial-balance/?run_id={run_id}",
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.consolidation_tb",
            action="Generar TB consolidado",
            expected="reporte consolidado disponible",
            status_code=status_code,
            body=tb_body,
        )

        status_code, pnl_body = self._api_json(
            "GET",
            f"/accounting/consolidation/reports/pnl/?run_id={run_id}",
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.consolidation_pnl",
            action="Generar PyG consolidado",
            expected="reporte consolidado disponible",
            status_code=status_code,
            body=pnl_body,
        )

        status_code, body = self._api_json(
            "GET",
            f"/accounting/reports/trial-balance/?year={year}&month={month}",
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.report_tb",
            action="Generar TB operativo",
            expected="TB por período disponible",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "GET",
            f"/accounting/reports/pnl/?year={year}&month={month}",
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.report_pnl",
            action="Generar PyG operativo",
            expected="PyG por período disponible",
            status_code=status_code,
            body=body,
        )

        status_code, body = self._api_json(
            "GET",
            f"/accounting/journal-entries/?year={year}&month={month}",
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.journal_entries_list",
            action="Listar asientos del período",
            expected="listado de asientos",
            status_code=status_code,
            body=body,
            allowed_statuses=[200],
        )

        entry_id = None
        if isinstance(body, dict):
            results = list(body.get("results") or [])
            if results:
                try:
                    entry_id = int(results[0].get("id"))
                except Exception:
                    entry_id = None

        if entry_id is None:
            entry_id = self._seed_manual_journal_entry(company_id=company_a, branch_id=branch_a1)
            self._record_check_step(
                module=module,
                key="accounting.manual_seed_entry",
                action="Seed técnico de asiento para reversa",
                expected="entry_id disponible",
                passed=True,
                actual=f"entry_id={entry_id}",
            )

        status_code, body = self._api_json(
            "POST",
            f"/accounting/journal-entries/{entry_id}/reverse/",
            payload={"reason": "LIFECYCLE_REVERSE", "allow_same_poster": True},
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        self._record_http_step(
            module=module,
            key="accounting.journal_entry_reverse",
            action="Reversa de asiento",
            expected="reversa creada o idempotente",
            status_code=status_code,
            body=body,
        )

        status_code, summary_body = self._api_json(
            "GET",
            f"/accounting/consolidation/runs/{run_id}/summary/",
            token=self.access_token,
            company_id=company_a,
            branch_id=branch_a1,
        )
        summary_body = self._record_http_step(
            module=module,
            key="accounting.consolidation_summary",
            action="Validar resumen de consolidación",
            expected="summary consistente",
            status_code=status_code,
            body=summary_body,
            allowed_statuses=[200],
        )
        summary_payload = dict(summary_body.get("summary") or {}) if isinstance(summary_body, dict) else {}
        self.intercompany_consistency = {
            "run_id": run_id,
            "run_status": str(summary_body.get("status") or ""),
            "issues_count": int(summary_payload.get("issues_count") or 0),
            "tx_id": tx_id,
        }
        self._record_check_step(
            module=module,
            key="accounting.intercompany_consistency",
            action="Consistencia intercompany/consolidación",
            expected="issues_count=0 y status COMPLETED",
            passed=(
                str(self.intercompany_consistency.get("run_status")) == "COMPLETED"
                and int(self.intercompany_consistency.get("issues_count") or 0) == 0
            ),
            actual=(
                f"run_status={self.intercompany_consistency.get('run_status')} "
                f"issues_count={self.intercompany_consistency.get('issues_count')}"
            ),
        )

    def _run_orphan_checks(self) -> None:
        module = "accounting"
        company_a, _branch_a1 = self._auth_context()
        year = datetime.now(timezone.utc).year
        month = datetime.now(timezone.utc).month

        code = """
import json
from decimal import Decimal
from django.db.models import Count, Q
from apps.kernels.accounting.models import ConsolidationRun, IntercompanyTransaction, JournalEntry
from apps.modulos.estacion_servicios.models import FuelSale
from apps.modulos.retail_pos.models import PosTicket

pos_orphans = PosTicket.objects.filter(status="CLOSED").filter(
    Q(sale_id__isnull=True) | Q(payment_intent_id__isnull=True)
).count()
fuel_orphans = FuelSale.objects.filter(dispense_id__isnull=True).count()
journal_orphans = JournalEntry.objects.annotate(line_count=Count("lines")).filter(line_count=0).count()
closed_diff = IntercompanyTransaction.objects.filter(status="CLOSED").exclude(difference_amount=Decimal("0.00")).count()
blocked_runs = ConsolidationRun.objects.filter(
    parent_company_id=int(%d), year=int(%d), month=int(%d), status="BLOCKED"
).count()
inconsistency = int(closed_diff) + int(blocked_runs)

payload = {
    "pos_ticket_closed_missing_sale_or_payment": int(pos_orphans),
    "fuel_sale_without_dispense": int(fuel_orphans),
    "journal_entry_without_lines": int(journal_orphans),
    "intercompany_or_consolidation_inconsistency": int(inconsistency),
    "closed_intercompany_with_difference": int(closed_diff),
    "blocked_consolidation_runs": int(blocked_runs),
}
payload["total"] = (
    payload["pos_ticket_closed_missing_sale_or_payment"]
    + payload["fuel_sale_without_dispense"]
    + payload["journal_entry_without_lines"]
    + payload["intercompany_or_consolidation_inconsistency"]
)
print(json.dumps(payload))
""" % (
            int(company_a),
            int(year),
            int(month),
        )
        checks = self._run_backend_manage_shell_json(code, label="orphan_checks")
        self.orphan_checks = checks

        self._record_check_step(
            module=module,
            key="integrity.orphan_checks",
            action="Validar huérfanos mínimos obligatorios",
            expected="total=0",
            passed=int(checks.get("total") or 0) == 0,
            actual=f"total={int(checks.get('total') or 0)}",
            detail=json.dumps(checks, ensure_ascii=False),
        )

    def run(self) -> dict[str, Any]:
        try:
            self._run_iam()
            self._run_organization()
            self._run_hr()
            self._run_retail_fuel()
            self._run_sync()
            self._run_accounting()
            self._run_orphan_checks()
        except StepFailure as exc:
            self.global_error = str(exc)
        except Exception as exc:  # noqa: BLE001
            self.global_error = f"Unhandled simulation error: {exc}"

        return self._build_summary()

    def _build_module_results(self) -> dict[str, Any]:
        buckets: dict[str, dict[str, int]] = {}
        for step in self.steps:
            row = buckets.setdefault(step.module, {"steps": 0, "passed": 0, "failed": 0})
            row["steps"] += 1
            if step.passed:
                row["passed"] += 1
            else:
                row["failed"] += 1

        out: dict[str, Any] = {}
        for module, stats in buckets.items():
            out[module] = {
                **stats,
                "pass": bool(stats["steps"] > 0 and stats["failed"] == 0),
            }
        return out

    def _build_summary(self) -> dict[str, Any]:
        module_results = self._build_module_results()
        required_modules = list(self.contract.get("required_modules") or [])
        orphan_total = int((self.orphan_checks or {}).get("total") or 0)
        required_ok = all(bool(module_results.get(m, {}).get("pass")) for m in required_modules)
        functional_pass = bool(not self.global_error and required_ok and orphan_total <= 0)

        http_violations = 0
        for step in self.steps:
            if step.http_status is None:
                continue
            if not step.passed:
                http_violations += 1

        summary = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "started_at": self.started_at.isoformat(),
            "timezone": self.timezone_name,
            "seed": int(self.seed),
            "base_url": self.base_url,
            "status": "PASS" if functional_pass else "FAIL",
            "pass": functional_pass,
            "global_error": self.global_error,
            "warnings": list(self.warnings),
            "required_modules": required_modules,
            "module_results": module_results,
            "http_contract": {
                "default_allowed_statuses": self.contract.get("default_allowed_statuses") or [200, 201],
                "status_overrides": self.contract.get("status_overrides") or {},
                "violations_count": int(http_violations),
            },
            "orphan_checks": self.orphan_checks,
            "intercompany_consistency": self.intercompany_consistency,
            "context": {
                "admin_username": self.admin_username,
                "admin_user_id": self.admin_user_id,
                "company_a_id": self.company_a_id,
                "company_b_id": self.company_b_id,
                "branch_a1_id": self.branch_a1_id,
                "branch_a2_id": self.branch_a2_id,
                "branch_b1_id": self.branch_b1_id,
            },
            "steps": [asdict(step) for step in self.steps],
        }
        return summary

    def write_outputs(self, summary: dict[str, Any]) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        functional_file = self.out_dir / "20_product_lifecycle_functional.json"
        functional_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        lines = [
            "# Product Lifecycle Full Cycle Log",
            "",
            f"- Generated at (UTC): `{summary.get('generated_at')}`",
            f"- Timezone reference: `{self.timezone_name}`",
            f"- Seed: `{self.seed}`",
            f"- Functional status: **{summary.get('status')}**",
            "",
            "## Step Trace",
            "",
        ]

        for step in self.steps:
            module_label = str(step.module or "").upper()
            state = "PASS" if step.passed else "FAIL"
            actual = step.actual
            if step.http_status is not None:
                actual = f"{actual} (http={step.http_status})"
            lines.append(
                f"- [{module_label}] -> {step.action} -> {step.expected} -> {state} | actual: {actual}"
            )
            if step.detail:
                lines.append(f"  - detail: {step.detail}")

        if summary.get("global_error"):
            lines.extend(
                [
                    "",
                    "## Error",
                    "",
                    f"- `{summary.get('global_error')}`",
                ]
            )

        log_file = self.out_dir / "31_product_lifecycle_log.md"
        log_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulación dinámica integral del ciclo completo de producto ERP_CRM")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://localhost:8000/api"))
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--seed", type=int, default=int(os.getenv("SIM_SEED", "20260412")))
    parser.add_argument("--admin-username", default=os.getenv("PRODUCT_LIFECYCLE_ADMIN_USERNAME", "root_lifecycle"))
    parser.add_argument("--admin-password", default=os.getenv("PRODUCT_LIFECYCLE_ADMIN_PASSWORD", "Tmp!Lifecycle2026"))
    parser.add_argument(
        "--contract",
        default="qa/contracts/product_lifecycle_full_cycle_contract.json",
        help="Ruta del contrato operativo QA para esta simulación",
    )
    parser.add_argument("--timezone", default=os.getenv("TZ", "America/Managua"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sim = ProductLifecycleSimulation(
        base_url=str(args.base_url),
        out_dir=Path(str(args.out_dir)),
        seed=int(args.seed),
        admin_username=str(args.admin_username),
        admin_password=str(args.admin_password),
        contract_path=Path(str(args.contract)),
        timezone_name=str(args.timezone),
    )
    summary = sim.run()
    sim.write_outputs(summary)
    print(json.dumps({"status": summary.get("status"), "functional_file": str(Path(args.out_dir) / "20_product_lifecycle_functional.json")}, ensure_ascii=False))
    return 0 if bool(summary.get("pass")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
