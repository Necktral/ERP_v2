"""PR-9: auditoría de CEC (cierra audit=0).

CEC gobierna el cierre pero no emitía auditoría: ahora cada transición de CloseRun
(`CEC_CLOSE_RUN_ADVANCED`, incl. reapertura) y cada excepción de cierre detectada
(`CEC_EXCEPTION_RAISED`) quedan en el audit trail append-only (invariante #4).
"""
from __future__ import annotations

import uuid

import pytest

from apps.modulos.audit.models import AuditEvent
from apps.modulos.cec.models import CECException, CloseRun
from apps.modulos.cec.services import _register_exception, advance_close_run_state
from apps.modulos.iam.models import OrgUnit


def _scope():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    return company, branch


def _close_run(company, branch, status=CloseRun.Status.CREATED):
    return CloseRun.objects.create(
        company=company, branch=branch, run_type=CloseRun.RunType.DAILY, status=status,
    )


@pytest.mark.django_db
def test_advance_close_run_state_emits_audit():
    company, branch = _scope()
    run = _close_run(company, branch)

    advance_close_run_state(run=run, target_status=CloseRun.Status.GATHERED)

    ev = AuditEvent.objects.filter(event_type="CEC_CLOSE_RUN_ADVANCED", subject_id=str(run.run_id)).first()
    assert ev is not None
    assert ev.subject_type == "CLOSE_RUN"
    assert ev.before_snapshot.get("status") == CloseRun.Status.CREATED
    assert ev.after_snapshot.get("status") == CloseRun.Status.GATHERED


@pytest.mark.django_db
def test_register_exception_emits_audit():
    company, branch = _scope()
    run = _close_run(company, branch)

    created, was_created = _register_exception(
        run=run,
        code="TEST_GATE",
        severity=CECException.Severity.MEDIUM,
        strict=True,
        related_object_type="BILLING_DOC",
        related_object_id="123",
        details_json={"reason": "test"},
    )
    assert was_created is True

    ev = AuditEvent.objects.filter(
        event_type="CEC_EXCEPTION_RAISED", subject_id=str(created.exception_id)
    ).first()
    assert ev is not None
    assert ev.subject_type == "CEC_EXCEPTION"
    assert ev.metadata.get("code") == "TEST_GATE"


@pytest.mark.django_db
def test_reopen_transition_is_audited():
    # La reapertura (REOPENED_EXCEPTION) queda con cadena de auditoría (anti-patrón #9).
    company, branch = _scope()
    run = _close_run(company, branch, status=CloseRun.Status.DELIVERED)

    advance_close_run_state(run=run, target_status=CloseRun.Status.REOPENED_EXCEPTION)

    ev = (
        AuditEvent.objects.filter(event_type="CEC_CLOSE_RUN_ADVANCED", subject_id=str(run.run_id))
        .order_by("-id")
        .first()
    )
    assert ev is not None
    assert ev.after_snapshot.get("status") == CloseRun.Status.REOPENED_EXCEPTION
