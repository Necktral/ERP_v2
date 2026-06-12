"""Servicios de ingesta biométrica.

Flujo: archivo/push → parseo flexible → BiometricCheck idempotente (dedupe_key)
→ matching a Employee (PersonMap o employee_code) → rollup por período a
AttendanceReport(source=BIOMETRIC) para el cruce de 3 controles.

Regla del negocio: la ENTRADA valida el día trabajado; la salida solo es
evidencia (en el campo las distancias hacen que difiera). Por eso el día cuenta
con AL MENOS UN chequeo en la fecha, sin exigir par entrada/salida.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.hr.models import Employee

from ..models import (
    AttendanceReport,
    AttendanceSource,
    AttendanceStatus,
    PayrollPeriod,
    PeriodStatus,
)
from .models_biometric import (
    BiometricCheck,
    BiometricCheckDirection,
    BiometricDevice,
    BiometricImportBatch,
    BiometricPersonMap,
)
from .tabular_reader import TabularReadError, excel_serial_to_datetime, read_tabular_file

MAX_ERRORS_STORED = 20


def _norm(text: str) -> str:
    """minúsculas + sin acentos + sin signos, para comparar encabezados."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch == " ").strip()


# Sinónimos de encabezados que usan los aparatos/exportes comunes
_CODE_HEADERS = {
    "id", "no", "codigo", "cod", "ac no", "acno", "user id", "userid", "enroll number",
    "emp no", "empno", "person id", "personid", "numero", "id de usuario", "id usuario",
    "codigo de trabajador", "codigo trabajador", "employee code",
}
_NAME_HEADERS = {"nombre", "name", "nombres", "first name", "nombre completo", "persona"}
_DATETIME_HEADERS = {
    "fechahora", "fecha hora", "datetime", "date time", "time", "checktime", "check time",
    "hora de registro", "registro", "marcacion", "marca", "fecha y hora",
}
_DATE_HEADERS = {"fecha", "date", "dia"}
_TIME_HEADERS = {"hora", "time", "hora de marca"}
_DIRECTION_HEADERS = {
    "estado", "status", "direction", "in out", "inout", "entrada salida", "tipo",
    "check type", "checktype", "evento", "verificacion", "io", "es",
}

_IN_VALUES = {"in", "entrada", "check in", "checkin", "c in", "cin", "0", "i", "e", "ingreso"}
_OUT_VALUES = {"out", "salida", "check out", "checkout", "c out", "cout", "1", "o", "s", "egreso"}

_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
)
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
_TIME_FORMATS = ("%H:%M:%S", "%H:%M")


@dataclass
class ParsedCheck:
    external_code: str
    checked_at: datetime  # aware
    direction: str
    external_name: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    checks: list[ParsedCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rows_total: int = 0


def _parse_datetime_cell(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    # serial de Excel (numérico)
    try:
        num = float(value)
        if 20000 < num < 80000:  # rango razonable de fechas (1954..2118)
            return excel_serial_to_datetime(num)
    except ValueError:
        pass
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_date_cell(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        num = float(value)
        if 20000 < num < 80000:
            return excel_serial_to_datetime(num)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_time_cell(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        num = float(value)
        if 0 <= num < 1:  # fracción de día de Excel
            return (excel_serial_to_datetime(20000 + num)).time()
    except ValueError:
        pass
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


def _parse_direction(value: str) -> str:
    v = _norm(value)
    if v in _IN_VALUES:
        return BiometricCheckDirection.IN
    if v in _OUT_VALUES:
        return BiometricCheckDirection.OUT
    return BiometricCheckDirection.UNKNOWN


def parse_check_rows(rows: list[list[str]]) -> ParseResult:
    """Detecta columnas por encabezado (flexible) y parsea las filas."""
    result = ParseResult()
    if not rows:
        result.errors.append("Archivo vacío.")
        return result

    header = [_norm(h) for h in rows[0]]
    col = {"code": -1, "name": -1, "dt": -1, "date": -1, "time": -1, "dir": -1}
    for i, h in enumerate(header):
        if col["code"] < 0 and h in _CODE_HEADERS:
            col["code"] = i
        elif col["dt"] < 0 and h in _DATETIME_HEADERS:
            col["dt"] = i
        elif col["date"] < 0 and h in _DATE_HEADERS:
            col["date"] = i
        elif col["time"] < 0 and h in _TIME_HEADERS:
            col["time"] = i
        elif col["dir"] < 0 and h in _DIRECTION_HEADERS:
            col["dir"] = i
        elif col["name"] < 0 and h in _NAME_HEADERS:
            col["name"] = i

    if col["code"] < 0:
        result.errors.append(
            "No se encontró la columna del código de persona (ID/No./Código). "
            f"Encabezados leídos: {rows[0]}"
        )
        return result
    if col["dt"] < 0 and col["date"] < 0:
        result.errors.append(
            "No se encontró la columna de fecha/hora. " f"Encabezados leídos: {rows[0]}"
        )
        return result

    tz = timezone.get_current_timezone()
    for line_no, row in enumerate(rows[1:], start=2):
        result.rows_total += 1

        def cell(idx: int) -> str:
            return row[idx].strip() if 0 <= idx < len(row) else ""

        code = cell(col["code"])
        if not code:
            result.errors.append(f"Fila {line_no}: sin código de persona.")
            continue
        # normalizar códigos numéricos de Excel ("12.0" → "12")
        if code.endswith(".0") and code[:-2].isdigit():
            code = code[:-2]

        dt: datetime | None = None
        if col["dt"] >= 0:
            dt = _parse_datetime_cell(cell(col["dt"]))
        if dt is None and col["date"] >= 0:
            d = _parse_date_cell(cell(col["date"]))
            if d is not None:
                t = _parse_time_cell(cell(col["time"])) if col["time"] >= 0 else None
                dt = datetime.combine(d.date(), t) if t else d
        if dt is None:
            result.errors.append(f"Fila {line_no}: fecha/hora ilegible.")
            continue
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, tz)

        result.checks.append(
            ParsedCheck(
                external_code=code,
                checked_at=dt,
                direction=_parse_direction(cell(col["dir"])) if col["dir"] >= 0 else BiometricCheckDirection.UNKNOWN,
                external_name=cell(col["name"]) if col["name"] >= 0 else "",
                raw={"row": row, "line": line_no},
            )
        )
    return result


def match_employee(*, company, external_code: str) -> Employee | None:
    """PersonMap activo primero; si no, employee_code igual al código del aparato."""
    mapped = (
        BiometricPersonMap.objects.filter(company=company, external_code=external_code, is_active=True)
        .select_related("employee")
        .first()
    )
    if mapped:
        return mapped.employee
    return Employee.objects.filter(company=company, employee_code=external_code).first()


def _dedupe_key(device: BiometricDevice, parsed: ParsedCheck) -> str:
    base = f"{device.id}|{parsed.external_code}|{parsed.checked_at.isoformat()}|{parsed.direction}"
    return hashlib.sha256(base.encode()).hexdigest()


@dataclass(frozen=True)
class IngestResult:
    created: int
    duplicates: int
    unmatched: int


@transaction.atomic
def ingest_checks(
    *, device: BiometricDevice, parsed_checks: list[ParsedCheck], batch: BiometricImportBatch | None = None
) -> IngestResult:
    """Inserta chequeos de forma idempotente (reimportar/reenviar no duplica)."""
    created = duplicates = unmatched = 0
    company = device.company
    match_cache: dict[str, Employee | None] = {}

    for p in parsed_checks:
        key = _dedupe_key(device, p)
        if BiometricCheck.objects.filter(dedupe_key=key).exists():
            duplicates += 1
            continue
        if p.external_code not in match_cache:
            match_cache[p.external_code] = match_employee(company=company, external_code=p.external_code)
        employee = match_cache[p.external_code]
        if employee is None:
            unmatched += 1
        BiometricCheck.objects.create(
            device=device,
            company=company,
            employee=employee,
            external_code=p.external_code,
            external_name=p.external_name,
            direction=p.direction,
            checked_at=p.checked_at,
            work_date=timezone.localtime(p.checked_at).date(),
            import_batch=batch,
            raw=p.raw,
            dedupe_key=key,
        )
        created += 1
    return IngestResult(created=created, duplicates=duplicates, unmatched=unmatched)


def import_checks_file(
    *, device: BiometricDevice, file_name: str, content: bytes, request=None, actor=None
) -> BiometricImportBatch:
    """Importa el archivo exportado por el aparato (xlsx/csv). Idempotente."""
    try:
        rows = read_tabular_file(file_name, content)
    except TabularReadError:
        raise
    parse = parse_check_rows(rows)

    with transaction.atomic():
        batch = BiometricImportBatch.objects.create(
            company=device.company,
            device=device,
            file_name=file_name or "",
            imported_by=actor,
        )
        result = ingest_checks(device=device, parsed_checks=parse.checks, batch=batch)
        batch.rows_total = parse.rows_total
        batch.created_count = result.created
        batch.duplicate_count = result.duplicates
        batch.unmatched_count = result.unmatched
        batch.error_count = len(parse.errors)
        batch.errors = parse.errors[:MAX_ERRORS_STORED]
        batch.save(
            update_fields=[
                "rows_total", "created_count", "duplicate_count", "unmatched_count", "error_count", "errors",
            ]
        )

    write_event(
        request=request,
        module="NOMINA",
        event_type="NOMINA_BIOMETRIC_IMPORTED",
        reason_code="OK",
        actor_user=actor,
        subject_type="DEVICE",
        subject_id=str(device.id),
        metadata={
            "batch_id": batch.id,
            "file_name": batch.file_name,
            "rows_total": batch.rows_total,
            "created": batch.created_count,
            "duplicates": batch.duplicate_count,
            "unmatched": batch.unmatched_count,
            "errors": batch.error_count,
        },
    )
    return batch


@transaction.atomic
def set_person_map(*, company, external_code: str, employee: Employee, request=None, actor=None) -> int:
    """Mapea código-del-aparato → trabajador y re-matchea chequeos pendientes."""
    if employee.company_id != company.id:
        raise ValueError("EMPLOYEE_OTHER_COMPANY")
    obj, created = BiometricPersonMap.objects.update_or_create(
        company=company,
        external_code=external_code,
        defaults={"employee": employee, "is_active": True, "created_by": actor},
    )
    rematched = BiometricCheck.objects.filter(
        company=company, external_code=external_code, employee__isnull=True
    ).update(employee=employee)

    write_event(
        request=request,
        module="NOMINA",
        event_type="NOMINA_BIOMETRIC_MAP_SET",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={
            "external_code": external_code,
            "created": created,
            "rematched_checks": rematched,
        },
    )
    return rematched


_ROLLUP_BLOCKED_STATUSES = (PeriodStatus.APPROVED, PeriodStatus.PAID, PeriodStatus.CLOSED)


@transaction.atomic
def rollup_biometric_to_period(*, period: PayrollPeriod, request=None, actor=None) -> dict:
    """Agrega los chequeos del período → AttendanceReport(source=BIOMETRIC) por empleado.

    Un día cuenta como trabajado con AL MENOS UN chequeo ese día (la entrada
    valida; la salida es evidencia). Idempotente: re-ejecutar recalcula el
    mismo reporte (unique period+employee+source).
    """
    if period.status in _ROLLUP_BLOCKED_STATUSES:
        raise ValueError("PERIOD_NOT_EDITABLE")

    company = period.company
    qs = (
        BiometricCheck.objects.filter(
            company=company,
            employee__isnull=False,
            work_date__gte=period.start_date,
            work_date__lte=period.end_date,
        )
        .values("employee_id", "work_date")
        .distinct()
    )
    days_by_employee: dict[int, set] = {}
    for row in qs:
        days_by_employee.setdefault(row["employee_id"], set()).add(row["work_date"])

    now = timezone.now()
    created = updated = 0
    for employee_id, days in days_by_employee.items():
        report, was_created = AttendanceReport.objects.update_or_create(
            period=period,
            employee_id=employee_id,
            source=AttendanceSource.BIOMETRIC,
            defaults={
                "company": company,
                "status": AttendanceStatus.SUBMITTED,
                "days_worked": len(days),
                "submitted_by": actor,
                "submitted_at": now,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1

    write_event(
        request=request,
        module="NOMINA",
        event_type="NOMINA_BIOMETRIC_ROLLUP_APPLIED",
        reason_code="OK",
        actor_user=actor,
        subject_type="PAYROLL_PERIOD",
        subject_id=str(period.id),
        metadata={
            "employees": len(days_by_employee),
            "reports_created": created,
            "reports_updated": updated,
        },
    )
    return {"employees": len(days_by_employee), "reports_created": created, "reports_updated": updated}
