"""SoD (maker-checker) para la aprobación de asistencia de campo.

La aprobación de la consolidación diaria —que luego alimenta la planilla— es una
operación sensible (invariante #6): el jefe de área que aprueba debe ser DISTINTO del
capataz/planillero que capturó y consolidó. Reutiliza la primitiva
`apps.modulos.iam.approvals` y conserva el servicio crudo `approve_field_attendance`
para orquestación interna/sistema (igual que `payments.sod` conserva sus funciones crudas).

Flujo: `request_field_attendance_approval` (maker) -> `approve_field_attendance_with_sod`
(checker, valida approver != maker + permiso `nomina.field.approve`).
"""
from __future__ import annotations

from apps.modulos.iam.approvals import approve as _approve_request
from apps.modulos.iam.approvals import mark_executed, request_approval
from apps.modulos.iam.models import ApprovalRequest

from .models import (
    FieldAttendanceConsolidation,
    FieldAttendanceConsolidationStatus,
    FieldWorkDay,
    FieldWorkDayStatus,
)
from .services import FieldAttendanceError, approve_field_attendance

FIELD_ATTENDANCE_APPROVE_ACTION = "FIELD_ATTENDANCE_APPROVE"
FIELD_ATTENDANCE_APPROVE_PERMISSION = "nomina.field.approve"

_BLOCKING_STATUSES = (
    FieldAttendanceConsolidationStatus.CONFLICT,
    FieldAttendanceConsolidationStatus.BLOCKED,
)
_ELIGIBLE_STATUSES = (
    FieldAttendanceConsolidationStatus.OK,
    FieldAttendanceConsolidationStatus.WARNING,
)


def request_field_attendance_approval(
    *,
    request,
    actor,
    work_day: FieldWorkDay,
    reason: str = "",
    idempotency_key: str = "",
) -> ApprovalRequest:
    """Maker: solicita la aprobación de la consolidación del día de campo.

    Valida en caliente que el día sea aprobable (consolidado, sin conflictos bloqueantes)
    para dar feedback temprano; la validación SoD real ocurre en la aprobación.
    """
    if work_day.status == FieldWorkDayStatus.LOCKED:
        raise FieldAttendanceError("invalid_state", "El dia de campo bloqueado no admite aprobacion.")
    if work_day.status == FieldWorkDayStatus.APPROVED:
        raise FieldAttendanceError("invalid_state", "El dia de campo ya esta aprobado.")

    blocked = FieldAttendanceConsolidation.objects.filter(work_day=work_day, status__in=_BLOCKING_STATUSES)
    if blocked.exists():
        raise FieldAttendanceError(
            "blocked_conflict",
            "No se puede solicitar aprobacion con conflictos o bloqueos pendientes.",
            context={"work_day_id": work_day.id, "blocked_count": blocked.count()},
        )
    if not FieldAttendanceConsolidation.objects.filter(work_day=work_day, status__in=_ELIGIBLE_STATUSES).exists():
        raise FieldAttendanceError("invalid_state", "No hay consolidaciones listas para aprobar.")

    return request_approval(
        company=work_day.company,
        branch=work_day.branch,
        requested_by=actor,
        action_type=FIELD_ATTENDANCE_APPROVE_ACTION,
        required_permission=FIELD_ATTENDANCE_APPROVE_PERMISSION,
        subject_type="FIELD_WORK_DAY",
        subject_id=str(work_day.id),
        reason=reason or "FIELD_ATTENDANCE_APPROVE",
        payload={"work_day_id": int(work_day.id), "reason": reason or ""},
        idempotency_key=idempotency_key,
        request=request,
    )


def approve_field_attendance_with_sod(
    *, request, approver, approval: ApprovalRequest
) -> list[FieldAttendanceConsolidation]:
    """Checker: aprueba (valida SoD approver != maker + permiso) y ejecuta la aprobacion."""
    approval = _approve_request(approval=approval, approver=approver, request=request)
    payload = approval.payload or {}
    work_day = FieldWorkDay.objects.get(id=int(payload["work_day_id"]))
    result = approve_field_attendance(request=request, actor=approver, work_day=work_day)
    mark_executed(approval=approval, actor=approver, request=request)
    return result
