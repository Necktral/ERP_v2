from __future__ import annotations

import csv
import hashlib
import json
from html import escape as xml_escape
from io import BytesIO, StringIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from django.utils import timezone

from .enums import ExportStatus, RunStatus
from .exceptions import ReportingValidationError
from .models import ReportExportLog, ReportRun


def ensure_export_supported(format_code: str) -> str:
    normalized = str(format_code).lower().strip()
    if normalized not in {"json", "csv", "xlsx"}:
        raise ReportingValidationError(f"Formato de exportación no soportado: {format_code}")
    return normalized


def _resolve_columns(payload: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    for key in list(payload.get("dimensions") or []) + list(payload.get("measures") or []):
        text = str(key).strip()
        if text and text not in ordered:
            ordered.append(text)
    rows = payload.get("rows") or []
    dynamic = sorted({str(k) for row in rows for k in (row or {}).keys() if str(k) not in ordered})
    return ordered + dynamic


def _to_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, indent=2).encode("utf-8")


def _to_csv_bytes(*, columns: list[str], rows: list[dict[str, Any]]) -> bytes:
    sio = StringIO()
    writer = csv.writer(sio)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(col, "") for col in columns])
    return sio.getvalue().encode("utf-8")


def _xlsx_col_letter(col_index: int) -> str:
    letters: list[str] = []
    n = col_index
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(65 + rem))
    return "".join(reversed(letters))


def _to_xlsx_bytes(*, columns: list[str], rows: list[dict[str, Any]]) -> bytes:
    def _cell_xml(ref: str, value: Any) -> str:
        text = xml_escape(str("" if value is None else value))
        return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    xml_rows: list[str] = []
    header_cells = "".join(_cell_xml(f"{_xlsx_col_letter(i + 1)}1", col) for i, col in enumerate(columns))
    xml_rows.append(f'<row r="1">{header_cells}</row>')

    for r_index, row in enumerate(rows, start=2):
        row_cells = "".join(
            _cell_xml(f"{_xlsx_col_letter(c_index + 1)}{r_index}", row.get(col, ""))
            for c_index, col in enumerate(columns)
        )
        xml_rows.append(f'<row r="{r_index}">{row_cells}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(xml_rows)}</sheetData>"
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
        '<sheets><sheet name="dataset" sheetId="1" r:id="rId1"/></sheets>'
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


def _export_bytes(*, export_format: str, payload: dict[str, Any]) -> tuple[bytes, str]:
    rows = list(payload.get("rows") or [])
    columns = _resolve_columns(payload)
    if export_format == "json":
        return _to_json_bytes(payload), "application/json; charset=utf-8"
    if export_format == "csv":
        return _to_csv_bytes(columns=columns, rows=rows), "text/csv; charset=utf-8"
    if export_format == "xlsx":
        return _to_xlsx_bytes(columns=columns, rows=rows), (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    raise ReportingValidationError(f"Formato de exportación no soportado: {export_format}")


def create_export_from_run(*, run: ReportRun, requested_by, export_format: str) -> ReportExportLog:
    normalized = ensure_export_supported(export_format)
    if run.status != RunStatus.SUCCEEDED:
        raise ReportingValidationError("Solo se puede exportar un run en estado SUCCEEDED.")

    payload = dict(run.result_payload_json or {})
    if not payload:
        raise ReportingValidationError("El run no tiene payload persistido para exportar.")

    if normalized not in set(payload.get("export_capabilities") or []):
        raise ReportingValidationError(f"Formato no habilitado para dataset: {normalized}")

    file_name = f"{run.dataset_key.replace('.', '_')}_{run.run_id}.{normalized}"
    export = ReportExportLog.objects.create(
        run=run,
        format=normalized,
        requested_by=requested_by,
        status=ExportStatus.PENDING,
        file_name=file_name,
        delivery_channel="INLINE_API",
    )
    try:
        binary, mime_type = _export_bytes(export_format=normalized, payload=payload)
        digest = hashlib.sha256(binary).hexdigest()
        export.status = ExportStatus.SUCCEEDED
        export.output_hash = digest
        export.file_size = len(binary)
        export.mime_type = mime_type
        if normalized in {"json", "csv"}:
            export.content_text = binary.decode("utf-8")
            export.content_base64 = ""
        else:
            import base64

            export.content_text = ""
            export.content_base64 = base64.b64encode(binary).decode("ascii")
        export.completed_at = timezone.now()
        export.save(
            update_fields=[
                "status",
                "output_hash",
                "file_size",
                "mime_type",
                "content_text",
                "content_base64",
                "completed_at",
                "updated_at",
            ]
        )
        return export
    except Exception as exc:  # pragma: no cover - enforced by API behavior tests
        export.status = ExportStatus.FAILED
        export.error_detail = str(exc)
        export.completed_at = timezone.now()
        export.save(update_fields=["status", "error_detail", "completed_at", "updated_at"])
        raise


def export_to_dict(export: ReportExportLog) -> dict[str, Any]:
    return {
        "export_id": str(export.export_id),
        "run_id": str(export.run.run_id),
        "dataset_key": export.run.dataset_key,
        "format": export.format,
        "status": export.status,
        "output_hash": export.output_hash,
        "file_size": int(export.file_size or 0),
        "mime_type": export.mime_type,
        "file_name": export.file_name,
        "delivery_channel": export.delivery_channel,
        "error_detail": export.error_detail,
        "created_at": export.created_at,
        "completed_at": export.completed_at,
        "updated_at": export.updated_at,
    }
