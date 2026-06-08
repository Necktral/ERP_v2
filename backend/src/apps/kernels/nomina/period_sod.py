"""SoD (maker-checker) para la aprobación del período de planilla.

Aprobar un período de nómina (que luego genera asiento contable y pagos) es sensible:
quien lo arma/revisa no debe ser quien lo aprueba. Reusa `apps.modulos.iam.approvals`.

Flujo: `request_period_approval` (maker) -> `approve_period` (checker, valida approver
!= maker + permiso `nomina.period.approve`).
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.approvals import approve as _approve_request
from apps.modulos.iam.approvals import mark_executed, request_approval
from apps.modulos.iam.models import ApprovalRequest

from .models import PayrollPeriod, PeriodStatus

NOMINA_PERIOD_APPROVE_ACTION = "NOMINA_PERIOD_APPROVE"
NOMINA_PERIOD_APPROVE_PERMISSION = "nomina.period.approve"

_APPROVABLE_STATES = (PeriodStatus.DRAFT, PeriodStatus.IN_REVIEW)


def request_period_approval(
    *, request, actor, period: PayrollPeriod, reason: str = "", idempotency_key: str = ""
) -> ApprovalRequest:
    """Maker: solicita la aprobación del período."""
    if period.status not in _APPROVABLE_STATES:
        raise ValueError(f"El período no está en estado aprobable: {period.status}")
    return request_approval(
        company=period.company,
        requested_by=actor,
        action_type=NOMINA_PERIOD_APPROVE_ACTION,
        required_permission=NOMINA_PERIOD_APPROVE_PERMISSION,
        subject_type="PAYROLL_PERIOD",
        subject_id=str(period.id),
        reason=reason or "NOMINA_PERIOD_APPROVE",
        payload={"period_id": int(period.id), "reason": reason or ""},
        idempotency_key=idempotency_key,
        request=request,
    )


def approve_period(*, request, approver, approval: ApprovalRequest) -> PayrollPeriod:
    """Checker: aprueba (valida SoD + permiso) y marca el período APPROVED."""
    approval = _approve_request(approval=approval, approver=approver, request=request)
    period = PayrollPeriod.objects.get(id=int((approval.payload or {})["period_id"]))
    with transaction.atomic():
        period.status = PeriodStatus.APPROVED
        period.approved_by = approver
        period.approved_at = timezone.now()
        period.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        write_event(
            request=request,
            module="NOMINA",
            event_type="NOMINA_PERIOD_APPROVED",
            reason_code="NOMINA_OK",
            actor_user=approver,
            subject_type="PAYROLL_PERIOD",
            subject_id=str(period.id),
            metadata={"period_id": period.id},
        )
        # Asiento del costo de planilla (rollup + outbox + link a contabilidad, best-effort).
        from .accounting_link import post_payroll_period_to_accounting

        post_payroll_period_to_accounting(request=request, actor=approver, period=period)
        mark_executed(approval=approval, actor=approver, request=request)
    return period
