"""Export de la planilla legal (norma INSS) — reproduce TODAS las casillas en .xlsx.

Genera el .xlsx por OOXML crudo (zipfile + XML), sin dependencias nuevas, igual que
`apps.kernels.reporting.exports`. Reproduce la planilla legal con: bloque de título,
encabezados AGRUPADOS (INGRESOS / RETENCIONES / COSTOS PATRONALES) con celdas
combinadas, una fila por empleado con cada casilla (incluido el SÉPTIMO DÍA), fila de
totales, y firmas (ELABORADO / REVISADO / AUTORIZADO).

El PDF (WeasyPrint) se construye aparte (requiere dependencia + imagen); este módulo
expone `build_planilla_matrix` para que ambos formatos compartan la misma fuente.
"""
from __future__ import annotations

from decimal import Decimal
from html import escape as xml_escape
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

# (clave, etiqueta legal, grupo)  — grupo "" = sin grupo
COLUMNS: list[tuple[str, str, str]] = [
    ("no", "No.", ""),
    ("inss_number", "No. INSS", ""),
    ("cedula", "Cédula", ""),
    ("full_name", "Nombres y Apellidos", ""),
    ("gender", "Género", ""),
    ("cargo", "Cargo", ""),
    ("daily_rate_nio", "Salario Diario", ""),
    ("base_salary_nio", "Salario Mensual", ""),
    ("quincenal_salary", "Salario del Período", "INGRESOS"),
    ("days_worked", "Días Laborados", "INGRESOS"),
    ("seventh_day_days", "Séptimo Día", "INGRESOS"),
    ("days_subsidy", "Días Subsidio", "INGRESOS"),
    ("subsidy_amount", "Subsidio", "INGRESOS"),
    ("total_basico", "Total Básico", "INGRESOS"),
    ("vacation_provision", "Vacaciones", "INGRESOS"),
    ("thirteenth_month_provision", "13vo Mes", "INGRESOS"),
    ("total_income", "Total Ingresos", "INGRESOS"),
    ("inss_laboral", "INSS", "RETENCIONES"),
    ("ir_amount", "IR", "RETENCIONES"),
    ("loan_payment", "Abono Préstamos", "RETENCIONES"),
    ("total_deductions", "Total Retención", "RETENCIONES"),
    ("food_deduction", "Alimentación", "OTRAS DEDUCCIONES"),
    ("advance_deduction", "Adelanto Finca", "OTRAS DEDUCCIONES"),
    ("store_credit_deduction", "Crédito Comisariato", "OTRAS DEDUCCIONES"),
    ("total_devengado", "Salario Devengado", ""),
    ("net_to_pay", "Neto a Pagar", ""),
    ("recibi_conforme", "Recibí Conforme", ""),
    ("inss_patronal", "INSS Patronal", "COSTOS PATRONALES"),
    ("vacation_cost", "Vacaciones", "COSTOS PATRONALES"),
    ("thirteenth_month_cost", "13vo Mes", "COSTOS PATRONALES"),
    ("inatec", "INATEC 2%", "COSTOS PATRONALES"),
    ("total_payroll_cost", "Total Gastos Nómina", "COSTOS PATRONALES"),
]

# Columnas numéricas que se totalizan al pie.
_TOTALED = {
    "quincenal_salary", "subsidy_amount", "total_basico", "vacation_provision",
    "thirteenth_month_provision", "total_income", "inss_laboral", "ir_amount",
    "loan_payment", "total_deductions", "food_deduction", "advance_deduction",
    "store_credit_deduction", "total_devengado", "net_to_pay", "inss_patronal",
    "vacation_cost", "thirteenth_month_cost", "inatec", "total_payroll_cost",
}


def _entry_values(entry, index: int) -> dict[str, object]:
    """Mapea un PayrollEntry a las casillas de la planilla (incluye Total Básico = salario+séptimo+feriado)."""
    total_basico = (entry.quincenal_salary or Decimal("0")) + (entry.seventh_day_amount or Decimal("0")) + (
        entry.holiday_amount or Decimal("0")
    )
    return {
        "no": index,
        "inss_number": entry.inss_number,
        "cedula": entry.cedula,
        "full_name": entry.full_name,
        "gender": entry.gender,
        "cargo": entry.cargo,
        "daily_rate_nio": entry.daily_rate_nio,
        "base_salary_nio": entry.base_salary_nio,
        "quincenal_salary": entry.quincenal_salary,
        "days_worked": entry.days_worked,
        "seventh_day_days": entry.seventh_day_days,
        "days_subsidy": entry.days_subsidy,
        "subsidy_amount": entry.subsidy_amount,
        "total_basico": total_basico,
        "vacation_provision": entry.vacation_provision,
        "thirteenth_month_provision": entry.thirteenth_month_provision,
        "total_income": entry.total_income,
        "inss_laboral": entry.inss_laboral,
        "ir_amount": entry.ir_amount,
        "loan_payment": entry.loan_payment,
        "total_deductions": entry.total_deductions,
        "food_deduction": entry.food_deduction,
        "advance_deduction": entry.advance_deduction,
        "store_credit_deduction": entry.store_credit_deduction,
        "total_devengado": entry.total_devengado,
        "net_to_pay": entry.net_to_pay,
        "recibi_conforme": "",
        "inss_patronal": entry.inss_patronal,
        "vacation_cost": entry.vacation_cost,
        "thirteenth_month_cost": entry.thirteenth_month_cost,
        "inatec": entry.inatec,
        "total_payroll_cost": entry.total_payroll_cost,
    }


def build_planilla_matrix(sheet) -> dict:
    """Fuente común (xlsx/PDF): título, columnas, filas por empleado y totales."""
    period = sheet.period
    company = period.company
    entries = list(sheet.entries.select_related("employee").order_by("id"))
    rows = [_entry_values(e, i) for i, e in enumerate(entries, start=1)]

    totals = {key: Decimal("0.00") for key in _TOTALED}
    for row in rows:
        for key in _TOTALED:
            totals[key] += Decimal(str(row.get(key) or "0"))

    inss_label = "CON INSS" if sheet.has_inss else "SIN INSS"
    return {
        "company_name": str(company),
        "title": "PLANILLA DE SALARIO",
        "subtitle": f"{sheet.sheet_name} [{inss_label}] — {period.year}/{period.month:02d} {period.period_type}",
        "columns": COLUMNS,
        "rows": rows,
        "totals": totals,
    }


def _col_letter(col_index: int) -> str:
    letters: list[str] = []
    n = col_index
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters))


def _cell(ref: str, value: object) -> str:
    text = xml_escape("" if value is None else str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def render_planilla_xlsx(sheet) -> bytes:
    """Genera el .xlsx legal con encabezados agrupados (celdas combinadas) + totales + firmas."""
    data = build_planilla_matrix(sheet)
    cols = data["columns"]
    ncols = len(cols)
    xml_rows: list[str] = []
    merges: list[str] = []

    def row_xml(r: int, cells: list[str]) -> None:
        xml_rows.append(f'<row r="{r}">{"".join(cells)}</row>')

    # Título (filas 1-3), combinadas sobre todo el ancho
    last_col = _col_letter(ncols)
    row_xml(1, [_cell("A1", data["company_name"])])
    row_xml(2, [_cell("A2", data["title"])])
    row_xml(3, [_cell("A3", data["subtitle"])])
    for r in (1, 2, 3):
        merges.append(f'<mergeCell ref="A{r}:{last_col}{r}"/>')

    # Fila 5: encabezados de GRUPO (combinados por rango contiguo del mismo grupo)
    group_cells: list[str] = []
    i = 0
    while i < ncols:
        grp = cols[i][2]
        j = i
        while j + 1 < ncols and cols[j + 1][2] == grp and grp:
            j += 1
        if grp:
            ref = _col_letter(i + 1)
            group_cells.append(_cell(f"{ref}5", grp))
            if j > i:
                merges.append(f'<mergeCell ref="{ref}5:{_col_letter(j + 1)}5"/>')
        i = j + 1
    row_xml(5, group_cells)

    # Fila 6: encabezados de columna
    row_xml(6, [_cell(f"{_col_letter(c + 1)}6", label) for c, (_k, label, _g) in enumerate(cols)])

    # Filas de datos
    r = 7
    for row in data["rows"]:
        row_xml(r, [_cell(f"{_col_letter(c + 1)}{r}", row.get(key, "")) for c, (key, _l, _g) in enumerate(cols)])
        r += 1

    # Fila de TOTALES
    total_cells: list[str] = [_cell(f"A{r}", "TOTALES")]
    for c, (key, _l, _g) in enumerate(cols):
        if key in data["totals"]:
            total_cells.append(_cell(f"{_col_letter(c + 1)}{r}", data["totals"][key]))
    row_xml(r, total_cells)

    # Firmas
    r += 3
    row_xml(r, [
        _cell("A" + str(r), "ELABORADO"),
        _cell("E" + str(r), "REVISADO"),
        _cell("I" + str(r), "AUTORIZADO"),
    ])

    merge_xml = f'<mergeCells count="{len(merges)}">{"".join(merges)}</mergeCells>' if merges else ""
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(xml_rows)}</sheetData>"
        f"{merge_xml}"
        "</worksheet>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Planilla" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()
