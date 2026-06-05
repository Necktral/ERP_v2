from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.kernels.reporting import execution
from apps.kernels.reporting.domain_adapters import utils as adapter_utils
from apps.kernels.reporting.enums import FreshnessMode, MaterializationPolicy, RunStatus, ScopeLevel, SnapshotStatus
from apps.kernels.reporting.exceptions import (
    DatasetExecutionError,
    DatasetPermissionDenied,
    DatasetScopeError,
    ReportingValidationError,
)
from apps.kernels.reporting.models import ReportRun, ReportSnapshot
from apps.kernels.reporting.registry import DatasetSpec
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _request(*, company: OrgUnit | None, branch: OrgUnit | None, perms: list[str] | None = None):
    token = str(timezone.now().timestamp()).replace(".", "_")
    user = User.objects.create_user(username=f"report_{token}", email=f"report_{token}@test.local", password="x")
    return SimpleNamespace(
        user=user,
        company=company,
        branch=branch,
        reporting_effective_permissions=perms,
    )


def test_reporting_filter_normalization_rejects_ambiguous_or_invalid_inputs() -> None:
    normalized = execution.normalize_filters_for_dataset(
        dataset_key="billing.summary.period",
        filters={"date_from": "2026-03-01"},
    )
    assert normalized["date_from"] == date(2026, 3, 1)

    with pytest.raises(ReportingValidationError, match="Filtros no permitidos"):
        execution.normalize_filters_for_dataset(
            dataset_key="billing.summary.period",
            filters={"date_from": "2026-03-01", "extra": "x"},
        )

    with pytest.raises(ReportingValidationError, match="fecha ISO"):
        execution.normalize_filters_for_dataset(dataset_key="billing.summary.period", filters={"date_from": "03/01/2026"})

    with pytest.raises(ReportingValidationError, match="year y month"):
        execution.normalize_filters_for_dataset(dataset_key="accounting.trial_balance.period", filters={"year": 2026})

    with pytest.raises(ReportingValidationError, match="date_from debe"):
        execution.normalize_filters_for_dataset(
            dataset_key="billing.summary.period",
            filters={"date_from": "2026-03-02", "date_to": "2026-03-01"},
        )

    with pytest.raises(ReportingValidationError, match="no puede combinarse"):
        execution.normalize_filters_for_dataset(
            dataset_key="accounting.balance_sheet.as_of",
            filters={"as_of": "2026-03-31", "date_to": "2026-03-31"},
        )


def test_reporting_adapter_date_utils_make_default_ranges_and_reject_bad_values() -> None:
    assert adapter_utils.coerce_filter_date(None, field_name="date_from") is None
    assert adapter_utils.coerce_filter_date(datetime(2026, 3, 1, 8, 0), field_name="date_from") == date(2026, 3, 1)
    assert adapter_utils.coerce_filter_date(date(2026, 3, 2), field_name="date_to") == date(2026, 3, 2)
    assert adapter_utils.coerce_filter_date("", field_name="date_to") is None
    assert adapter_utils.resolve_date_range({"date_from": "2026-03-01"}) == (date(2026, 3, 1), date(2026, 3, 1))
    assert adapter_utils.resolve_date_range({"date_to": "2026-03-02"}) == (date(2026, 3, 2), date(2026, 3, 2))

    with pytest.raises(DatasetExecutionError, match="YYYY-MM-DD"):
        adapter_utils.coerce_filter_date("bad-date", field_name="date_from")
    with pytest.raises(DatasetExecutionError, match="inválido"):
        adapter_utils.coerce_filter_date(object(), field_name="date_from")


@pytest.mark.django_db
def test_execute_dataset_enforces_scope_permissions_and_persists_snapshot() -> None:
    company, branch = _mk_scope()
    filters = {"date_from": "2026-03-01", "date_to": "2026-03-01"}

    with pytest.raises(DatasetScopeError, match="branch requerido"):
        execution.execute_dataset(
            dataset_key="billing.summary.period",
            request=_request(company=company, branch=None, perms=["report.dataset.read", "billing.report.read"]),
            filters=filters,
        )

    with pytest.raises(DatasetPermissionDenied, match="billing.report.read"):
        execution.execute_dataset(
            dataset_key="billing.summary.period",
            request=_request(company=company, branch=branch, perms=["report.dataset.read"]),
            filters=filters,
        )

    envelope, run = execution.execute_dataset(
        dataset_key="billing.summary.period",
        request=_request(company=company, branch=branch, perms=["report.dataset.read", "billing.report.read"]),
        filters=filters,
        consumer_type="API",
        consumer_ref="diagnostic",
    )
    assert run.status == RunStatus.SUCCEEDED
    assert run.consumer_ref == "diagnostic"
    assert run.source_summary_json["materialization"] == "CACHE_REFRESH"
    assert envelope["dataset_key"] == "billing.summary.period"
    assert ReportSnapshot.objects.filter(dataset_key="billing.summary.period", status=SnapshotStatus.ACTIVE).count() == 1

    cached, cached_run = execution.execute_dataset(
        dataset_key="billing.summary.period",
        request=_request(company=company, branch=branch, perms=["report.dataset.read", "billing.report.read"]),
        filters=filters,
    )
    assert cached_run.status == RunStatus.SUCCEEDED
    assert cached_run.source_summary_json["materialization"] == "SNAPSHOT_HIT"
    assert cached["dataset_key"] == envelope["dataset_key"]

    snapshot = ReportSnapshot.objects.get(dataset_key="billing.summary.period", status=SnapshotStatus.ACTIVE)
    snapshot.fresh_until = timezone.now() - timedelta(minutes=1)
    snapshot.save(update_fields=["fresh_until", "updated_at"])
    rebuilt, rebuilt_run = execution.execute_dataset(
        dataset_key="billing.summary.period",
        request=_request(company=company, branch=branch, perms=["report.dataset.read", "billing.report.read"]),
        filters=filters,
    )
    assert rebuilt_run.source_summary_json["materialization"] == "CACHE_REFRESH"
    snapshot.refresh_from_db()
    assert snapshot.status == SnapshotStatus.ACTIVE
    assert rebuilt["dataset_key"] == "billing.summary.period"


@pytest.mark.django_db
def test_execute_dataset_records_failed_run_for_unknown_domain_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    company, branch = _mk_scope()
    spec = DatasetSpec(
        dataset_key="diagnostic.unknown.owner",
        title="Unknown",
        description="Unknown owner probe",
        domain_owner="UNKNOWN",
        scope_level=ScopeLevel.BRANCH,
        kernel_permissions=("report.dataset.read",),
        domain_permissions=(),
        filters_schema={},
        dimensions=[],
        measures=[],
        grain="none",
        freshness_mode=FreshnessMode.LIVE_ONLY,
        materialization_policy=MaterializationPolicy.LIVE_ONLY,
        export_capabilities=[],
        render_hints={},
        drill_metadata={},
        quality_policy={"allow_empty_rows": True},
    )
    monkeypatch.setattr(execution, "get_dataset_spec", lambda dataset_key: spec)

    with pytest.raises(DatasetExecutionError, match="domain_owner=UNKNOWN"):
        execution.execute_dataset(
            dataset_key=spec.dataset_key,
            request=_request(company=company, branch=branch, perms=["report.dataset.read"]),
            filters={},
        )

    failed = ReportRun.objects.get(dataset_key=spec.dataset_key)
    assert failed.status == RunStatus.FAILED
    assert "domain_owner=UNKNOWN" in failed.error_detail
