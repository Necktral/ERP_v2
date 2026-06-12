"""Tests del control biométrico (fuente ① de asistencia).

Cubre: lector .xlsx/.csv sin dependencias, parseo flexible de encabezados,
ingesta idempotente (reimportar/reenviar no duplica), matching por
employee_code y por mapeo manual, rollup a AttendanceReport(BIOMETRIC) y el
push del aparato autenticado por token de dispositivo.
"""
from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.nomina.biometric.services_biometric import (
    import_checks_file,
    parse_check_rows,
    rollup_biometric_to_period,
    set_person_map,
)
from apps.kernels.nomina.biometric.tabular_reader import TabularReadError, read_tabular_file
from apps.kernels.nomina.models import (
    AttendanceReport,
    AttendanceSource,
    BiometricCheck,
    BiometricDevice,
    PayrollPeriod,
    PeriodStatus,
    PeriodType,
)
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _scope():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    return company, branch


def _emp(company, code, first_name="Trabajador"):
    return Employee.objects.create(
        company=company, employee_code=code, first_name=first_name, last_name="Campo", is_active=True
    )


def _device(company, branch=None):
    return BiometricDevice.objects.create(company=company, branch=branch, name="Portón hacienda")


def _request(company=None):
    return SimpleNamespace(
        user=None, META={}, company=company, branch=None, _request=None,
        ctx=None, request_id=f"req_{uuid.uuid4().hex[:8]}", path="", method="POST",
    )


def _period(company, start=date(2026, 6, 1), end=date(2026, 6, 14)):
    return PayrollPeriod.objects.create(
        company=company,
        year=start.year,
        month=start.month,
        period_type=PeriodType.CATORCENA,
        start_date=start,
        end_date=end,
        working_days=12,
    )


def _make_xlsx(rows: list[list[str]]) -> bytes:
    """Construye un .xlsx mínimo (inline strings) — como exportan los aparatos."""
    sheet_rows = []
    for r_idx, row in enumerate(rows, start=1):
        cells = []
        for c_idx, value in enumerate(row):
            col = chr(ord("A") + c_idx)
            cells.append(f'<c r="{col}{r_idx}" t="inlineStr"><is><t>{value}</t></is></c>')
        sheet_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def _make_shared_string_xlsx() -> bytes:
    """Construye un .xlsx mínimo con sharedStrings y huecos de columnas."""
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="C2"><v>42</v></c></row>'
        "</sheetData></worksheet>"
    )
    shared = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<si><t>ID</t></si><si><t>Nombre</t></si>"
        '<si><r><t>10</t></r></si>'
        "</sst>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        zf.writestr("xl/sharedStrings.xml", shared)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def _make_xlsx_without_sheet() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types></Types>')
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Lector + parseo
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_xlsx_reader_and_flexible_parse():
    content = _make_xlsx(
        [
            ["No.", "Nombre", "Fecha/Hora", "Estado"],
            ["101", "Juan Pérez", "2026-06-01 06:02:11", "Check-In"],
            ["101", "Juan Pérez", "2026-06-01 16:40:00", "Check-Out"],
        ]
    )
    rows = read_tabular_file("export.xlsx", content)
    assert rows[0] == ["No.", "Nombre", "Fecha/Hora", "Estado"]

    parsed = parse_check_rows(rows)
    assert parsed.errors == []
    assert len(parsed.checks) == 2
    assert parsed.checks[0].external_code == "101"
    assert parsed.checks[0].direction == "IN"
    assert parsed.checks[1].direction == "OUT"


def test_tabular_reader_supports_shared_strings_fallbacks_and_user_errors():
    rows = read_tabular_file("export", _make_shared_string_xlsx())
    assert rows == [["ID", "Nombre"], ["10", "", "42"]]

    csv_rows = read_tabular_file("marcas.txt", "ID;Nombre\n1;José\n".encode("latin-1"))
    assert csv_rows == [["ID", "Nombre"], ["1", "José"]]

    with pytest.raises(TabularReadError, match="xlsx"):
        read_tabular_file("bad.xlsx", b"not-a-zip")
    with pytest.raises(TabularReadError, match="hojas"):
        read_tabular_file("empty.xlsx", _make_xlsx_without_sheet())
    with pytest.raises(TabularReadError, match="xls"):
        read_tabular_file("legacy.xls", b"old-binary")


def test_parse_supports_separate_date_time_and_excel_serial():
    rows = [
        ["ID", "Fecha", "Hora", "Tipo"],
        ["7", "01/06/2026", "06:15", "Entrada"],
        ["7", "46174.70", "", "Salida"],  # serial de Excel ≈ 2026-06-01 16:48
    ]
    parsed = parse_check_rows(rows)
    assert parsed.errors == []
    assert len(parsed.checks) == 2
    assert parsed.checks[0].checked_at.strftime("%Y-%m-%d %H:%M") == "2026-06-01 06:15"
    assert parsed.checks[1].checked_at.year == 2026


def test_parse_reports_missing_headers_and_excel_time_fraction():
    assert parse_check_rows([]).errors == ["Archivo vacío."]

    no_code = parse_check_rows([["Fecha/Hora"], ["2026-06-01 06:00:00"]])
    assert no_code.checks == []
    assert "código de persona" in no_code.errors[0]

    no_datetime = parse_check_rows([["ID", "Nombre"], ["7", "Juan"]])
    assert no_datetime.checks == []
    assert "fecha/hora" in no_datetime.errors[0]

    serial_time = parse_check_rows([["ID", "Fecha", "Hora"], ["7", "2026-06-01", "0.25"]])
    assert serial_time.errors == []
    assert serial_time.checks[0].checked_at.strftime("%Y-%m-%d %H:%M") == "2026-06-01 06:00"


def test_parse_reports_unreadable_rows():
    rows = [["ID", "Fecha/Hora"], ["", "2026-06-01 06:00"], ["9", "no-es-fecha"]]
    parsed = parse_check_rows(rows)
    assert len(parsed.checks) == 0
    assert len(parsed.errors) == 2


# ---------------------------------------------------------------------------
# Import idempotente + matching
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_import_csv_matches_and_is_idempotent():
    company, _ = _scope()
    device = _device(company)
    emp = _emp(company, code="101")

    csv_content = (
        "ID,Nombre,Fecha/Hora,Estado\n"
        "101,Juan,2026-06-01 06:02:11,Check-In\n"
        "101,Juan,2026-06-01 16:40:00,Check-Out\n"
        "999,Desconocido,2026-06-01 06:05:00,Check-In\n"
    ).encode()

    batch = import_checks_file(
        device=device, file_name="export.csv", content=csv_content, request=_request(company)
    )
    assert batch.rows_total == 3
    assert batch.created_count == 3
    assert batch.duplicate_count == 0
    assert batch.unmatched_count == 1  # el 999 no existe

    assert BiometricCheck.objects.filter(employee=emp).count() == 2
    assert BiometricCheck.objects.filter(employee__isnull=True, external_code="999").count() == 1

    # Reimportar EXACTAMENTE el mismo archivo → no duplica nada
    batch2 = import_checks_file(
        device=device, file_name="export.csv", content=csv_content, request=_request(company)
    )
    assert batch2.created_count == 0
    assert batch2.duplicate_count == 3
    assert BiometricCheck.objects.filter(device=device).count() == 3


@pytest.mark.django_db
def test_person_map_rematches_pending_checks():
    company, _ = _scope()
    device = _device(company)
    emp = _emp(company, code="EMP-77")  # su código NO coincide con el del aparato

    csv_content = ("ID,Fecha/Hora\n555,2026-06-01 06:00:00\n555,2026-06-02 06:01:00\n").encode()
    import_checks_file(device=device, file_name="e.csv", content=csv_content, request=_request(company))
    assert BiometricCheck.objects.filter(employee__isnull=True, external_code="555").count() == 2

    rematched = set_person_map(
        company=company, external_code="555", employee=emp, request=_request(company)
    )
    assert rematched == 2
    assert BiometricCheck.objects.filter(employee=emp).count() == 2

    # los siguientes imports del mismo código ya matchean directo
    more = ("ID,Fecha/Hora\n555,2026-06-03 06:00:00\n").encode()
    import_checks_file(device=device, file_name="e2.csv", content=more, request=_request(company))
    assert BiometricCheck.objects.filter(employee=emp).count() == 3


# ---------------------------------------------------------------------------
# Rollup al período
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rollup_counts_days_and_is_idempotent():
    company, _ = _scope()
    device = _device(company)
    emp = _emp(company, code="101")
    period = _period(company)

    # 3 días con chequeos (uno con entrada y salida, dos solo entrada) + 1 fuera del período
    csv_content = (
        "ID,Fecha/Hora,Estado\n"
        "101,2026-06-01 06:00:00,Entrada\n"
        "101,2026-06-01 16:30:00,Salida\n"
        "101,2026-06-02 06:05:00,Entrada\n"
        "101,2026-06-03 06:01:00,Entrada\n"
        "101,2026-06-20 06:00:00,Entrada\n"
    ).encode()
    import_checks_file(device=device, file_name="e.csv", content=csv_content, request=_request(company))

    result = rollup_biometric_to_period(period=period, request=_request(company))
    assert result["employees"] == 1
    assert result["reports_created"] == 1

    report = AttendanceReport.objects.get(period=period, employee=emp, source=AttendanceSource.BIOMETRIC)
    assert report.days_worked == 3  # la entrada valida el día; salida solo evidencia

    # idempotente: re-ejecutar actualiza el mismo reporte
    result2 = rollup_biometric_to_period(period=period, request=_request(company))
    assert result2["reports_created"] == 0
    assert result2["reports_updated"] == 1
    assert AttendanceReport.objects.filter(period=period, source=AttendanceSource.BIOMETRIC).count() == 1


@pytest.mark.django_db
def test_rollup_blocked_on_closed_period():
    company, _ = _scope()
    period = _period(company)
    period.status = PeriodStatus.CLOSED
    period.save(update_fields=["status"])
    with pytest.raises(ValueError):
        rollup_biometric_to_period(period=period, request=_request(company))


# ---------------------------------------------------------------------------
# API: push con token de dispositivo + import por endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_push_endpoint_requires_valid_device_token():
    company, _ = _scope()
    device = _device(company)
    emp = _emp(company, code="101")
    client = APIClient()

    body = {
        "checks": [
            {"code": "101", "ts": "2026-06-01T06:02:11", "direction": "IN"},
            {"code": "101", "ts": "2026-06-01T16:40:00", "direction": "OUT"},
        ]
    }

    # sin token → 401
    resp = client.post("/api/nomina/biometric/push/", body, format="json")
    assert resp.status_code == 401

    # token inválido → 401
    resp = client.post(
        "/api/nomina/biometric/push/", body, format="json", headers={"X-Device-Token": "nope"}
    )
    assert resp.status_code == 401

    # token correcto → ingesta idempotente
    resp = client.post(
        "/api/nomina/biometric/push/", body, format="json", headers={"X-Device-Token": device.api_token}
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["created"] == 2
    assert BiometricCheck.objects.filter(employee=emp).count() == 2

    # reenvío (el aparato repite) → no duplica
    resp = client.post(
        "/api/nomina/biometric/push/", body, format="json", headers={"X-Device-Token": device.api_token}
    )
    assert resp.data["created"] == 0
    assert resp.data["duplicates"] == 2

    device.refresh_from_db()
    assert device.last_seen_at is not None


def _client(*, company, branch, perms):
    u = User.objects.create_user(
        username=f"u_{uuid.uuid4().hex[:8]}", email=f"e_{uuid.uuid4().hex[:8]}@t.com", password="x"
    )
    UserMembership.objects.create(user=u, org_unit=company, is_active=True)
    UserMembership.objects.create(user=u, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=u, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=u, role=role, org_unit=branch, is_active=True)
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": u.username, "password": "x"}, format="json")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


@pytest.mark.django_db
def test_device_create_import_and_rollup_via_api():
    company, branch = _scope()
    emp = _emp(company, code="101")
    period = _period(company)
    client = _client(
        company=company,
        branch=branch,
        perms=["nomina.config.manage", "nomina.attendance.read", "nomina.attendance.build"],
    )

    created = client.post(
        "/api/nomina/biometric/devices/", {"name": "Portón principal", "vendor": "(por definir)"}, format="json"
    )
    assert created.status_code == 201, created.data
    assert created.data["api_token"]  # se muestra UNA vez
    device_id = created.data["id"]

    csv_bytes = io.BytesIO(b"ID,Fecha/Hora,Estado\n101,2026-06-01 06:00:00,Entrada\n")
    csv_bytes.name = "export.csv"
    imported = client.post(
        f"/api/nomina/biometric/devices/{device_id}/import/", {"file": csv_bytes}, format="multipart"
    )
    assert imported.status_code == 201, imported.data
    assert imported.data["created"] == 1
    assert imported.data["unmatched"] == 0

    rolled = client.post("/api/nomina/biometric/rollup/", {"period_id": period.id}, format="json")
    assert rolled.status_code == 200, rolled.data
    assert rolled.data["reports_created"] == 1
    report = AttendanceReport.objects.get(period=period, employee=emp, source=AttendanceSource.BIOMETRIC)
    assert report.days_worked == 1

    checks = client.get("/api/nomina/biometric/checks/", {"work_date": "2026-06-01"})
    assert checks.status_code == 200
    assert checks.data["count"] == 1


@pytest.mark.django_db
def test_biometric_device_admin_and_error_paths_via_api():
    company, branch = _scope()
    other_company, _ = _scope()
    other_emp = _emp(other_company, code="X-1")
    period = _period(company)
    period.status = PeriodStatus.CLOSED
    period.save(update_fields=["status"])
    client = _client(
        company=company,
        branch=branch,
        perms=["nomina.config.manage", "nomina.attendance.read", "nomina.attendance.build"],
    )

    created = client.post(
        "/api/nomina/biometric/devices/",
        {"name": "Reloj comedor", "vendor": "ZK", "serial": "SN-1", "branch_id": branch.id},
        format="json",
    )
    assert created.status_code == 201, created.data
    device_id = created.data["id"]
    token = created.data["api_token"]
    assert created.data["branch_id"] == branch.id

    listed = client.get("/api/nomina/biometric/devices/")
    assert listed.status_code == 200
    assert listed.data["results"][0]["id"] == device_id

    patched = client.patch(
        f"/api/nomina/biometric/devices/{device_id}/",
        {"name": "Reloj central", "branch_id": None, "is_active": True},
        format="json",
    )
    assert patched.status_code == 200, patched.data
    assert patched.data["name"] == "Reloj central"
    assert patched.data["branch_id"] is None

    rotated = client.post(f"/api/nomina/biometric/devices/{device_id}/rotate-token/", {}, format="json")
    assert rotated.status_code == 200, rotated.data
    assert rotated.data["api_token"] != token

    missing_file = client.post(f"/api/nomina/biometric/devices/{device_id}/import/", {}, format="multipart")
    assert missing_file.status_code == 400

    invalid_upload = io.BytesIO(b"binary")
    invalid_upload.name = "legacy.xls"
    invalid = client.post(
        f"/api/nomina/biometric/devices/{device_id}/import/",
        {"file": invalid_upload},
        format="multipart",
    )
    assert invalid.status_code == 400
    assert "xls" in str(invalid.data)

    csv_bytes = io.BytesIO(b"ID,Fecha/Hora\n999,2026-06-01 06:00:00\n")
    csv_bytes.name = "export.csv"
    imported = client.post(
        f"/api/nomina/biometric/devices/{device_id}/import/",
        {"file": csv_bytes},
        format="multipart",
    )
    assert imported.status_code == 201, imported.data
    assert imported.data["unmatched"] == 1

    batches = client.get("/api/nomina/biometric/batches/")
    assert batches.status_code == 200
    assert batches.data["count"] == 1
    assert batches.data["results"][0]["device_id"] == device_id

    unmatched = client.get("/api/nomina/biometric/checks/", {"only_unmatched": "true"})
    assert unmatched.status_code == 200
    assert unmatched.data["count"] == 1
    assert unmatched.data["results"][0]["external_code"] == "999"

    map_other_company = client.post(
        "/api/nomina/biometric/map/",
        {"external_code": "999", "employee_id": other_emp.id},
        format="json",
    )
    assert map_other_company.status_code == 404

    with pytest.raises(ValueError):
        set_person_map(company=company, external_code="999", employee=other_emp, request=_request(company))

    blocked_rollup = client.post("/api/nomina/biometric/rollup/", {"period_id": period.id}, format="json")
    assert blocked_rollup.status_code == 409
