"""Tests del helper estándar de auditoría de servicio."""
from __future__ import annotations

import uuid

import pytest

from apps.modulos.audit.models import AuditEvent
from apps.modulos.audit.service_audit import ServiceAuditRequest, build_audit_request, emit_service_event
from apps.modulos.iam.models import OrgUnit


def _mk_company():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    return OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)


def test_build_audit_request_synthetic_and_passthrough():
    class _Real:
        pass

    real = _Real()
    assert build_audit_request(company=None, base_request=real) is real
    synthetic = build_audit_request(company="C", branch="B", request_id="r")
    assert isinstance(synthetic, ServiceAuditRequest)
    assert synthetic.company == "C" and synthetic.request_id == "r"
    assert synthetic.META == {}


@pytest.mark.django_db
def test_emit_service_event_writes_audit_with_partition():
    company = _mk_company()
    ev = emit_service_event(
        company=company,
        module="ORG",
        event_type="ORG_COMPANY_CREATED",
        reason_code="ORG_OK",
        subject_type="COMPANY",
        subject_id=str(company.id),
        after_snapshot={"name": company.name},
    )
    assert ev.pk is not None
    assert ev.event_type == "ORG_COMPANY_CREATED"
    assert ev.partition_key == f"COMPANY:{company.id}"
    assert ev.metadata.get("company_id") == str(company.id)
    # Integridad: el evento queda firmado/encadenado por el writer.
    assert ev.event_hash and ev.signature
    assert AuditEvent.objects.filter(pk=ev.pk).exists()
