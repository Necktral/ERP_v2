"""Servicios SoD / maker-checker (invariante #6, anti-patrón #10).

Una operación sensible se solicita (maker) y debe aprobarla un segundo usuario
distinto (checker) que posea el permiso requerido en el scope. Todo el ciclo es
auditable (`IAM_APPROVAL_*`). Reusa `rbac.selectors.get_effective_permissions_for_scope`.
"""
from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.common.domain_errors import DomainError
from apps.modulos.rbac.selectors import get_effective_permissions_for_scope

from .models import ApprovalRequest, OrgUnit


class ApprovalStateError(DomainError):
    default_code = "APPROVAL_INVALID_STATE"


class SelfApprovalError(DomainError):
    default_code = "SOD_SELF_APPROVAL"


class ApproverNotAuthorizedError(DomainError):
    default_code = "APPROVER_NOT_AUTHORIZED"


class _ApprovalAuditRequest:
    """Request sintético para encadenar auditoría por company sin HTTP."""

    def __init__(self, *, company, branch=None) -> None:
        self.company = company
        self.branch = branch
        self.META: dict[str, Any] = {}
        self.path = ""
        self.method = ""
        self.request_id = ""


def _audit_request(*, request, company, branch=None):
    if request is not None:
        return request
    return _ApprovalAuditRequest(company=company, branch=branch)


def _approver_has_permission(*, approver, company, branch, required_permission: str) -> bool:
    if getattr(approver, "is_superuser", False):
        return True
    perms = get_effective_permissions_for_scope(approver, company=company, branch=branch)
    return required_permission in perms or "*" in perms


def _snapshot(approval: ApprovalRequest) -> dict[str, Any]:
    return {
        "request_id": str(approval.request_id),
        "action_type": approval.action_type,
        "status": approval.status,
        "required_permission": approval.required_permission,
        "requested_by_id": approval.requested_by_id,
        "decided_by_id": approval.decided_by_id,
    }


@transaction.atomic
def request_approval(
    *,
    company: OrgUnit,
    requested_by,
    action_type: str,
    required_permission: str,
    branch: OrgUnit | None = None,
    subject_type: str = "",
    subject_id: str = "",
    reason: str = "",
    payload: dict | None = None,
    idempotency_key: str = "",
    request=None,
) -> ApprovalRequest:
    key = str(idempotency_key or "").strip()
    if key:
        existing = ApprovalRequest.objects.filter(company=company, idempotency_key=key).first()
        if existing is not None:
            return existing

    approval = ApprovalRequest.objects.create(
        company=company,
        branch=branch,
        action_type=action_type,
        subject_type=subject_type or "",
        subject_id=str(subject_id or ""),
        required_permission=required_permission,
        requested_by=requested_by,
        reason=reason or "",
        payload=payload or {},
        idempotency_key=key,
        status=ApprovalRequest.Status.PENDING,
    )
    write_event(
        request=_audit_request(request=request, company=company, branch=branch),
        module="IAM",
        event_type="IAM_APPROVAL_REQUESTED",
        reason_code="IAM_OK",
        actor_user=requested_by,
        subject_type="APPROVAL_REQUEST",
        subject_id=str(approval.request_id),
        after_snapshot=_snapshot(approval),
        metadata={"company_id": str(company.id), "action_type": action_type},
    )
    return approval


def _decide(
    *, approval: ApprovalRequest, approver, target_status: str, note: str, request, event_type: str
) -> ApprovalRequest:
    if approval.status != ApprovalRequest.Status.PENDING:
        raise ApprovalStateError(
            "La solicitud no está pendiente.",
            code="APPROVAL_INVALID_STATE",
            context={"status": approval.status},
        )
    if approver is not None and approver.id == approval.requested_by_id:
        raise SelfApprovalError("El solicitante no puede decidir su propia solicitud (SoD).")

    scope_company = approval.company
    scope_branch = approval.branch
    if not _approver_has_permission(
        approver=approver, company=scope_company, branch=scope_branch, required_permission=approval.required_permission
    ):
        raise ApproverNotAuthorizedError(
            "El aprobador no posee el permiso requerido en el scope.",
            context={"required_permission": approval.required_permission},
        )

    before = _snapshot(approval)
    approval.status = target_status
    approval.decided_by = approver
    approval.decided_at = timezone.now()
    approval.decision_note = note or ""
    approval.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])

    write_event(
        request=_audit_request(request=request, company=scope_company, branch=scope_branch),
        module="IAM",
        event_type=event_type,
        reason_code="IAM_OK",
        actor_user=approver,
        subject_type="APPROVAL_REQUEST",
        subject_id=str(approval.request_id),
        before_snapshot=before,
        after_snapshot=_snapshot(approval),
        metadata={"company_id": str(scope_company.id), "action_type": approval.action_type},
    )
    return approval


@transaction.atomic
def approve(*, approval: ApprovalRequest, approver, note: str = "", request=None) -> ApprovalRequest:
    approval = ApprovalRequest.objects.select_for_update().get(pk=approval.pk)
    return _decide(
        approval=approval,
        approver=approver,
        target_status=ApprovalRequest.Status.APPROVED,
        note=note,
        request=request,
        event_type="IAM_APPROVAL_APPROVED",
    )


@transaction.atomic
def reject(*, approval: ApprovalRequest, approver, note: str = "", request=None) -> ApprovalRequest:
    approval = ApprovalRequest.objects.select_for_update().get(pk=approval.pk)
    return _decide(
        approval=approval,
        approver=approver,
        target_status=ApprovalRequest.Status.REJECTED,
        note=note,
        request=request,
        event_type="IAM_APPROVAL_REJECTED",
    )


@transaction.atomic
def cancel(*, approval: ApprovalRequest, actor, note: str = "", request=None) -> ApprovalRequest:
    approval = ApprovalRequest.objects.select_for_update().get(pk=approval.pk)
    if approval.status != ApprovalRequest.Status.PENDING:
        raise ApprovalStateError("Solo se puede cancelar una solicitud pendiente.", context={"status": approval.status})
    if actor is not None and actor.id != approval.requested_by_id:
        raise ApproverNotAuthorizedError("Solo el solicitante puede cancelar su solicitud.")

    before = _snapshot(approval)
    approval.status = ApprovalRequest.Status.CANCELLED
    approval.decision_note = note or ""
    approval.save(update_fields=["status", "decision_note", "updated_at"])
    write_event(
        request=_audit_request(request=request, company=approval.company, branch=approval.branch),
        module="IAM",
        event_type="IAM_APPROVAL_CANCELLED",
        reason_code="IAM_OK",
        actor_user=actor,
        subject_type="APPROVAL_REQUEST",
        subject_id=str(approval.request_id),
        before_snapshot=before,
        after_snapshot=_snapshot(approval),
        metadata={"company_id": str(approval.company_id)},
    )
    return approval


@transaction.atomic
def mark_executed(*, approval: ApprovalRequest, actor=None, request=None) -> ApprovalRequest:
    approval = ApprovalRequest.objects.select_for_update().get(pk=approval.pk)
    if not approval.can_transition_to(ApprovalRequest.Status.EXECUTED):
        raise ApprovalStateError(
            "Solo una solicitud aprobada puede marcarse como ejecutada.", context={"status": approval.status}
        )
    before = _snapshot(approval)
    approval.status = ApprovalRequest.Status.EXECUTED
    approval.save(update_fields=["status", "updated_at"])
    write_event(
        request=_audit_request(request=request, company=approval.company, branch=approval.branch),
        module="IAM",
        event_type="IAM_APPROVAL_EXECUTED",
        reason_code="IAM_OK",
        actor_user=actor,
        subject_type="APPROVAL_REQUEST",
        subject_id=str(approval.request_id),
        before_snapshot=before,
        after_snapshot=_snapshot(approval),
        metadata={"company_id": str(approval.company_id)},
    )
    return approval
