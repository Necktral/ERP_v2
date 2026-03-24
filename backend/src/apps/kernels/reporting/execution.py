from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from django.utils import timezone

from .contracts import build_dataset_envelope
from .domain_adapters import accounting as accounting_adapter
from .enums import RunStatus
from .exceptions import DatasetExecutionError, DatasetScopeError, ReportingValidationError
from .lineage import build_lineage
from .models import ReportRun
from .permissions import ensure_permissions
from .registry import DatasetSpec, get_dataset_spec


@dataclass(frozen=True)
class ResolvedReportScope:
    company: Any
    branch: Any | None
    scope_level: str
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope_level": self.scope_level,
            "company_id": getattr(self.company, "id", None),
            "branch_id": getattr(self.branch, "id", None),
            "source": self.source,
        }


def _parse_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ReportingValidationError(f"{field_name} no puede ser vacío.")
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise ReportingValidationError(f"{field_name} debe ser fecha ISO (YYYY-MM-DD).") from exc
    raise ReportingValidationError(f"{field_name} debe ser fecha válida.")


def _normalize_filters(raw_filters: dict[str, Any], schema: dict[str, dict[str, Any]]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    provided = set(raw_filters.keys())
    allowed = set(schema.keys())
    unknown = sorted(provided - allowed)
    if unknown:
        raise ReportingValidationError(f"Filtros no permitidos: {', '.join(unknown)}")

    for field_name, rule in schema.items():
        required = bool(rule.get("required", False))
        if required and field_name not in raw_filters:
            raise ReportingValidationError(f"Filtro requerido ausente: {field_name}")
        if field_name not in raw_filters:
            continue

        expected_type = str(rule.get("type") or "str")
        value = raw_filters[field_name]
        if expected_type == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ReportingValidationError(f"{field_name} debe ser entero.")
            normalized[field_name] = int(value)
        elif expected_type == "date":
            normalized[field_name] = _parse_date(value, field_name=field_name)
        elif expected_type == "str":
            if not isinstance(value, str):
                raise ReportingValidationError(f"{field_name} debe ser texto.")
            val = value.strip()
            if not val and required:
                raise ReportingValidationError(f"{field_name} no puede ser vacío.")
            normalized[field_name] = val
        else:
            normalized[field_name] = value

    year = normalized.get("year")
    month = normalized.get("month")
    if (year is None) ^ (month is None):
        raise ReportingValidationError("year y month deben enviarse juntos.")
    if "date_from" in normalized and "date_to" in normalized and normalized["date_from"] > normalized["date_to"]:
        raise ReportingValidationError("date_from debe ser menor o igual que date_to.")
    if "as_of" in normalized and ("date_from" in normalized or "date_to" in normalized):
        raise ReportingValidationError("as_of no puede combinarse con date_from/date_to.")

    return normalized


def _resolve_scope(*, request, spec: DatasetSpec) -> ResolvedReportScope:
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    if company is None:
        raise DatasetScopeError("Contexto company requerido para reporting.")
    if spec.scope_level == "BRANCH" and branch is None:
        raise DatasetScopeError("Contexto branch requerido para este dataset.")
    return ResolvedReportScope(company=company, branch=branch, scope_level=spec.scope_level, source="request_context")


def _serialize_filters_for_storage(filters: dict[str, Any]) -> dict[str, Any]:
    serialized: dict[str, Any] = {}
    for key, value in filters.items():
        if isinstance(value, datetime):
            serialized[key] = value.date().isoformat()
        elif isinstance(value, date):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def _adapter_run(*, spec: DatasetSpec, scope: ResolvedReportScope, filters: dict[str, Any]) -> dict[str, Any]:
    if spec.domain_owner == "ACCOUNTING":
        return accounting_adapter.run_dataset(
            dataset_key=spec.dataset_key,
            company=scope.company,
            branch=scope.branch,
            filters=filters,
        )
    raise DatasetExecutionError(f"No existe adapter para domain_owner={spec.domain_owner}")


def _result_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def execute_dataset(
    *,
    dataset_key: str,
    request,
    filters: dict[str, Any] | None = None,
    consumer_type: str = "API",
    consumer_ref: str = "",
    enforce_kernel_permission: bool = True,
) -> tuple[dict[str, Any], ReportRun]:
    spec = get_dataset_spec(dataset_key)
    scope = _resolve_scope(request=request, spec=spec)
    normalized_filters = _normalize_filters(filters or {}, spec.filters_schema)

    required_permissions = spec.required_permissions if enforce_kernel_permission else list(spec.domain_permissions)
    ensure_permissions(
        user=getattr(request, "user", None),
        company=scope.company,
        branch=scope.branch,
        required_permissions=required_permissions,
    )

    started_at = timezone.now()
    run = ReportRun.objects.create(
        dataset_key=spec.dataset_key,
        requested_by=getattr(request, "user", None),
        company=scope.company,
        branch=scope.branch,
        filters_json=_serialize_filters_for_storage(normalized_filters),
        status=RunStatus.RUNNING,
        started_at=started_at,
        consumer_type=consumer_type,
        consumer_ref=consumer_ref,
        schema_version_used=spec.schema_version,
        semantic_version_used=spec.semantic_version,
    )

    try:
        adapter_payload = _adapter_run(spec=spec, scope=scope, filters=normalized_filters)
        lineage = build_lineage(
            run_id=str(run.run_id),
            dataset_key=spec.dataset_key,
            source_modules=list((adapter_payload.get("source_summary") or {}).get("source_modules") or [spec.domain_owner]),
            semantic_version=spec.semantic_version,
            schema_version=spec.schema_version,
        )
        envelope = build_dataset_envelope(
            dataset_key=spec.dataset_key,
            title=spec.title,
            description=spec.description,
            schema_version=spec.schema_version,
            semantic_version=spec.semantic_version,
            freshness_mode=spec.freshness_mode,
            scope=scope.as_dict(),
            filters=adapter_payload.get("effective_filters") or normalized_filters,
            grain=str(adapter_payload.get("grain") or spec.grain),
            dimensions=list(adapter_payload.get("dimensions") or spec.dimensions),
            measures=list(adapter_payload.get("measures") or spec.measures),
            rows=list(adapter_payload.get("rows") or []),
            totals=dict(adapter_payload.get("totals") or {}),
            warnings=list(adapter_payload.get("warnings") or []),
            lineage=lineage,
            render_hints=spec.render_hints,
            export_capabilities=spec.export_capabilities,
        )
        completed_at = timezone.now()
        run.status = RunStatus.SUCCEEDED
        run.completed_at = completed_at
        run.duration_ms = max(int((completed_at - started_at).total_seconds() * 1000), 0)
        run.row_count = len(envelope.get("rows") or [])
        run.warnings_json = envelope.get("warnings") or []
        run.source_summary_json = adapter_payload.get("source_summary") or {}
        run.lineage_json = envelope.get("lineage") or {}
        run.result_hash = _result_hash({"rows": envelope.get("rows"), "totals": envelope.get("totals")})
        run.save(
            update_fields=[
                "status",
                "completed_at",
                "duration_ms",
                "row_count",
                "warnings_json",
                "source_summary_json",
                "lineage_json",
                "result_hash",
                "updated_at",
            ]
        )
        return envelope, run
    except Exception as exc:  # pragma: no cover - guarded by API tests
        completed_at = timezone.now()
        run.status = RunStatus.FAILED
        run.completed_at = completed_at
        run.duration_ms = max(int((completed_at - started_at).total_seconds() * 1000), 0)
        run.error_detail = str(exc)
        run.save(update_fields=["status", "completed_at", "duration_ms", "error_detail", "updated_at"])
        if isinstance(exc, (ReportingValidationError, DatasetScopeError)):
            raise
        raise DatasetExecutionError(str(exc)) from exc
