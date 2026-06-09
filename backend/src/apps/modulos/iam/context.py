from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# IAM-03: lista única de rutas exentas de contexto organizacional. Antes
# `JWTAuthWithOrgContext` (authentication.py) y `OrgContextMiddleware`
# (context_middleware.py) mantenían listas divergentes (auth eximía /2fa/verify/
# y /password/, el middleware no) → riesgo de drift de seguridad. Ambos importan
# de aquí. Es la UNIÓN (superset) de ambas: las rutas de auth/2fa/password/docs
# no requieren X-Company-Id.
EXEMPT_PATH_PREFIXES: tuple[str, ...] = (
    "/admin/",
    "/api/auth/login/",
    "/api/v1/auth/login/",
    "/api/auth/refresh/",
    "/api/v1/auth/refresh/",
    "/api/auth/logout/",
    "/api/v1/auth/logout/",
    "/api/auth/2fa/verify/",
    "/api/v1/auth/2fa/verify/",
    "/api/auth/me/",
    "/api/v1/auth/me/",
    "/api/auth/me/acl/",
    "/api/v1/auth/me/acl/",
    "/api/auth/bootstrap/",
    "/api/v1/auth/bootstrap/",
    "/api/auth/password/",
    "/api/v1/auth/password/",
    "/api/schema/",
    "/api/v1/schema/",
    "/api/docs/",
)


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    company_id: Optional[int]
    branch_id: Optional[int]
    data_company_id: Optional[int]
    data_branch_id: Optional[int]


def attach_request_context(
    request,
    *,
    company=None,
    branch=None,
    data_company=None,
    data_branch=None,
) -> None:
    """Adjunta contexto operativo en request.ctx.

    Contrato:
    - No reemplaza request.company/request.branch (ya usados en otras capas).
    - Usa request.request_id si existe; si no, lo deja en blanco.
    """

    request_id = getattr(request, "request_id", "") or ""

    ctx = RequestContext(
        request_id=request_id,
        company_id=getattr(company, "id", None),
        branch_id=getattr(branch, "id", None),
        data_company_id=getattr(data_company, "id", None),
        data_branch_id=getattr(data_branch, "id", None),
    )

    setattr(request, "ctx", ctx)

    raw = getattr(request, "_request", None)
    if raw is not None:
        setattr(raw, "ctx", ctx)
