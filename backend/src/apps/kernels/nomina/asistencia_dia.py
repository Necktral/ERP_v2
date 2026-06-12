"""Asistencia del día — la pantalla simple del mandador/capataz (PC y cel).

El mandador ve al personal de la empresa y marca por trabajador:
PRESENTE / AUSENTE / ENFERMO / MEDIO_DIA / ACCIDENTADO.

NO es un canal paralelo: cada marca escribe en las piezas FORMALES de campo
(FieldRollCall/Line + FieldWorkerEvent) que la consolidación de 3 fuentes ya
cruza con el biométrico y los reportes de cuadrilla. Corregir una marca
reemplaza la línea y los eventos hechos por esta vía (source=asistencia_app);
lo que registró el capataz por su canal no se toca.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.hr.models import Employee, EmploymentAssignment
from apps.modulos.iam.models import OrgUnit

from .models import (
    FieldRollCall,
    FieldRollCallLine,
    FieldRollCallLineStatus,
    FieldWorkDay,
    FieldWorkerEvent,
    FieldWorkerEventType,
)
from .services import _validate_work_day_mutable, open_field_work_day, record_worker_event

APP_SOURCE = "asistencia_app"

# Estados de la pantalla (lo que pidió el dueño) y su efecto formal
ESTADO_PRESENTE = "PRESENTE"
ESTADO_AUSENTE = "AUSENTE"
ESTADO_ENFERMO = "ENFERMO"
ESTADO_MEDIO_DIA = "MEDIO_DIA"
ESTADO_ACCIDENTADO = "ACCIDENTADO"
ESTADO_SIN_MARCAR = "SIN_MARCAR"

ESTADOS_VALIDOS = {
    ESTADO_PRESENTE,
    ESTADO_AUSENTE,
    ESTADO_ENFERMO,
    ESTADO_MEDIO_DIA,
    ESTADO_ACCIDENTADO,
}

# estado → (rollcall_status, absence_reason, event_type, details)
_EFECTOS = {
    ESTADO_PRESENTE: (FieldRollCallLineStatus.PRESENT, "", None, ""),
    ESTADO_AUSENTE: (FieldRollCallLineStatus.ABSENT, "", None, ""),
    ESTADO_ENFERMO: (FieldRollCallLineStatus.ABSENT, "SICK", FieldWorkerEventType.SICK, "Se enfermó (marcado en asistencia)"),
    ESTADO_MEDIO_DIA: (FieldRollCallLineStatus.PRESENT, "", FieldWorkerEventType.LEFT_EARLY, "Trabajó medio día (marcado en asistencia)"),
    ESTADO_ACCIDENTADO: (FieldRollCallLineStatus.PRESENT, "", FieldWorkerEventType.ACCIDENT, "Accidente de trabajo (marcado en asistencia)"),
}


def _resolve_branch(request) -> OrgUnit | None:
    branch = getattr(request, "branch", None)
    if branch is not None:
        return branch
    company = request.company
    branches = list(
        OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH, is_active=True)[:2]
    )
    # Una sola sucursal: se usa sin pedir contexto. Varias: el día queda a nivel empresa.
    return branches[0] if len(branches) == 1 else None


def ensure_work_day(*, request, actor, work_date) -> FieldWorkDay:
    """Devuelve (o abre) el día de campo de hoy para la empresa/sucursal del contexto."""
    company: OrgUnit = request.company
    branch = _resolve_branch(request)
    lookup = {"company": company, "work_date": work_date}
    lookup["branch"] = branch if branch is not None else None
    existing = FieldWorkDay.objects.filter(**lookup).first()
    if existing:
        return existing
    # Sin período de nómina: nómina lo liga al consolidar (payroll_period es opcional).
    return open_field_work_day(
        request=request, actor=actor, company=company, branch=branch, work_date=work_date
    )


def _estado_actual(line: FieldRollCallLine | None, event_types: set[str]) -> str:
    if FieldWorkerEventType.SICK in event_types:
        return ESTADO_ENFERMO
    if FieldWorkerEventType.ACCIDENT in event_types:
        return ESTADO_ACCIDENTADO
    if FieldWorkerEventType.LEFT_EARLY in event_types:
        return ESTADO_MEDIO_DIA
    if line is None:
        return ESTADO_SIN_MARCAR
    if line.status == FieldRollCallLineStatus.PRESENT:
        return ESTADO_PRESENTE
    if line.status == FieldRollCallLineStatus.ABSENT:
        return ESTADO_AUSENTE
    return ESTADO_SIN_MARCAR


def personal_del_dia(*, request, work_day: FieldWorkDay | None) -> list[dict]:
    """Personal activo de la empresa con su estado marcado de hoy y su perfil (solo lectura).

    work_day None = aún nadie marcó hoy: todos salen SIN_MARCAR (el día se abre
    con la primera marca, no con la consulta).
    """
    company = request.company
    lines: dict[int, FieldRollCallLine] = {}
    events_by_emp: dict[int, set[str]] = {}
    constancia_by_emp: dict[int, bool] = {}
    if work_day is not None:
        lines = {
            ln.employee_id: ln
            for ln in FieldRollCallLine.objects.filter(rollcall__work_day=work_day)
        }
        for ev in FieldWorkerEvent.objects.filter(work_day=work_day):
            events_by_emp.setdefault(ev.employee_id, set()).add(ev.event_type)
            if ev.event_type == FieldWorkerEventType.SICK and isinstance(ev.metadata, dict):
                if "constancia_medica" in ev.metadata:
                    constancia_by_emp[ev.employee_id] = bool(ev.metadata["constancia_medica"])

    assignments = {
        a.employee_id: a
        for a in EmploymentAssignment.objects.filter(
            employee__company=company, is_active=True
        ).select_related("position").order_by("started_at")
    }

    from django.db.models import Exists, OuterRef

    from apps.modulos.hr.models import EmployeePhoto

    out = []
    employees = (
        Employee.objects.filter(company=company, is_active=True)
        .annotate(has_photo=Exists(EmployeePhoto.objects.filter(employee_id=OuterRef("pk"))))
        .order_by("first_name", "last_name")
    )
    for e in employees:
        asg = assignments.get(e.id)
        out.append(
            {
                "employee_id": e.id,
                "employee_code": e.employee_code or "",
                "first_name": e.first_name,
                "last_name": e.last_name or "",
                "phone": e.phone or "",
                "position_name": asg.position.name if asg and asg.position_id else "",
                "has_photo": bool(e.has_photo),
                "estado": _estado_actual(lines.get(e.id), events_by_emp.get(e.id, set())),
                # Solo aplica al estado ENFERMO: con/sin constancia médica certificada.
                "constancia_medica": constancia_by_emp.get(e.id),
            }
        )
    return out


@transaction.atomic
def marcar_asistencia(
    *,
    request,
    actor,
    work_day: FieldWorkDay,
    employee: Employee,
    estado: str,
    constancia_medica: bool = False,
) -> str:
    """Marca (o corrige) el estado del trabajador para el día. Idempotente por estado."""
    if estado not in ESTADOS_VALIDOS:
        raise ValueError("ESTADO_INVALIDO")
    _validate_work_day_mutable(work_day)
    if employee.company_id != work_day.company_id:
        raise ValueError("EMPLOYEE_OTHER_COMPANY")

    rollcall_status, absence_reason, event_type, details = _EFECTOS[estado]

    rollcall, _ = FieldRollCall.objects.get_or_create(
        work_day=work_day, defaults={"submitted_by": actor, "notes": "Asistencia del día (app)"}
    )
    FieldRollCallLine.objects.update_or_create(
        rollcall=rollcall,
        employee=employee,
        defaults={"status": rollcall_status, "absence_reason": absence_reason},
    )

    # Corrección: se reemplazan SOLO los eventos creados por esta pantalla.
    FieldWorkerEvent.objects.filter(
        work_day=work_day, employee=employee, metadata__source=APP_SOURCE
    ).delete()
    if event_type is not None:
        metadata: dict[str, object] = {"source": APP_SOURCE, "estado": estado}
        if estado == ESTADO_MEDIO_DIA:
            # "Trabajó medio día" PAGA medio día: la consolidación lee este
            # day_value cuando no hay reporte de cuadrilla del capataz.
            metadata["day_value"] = "0.5"
        elif estado == ESTADO_ACCIDENTADO:
            # Regla del dueño: el accidente fue EN el trabajo → se le pone el día.
            metadata["day_value"] = "1.0"
        elif estado == ESTADO_ENFERMO:
            # Regla del dueño: enfermo se paga SOLO con constancia médica certificada.
            metadata["constancia_medica"] = bool(constancia_medica)
            metadata["day_value"] = "1.0" if constancia_medica else "0.0"
        record_worker_event(
            request=request,
            actor=actor,
            work_day=work_day,
            employee=employee,
            event_type=event_type,
            details=details,
            metadata=metadata,
        )

    write_event(
        request=request,
        module="NOMINA",
        event_type="NOMINA_ASISTENCIA_MARCADA",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={
            "work_day_id": work_day.id,
            "work_date": str(work_day.work_date),
            "estado": estado,
            **({"constancia_medica": bool(constancia_medica)} if estado == ESTADO_ENFERMO else {}),
        },
    )
    return estado


def hoy_local():
    return timezone.localdate()
