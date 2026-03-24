from __future__ import annotations

from .exceptions import ReportingValidationError


def ensure_export_supported(format_code: str) -> None:
    if str(format_code).lower() not in {"json", "csv", "xlsx"}:
        raise ReportingValidationError(f"Formato de exportación no soportado: {format_code}")

