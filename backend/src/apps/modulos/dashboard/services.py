from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, cast
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.selectors import get_effective_permissions_for_scope

from .models import DashboardEmbedGrant


class DashboardValidationError(ValueError):
    pass


class DashboardPermissionDenied(PermissionError):
    pass


class DashboardConflictError(RuntimeError):
    pass


class DashboardAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspaceSpec:
    key: str
    title: str
    description: str
    required_permissions: tuple[str, ...]
    datasets: tuple[str, ...]


WORKSPACE_REGISTRY: tuple[WorkspaceSpec, ...] = (
    WorkspaceSpec(
        key="executive",
        title="Executive Workspace",
        description="Vista directiva de ingresos, margen y posición financiera.",
        required_permissions=("report.dashboard.read", "report.dataset.read", "accounting.report.read"),
        datasets=(
            "accounting.pnl.period",
            "accounting.balance_sheet.as_of",
            "accounting.trial_balance.period",
        ),
    ),
    WorkspaceSpec(
        key="operations",
        title="Operations Workspace",
        description="Monitoreo operativo Fuel + conciliación contable operacional.",
        required_permissions=(
            "report.dashboard.read",
            "report.dataset.read",
            "fuel.reports.view",
            "accounting.report.read",
        ),
        datasets=(
            "fuel.sales.by_shift.daily",
            "fuel.sales.by_pump.daily",
            "fuel.dispense_vs_sale.daily",
            "accounting.operational_reconciliation.period",
        ),
    ),
)

_WORKSPACE_MAP = {row.key: row for row in WORKSPACE_REGISTRY}


def _workspace_to_dict(spec: WorkspaceSpec, *, compose_allowed: bool) -> dict[str, Any]:
    return {
        "workspace_key": spec.key,
        "title": spec.title,
        "description": spec.description,
        "required_permissions": list(spec.required_permissions),
        "datasets": list(spec.datasets),
        "compose_allowed": bool(compose_allowed),
    }


def _get_workspace_or_raise(workspace_key: str) -> WorkspaceSpec:
    key = str(workspace_key or "").strip().lower()
    spec = _WORKSPACE_MAP.get(key)
    if spec is None:
        raise DashboardValidationError("workspace_key inválido.")
    return spec


def _resolved_branch_for_scope(*, user, company: OrgUnit, branch_id: int | None, request_branch) -> OrgUnit | None:
    if branch_id is None:
        return request_branch
    branch = OrgUnit.objects.filter(
        id=branch_id,
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        is_active=True,
    ).first()
    if branch is None:
        raise DashboardValidationError("branch_id inválido para la empresa activa.")
    has_membership = UserMembership.objects.filter(user=user, org_unit=branch, is_active=True).exists()
    if not has_membership:
        has_company_membership = UserMembership.objects.filter(user=user, org_unit=company, is_active=True).exists()
        if not has_company_membership:
            raise DashboardPermissionDenied("Sin acceso a la sucursal solicitada.")
    return branch


def _effective_permissions(*, user, company: OrgUnit, branch: OrgUnit | None) -> set[str]:
    include_global = bool(getattr(settings, "RBAC_INCLUDE_GLOBAL_USERROLES", False))
    perms = get_effective_permissions_for_scope(
        user,
        company=company,
        branch=branch,
        include_global=include_global,
    )
    return {str(code).strip() for code in perms if str(code).strip()}


def _ensure_required_permissions(*, effective: set[str], required: set[str]) -> None:
    if "*" in effective:
        return
    missing = sorted(code for code in required if code not in effective)
    if missing:
        raise DashboardPermissionDenied(f"Permisos requeridos no satisfechos: {', '.join(missing)}")


def _token_exp_to_dt(exp: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(exp), tz=dt_timezone.utc)
    except Exception as exc:  # pragma: no cover - defensive
        raise DashboardAuthError("Token inválido (exp).") from exc


def list_workspaces_for_request(*, request) -> list[dict[str, Any]]:
    user = getattr(request, "user", None)
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    if user is None or not getattr(user, "is_authenticated", False):
        raise DashboardAuthError("Usuario no autenticado.")
    if company is None:
        raise DashboardValidationError("X-Company-Id requerido.")

    effective = _effective_permissions(user=user, company=company, branch=branch)
    can_compose = "report.dashboard.compose" in effective or "*" in effective

    rows: list[dict[str, Any]] = []
    for spec in WORKSPACE_REGISTRY:
        if "*" in effective or all(code in effective for code in spec.required_permissions):
            rows.append(_workspace_to_dict(spec, compose_allowed=can_compose))
    return rows


def create_embed_token_for_request(
    *,
    request,
    workspace_key: str,
    branch_id: int | None = None,
    require_compose: bool = False,
) -> dict[str, Any]:
    user = getattr(request, "user", None)
    company = getattr(request, "company", None)
    if user is None or not getattr(user, "is_authenticated", False):
        raise DashboardAuthError("Usuario no autenticado.")
    if company is None:
        raise DashboardValidationError("X-Company-Id requerido.")

    spec = _get_workspace_or_raise(workspace_key)
    branch = _resolved_branch_for_scope(
        user=user,
        company=company,
        branch_id=branch_id,
        request_branch=getattr(request, "branch", None),
    )
    if branch is None:
        raise DashboardValidationError("X-Branch-Id requerido para analytics en esta fase.")
    effective = _effective_permissions(user=user, company=company, branch=branch)
    required = set(spec.required_permissions)
    if require_compose:
        required.add("report.dashboard.compose")
    _ensure_required_permissions(effective=effective, required=required)

    token = AccessToken.for_user(user)
    token["purpose"] = "dash_embed"
    token["sub"] = str(getattr(user, "id", ""))
    token["company_id"] = int(company.id)
    token["branch_id"] = int(branch.id) if branch is not None else None
    token["workspace_key"] = spec.key
    token["perm_codes"] = sorted(effective)
    token.set_exp(lifetime=timedelta(seconds=90))

    jti = str(token.get("jti") or "")
    exp_at = _token_exp_to_dt(token.get("exp"))
    grant = DashboardEmbedGrant.objects.create(
        jti=jti,
        user=user,
        company=company,
        branch=branch,
        workspace_key=spec.key,
        perm_codes_json=sorted(effective),
        status=DashboardEmbedGrant.Status.ISSUED,
        expires_at=exp_at,
    )

    raw_token = str(token)
    bootstrap_url = f"/analytics/bootstrap?token={quote(raw_token, safe='')}"
    return {
        "embed_grant_id": int(grant.id),
        "workspace": _workspace_to_dict(spec, compose_allowed=("report.dashboard.compose" in effective or "*" in effective)),
        "workspace_key": spec.key,
        "bootstrap_url": bootstrap_url,
        "expires_at": exp_at.isoformat(),
    }


def redeem_embed_token(*, token_str: str) -> dict[str, Any]:
    raw = str(token_str or "").strip()
    if not raw:
        raise DashboardValidationError("token es requerido.")
    try:
        decoded = AccessToken(cast(Any, raw))
    except TokenError as exc:
        raise DashboardAuthError("Token embed inválido o expirado.") from exc

    if str(decoded.get("purpose") or "") != "dash_embed":
        raise DashboardAuthError("Token embed inválido (purpose).")

    jti = str(decoded.get("jti") or "")
    if not jti:
        raise DashboardAuthError("Token embed inválido (jti).")

    grant = DashboardEmbedGrant.objects.select_related("user", "company", "branch").filter(jti=jti).first()
    if grant is None:
        raise DashboardAuthError("Embed grant no encontrado.")

    now = timezone.now()
    if grant.expires_at <= now:
        if grant.status == DashboardEmbedGrant.Status.ISSUED:
            grant.status = DashboardEmbedGrant.Status.EXPIRED
            grant.save(update_fields=["status", "updated_at"])
        raise DashboardAuthError("Embed grant expirado.")
    if grant.status == DashboardEmbedGrant.Status.REDEEMED:
        raise DashboardConflictError("Embed grant ya canjeado.")
    if grant.status != DashboardEmbedGrant.Status.ISSUED:
        raise DashboardAuthError("Embed grant no disponible.")

    claim_company = int(decoded.get("company_id") or 0)
    claim_branch = decoded.get("branch_id")
    claim_workspace = str(decoded.get("workspace_key") or "").strip().lower()
    if claim_company != int(grant.company_id or 0):
        raise DashboardAuthError("Token embed inválido (scope company).")
    if claim_workspace != str(grant.workspace_key or "").strip().lower():
        raise DashboardAuthError("Token embed inválido (workspace).")
    if grant.branch_id is None and claim_branch not in (None, "", 0):
        raise DashboardAuthError("Token embed inválido (scope branch).")
    if grant.branch_id is not None and int(claim_branch or 0) != int(grant.branch_id):
        raise DashboardAuthError("Token embed inválido (scope branch).")

    reporting_token = AccessToken.for_user(grant.user)
    reporting_token["purpose"] = "reporting_embed"
    reporting_token["company_id"] = int(grant.company_id)
    reporting_token["branch_id"] = int(grant.branch_id) if grant.branch_id is not None else None
    reporting_token["workspace_key"] = str(grant.workspace_key)
    reporting_token["perm_codes"] = list(grant.perm_codes_json or [])
    reporting_token.set_exp(lifetime=timedelta(minutes=15))
    reporting_exp = _token_exp_to_dt(reporting_token.get("exp"))

    grant.status = DashboardEmbedGrant.Status.REDEEMED
    grant.redeemed_at = now
    grant.save(update_fields=["status", "redeemed_at", "updated_at"])

    spec = _get_workspace_or_raise(grant.workspace_key)
    return {
        "reporting_access_token": str(reporting_token),
        "expires_at": reporting_exp.isoformat(),
        "workspace": _workspace_to_dict(
            spec,
            compose_allowed=(
                "report.dashboard.compose" in set(grant.perm_codes_json or [])
                or "*" in set(grant.perm_codes_json or [])
            ),
        ),
    }
