from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.kernels.payments.models import CashSession
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from tests.helpers.operational_auth import create_operational_api_actor as _client_with_perms


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


@pytest.mark.django_db
def test_cec_execute_success_and_summary_endpoint():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )

    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    now = timezone.now()
    execute_resp = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(days=1)).isoformat(),
            "strict": True,
        },
        format="json",
    )
    assert execute_resp.status_code == 200
    assert execute_resp.data["status"] == "PACKAGED"
    assert execute_resp.data["blocking_exceptions_count"] == 0
    assert len(execute_resp.data["output_manifest_hash"]) == 64

    summary_resp = client.get(f"/api/cec/close-runs/{run_id}/summary/")
    assert summary_resp.status_code == 200
    assert summary_resp.data["status"] == "PACKAGED"
    assert summary_resp.data["consistency_score"] == 100
    assert isinstance(summary_resp.data["summary"], dict)
    assert isinstance(summary_resp.data["exceptions"], list)


@pytest.mark.django_db
def test_cec_execute_blocked_when_cash_difference_exists():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update", "cec.evidence.create"],
    )

    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    now = timezone.now()
    CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=user,
        closed_by=user,
        status=CashSession.Status.CLOSED,
        opened_at=now - timedelta(hours=4),
        closed_at=now - timedelta(hours=1),
        opening_amount=Decimal("100.00"),
        expected_amount=Decimal("180.00"),
        counted_amount=Decimal("170.00"),
        difference_amount=Decimal("-10.00"),
    )

    execute_resp = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(days=1)).isoformat(),
            "strict": True,
        },
        format="json",
    )
    assert execute_resp.status_code == 200
    assert execute_resp.data["status"] == "REOPENED_EXCEPTION"
    assert execute_resp.data["blocking_exceptions_count"] >= 1

    outbox_types = set(
        OutboxEvent.objects.filter(source_module="CEC").values_list("event_type", flat=True)
    )
    assert "CloseRunExecuted" in outbox_types
    assert "CloseRunBlocked" in outbox_types


@pytest.mark.django_db
def test_cec_execute_with_strict_false_still_blocks_cash_difference():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )

    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    now = timezone.now()
    CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=user,
        closed_by=user,
        status=CashSession.Status.CLOSED,
        opened_at=now - timedelta(hours=4),
        closed_at=now - timedelta(hours=1),
        opening_amount=Decimal("100.00"),
        expected_amount=Decimal("180.00"),
        counted_amount=Decimal("170.00"),
        difference_amount=Decimal("-10.00"),
    )

    execute_resp = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(days=1)).isoformat(),
            "strict": False,
        },
        format="json",
    )
    assert execute_resp.status_code == 200
    assert execute_resp.data["status"] == "REOPENED_EXCEPTION"
    assert execute_resp.data["blocking_exceptions_count"] >= 1


@pytest.mark.django_db
def test_cec_advance_rejects_invalid_transition_with_409():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.create", "cec.close_run.update"],
    )
    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    invalid = client.post(
        f"/api/cec/close-runs/{run_id}/advance/",
        {"status": "PACKAGED"},
        format="json",
    )
    assert invalid.status_code == 409
