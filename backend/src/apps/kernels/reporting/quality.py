from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .enums import QualityStatus
from .registry import DatasetSpec


@dataclass(frozen=True)
class QualityOutcome:
    status: str
    checks: list[dict[str, Any]]


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(row).strip() for row in value if str(row).strip()]


def _is_numeric(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float, Decimal)):
        return True
    raw = str(value).strip()
    if not raw:
        return False
    try:
        Decimal(raw)
    except (InvalidOperation, ValueError):
        return False
    return True


def evaluate_dataset_quality(*, spec: DatasetSpec, envelope: dict[str, Any]) -> QualityOutcome:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, status: str, detail: str, *, expected: Any = None, observed: Any = None) -> None:
        row = {"name": name, "status": status, "detail": detail}
        if expected is not None:
            row["expected"] = expected
        if observed is not None:
            row["observed"] = observed
        checks.append(row)

    policy = dict(spec.quality_policy or {})
    required_totals = _as_list(policy.get("required_totals"))
    required_dimensions = _as_list(policy.get("required_dimensions"))
    global_totals_only_measures = _as_list(policy.get("global_totals_only_measures"))
    allow_empty_rows = bool(policy.get("allow_empty_rows", True))

    invalid_global_totals = [key for key in global_totals_only_measures if key not in required_totals]
    if invalid_global_totals:
        add_check(
            "global_totals_only_contract",
            QualityStatus.FAIL,
            "global_totals_only_measures debe estar incluido en required_totals.",
            expected=required_totals,
            observed=invalid_global_totals,
        )
    else:
        add_check("global_totals_only_contract", QualityStatus.PASS, "Contrato de global_totals_only_measures válido.")

    required_contract_keys = ("dataset_key", "rows", "totals", "dimensions", "measures", "lineage")
    missing_contract_keys = [key for key in required_contract_keys if key not in envelope]
    if missing_contract_keys:
        add_check(
            "contract_keys",
            QualityStatus.FAIL,
            "Faltan claves obligatorias del envelope.",
            expected=list(required_contract_keys),
            observed=missing_contract_keys,
        )
    else:
        add_check("contract_keys", QualityStatus.PASS, "Envelope con claves obligatorias completas.")

    lineage = dict(envelope.get("lineage") or {})
    source_modules = _as_list(lineage.get("source_modules"))
    if source_modules:
        add_check("lineage", QualityStatus.PASS, "Lineage presente con source_modules.")
    else:
        add_check("lineage", QualityStatus.FAIL, "Lineage sin source_modules.")

    totals = dict(envelope.get("totals") or {})
    missing_totals = [key for key in required_totals if key not in totals]
    non_numeric_totals = [key for key in required_totals if key in totals and not _is_numeric(totals.get(key))]
    if missing_totals:
        add_check(
            "required_totals",
            QualityStatus.FAIL,
            "Faltan claves de totales requeridas por quality_policy.",
            expected=required_totals,
            observed=missing_totals,
        )
    elif non_numeric_totals:
        add_check(
            "required_totals",
            QualityStatus.FAIL,
            "Hay totales requeridos con valores no numéricos.",
            expected=required_totals,
            observed=non_numeric_totals,
        )
    else:
        add_check("required_totals", QualityStatus.PASS, "Totales requeridos presentes y numéricos.")

    dimensions = _as_list(envelope.get("dimensions"))
    missing_dimensions = [key for key in required_dimensions if key not in dimensions]
    if missing_dimensions:
        add_check(
            "required_dimensions_schema",
            QualityStatus.FAIL,
            "Dimensiones requeridas no declaradas en envelope.dimensions.",
            expected=required_dimensions,
            observed=missing_dimensions,
        )
    else:
        add_check("required_dimensions_schema", QualityStatus.PASS, "Dimensiones requeridas declaradas.")

    rows = list(envelope.get("rows") or [])
    measures = _as_list(envelope.get("measures"))
    missing_global_measures = [key for key in global_totals_only_measures if key not in measures]
    missing_global_totals = [key for key in global_totals_only_measures if key not in totals]
    non_numeric_global_totals = [key for key in global_totals_only_measures if key in totals and not _is_numeric(totals.get(key))]
    if missing_global_measures:
        add_check(
            "global_totals_only_measures",
            QualityStatus.FAIL,
            "Hay medidas globales no declaradas en envelope.measures.",
            expected=global_totals_only_measures,
            observed=missing_global_measures,
        )
    elif missing_global_totals or non_numeric_global_totals:
        add_check(
            "global_totals_only_measures",
            QualityStatus.FAIL,
            "Hay medidas globales ausentes/no numéricas en envelope.totals.",
            expected=global_totals_only_measures,
            observed=missing_global_totals + non_numeric_global_totals,
        )
    else:
        add_check("global_totals_only_measures", QualityStatus.PASS, "Medidas globales válidas en totales.")

    global_in_rows = [key for key in global_totals_only_measures if any(key in (row or {}) for row in rows)]
    if global_in_rows:
        add_check(
            "global_totals_only_rows",
            QualityStatus.FAIL,
            "Se encontraron medidas globales dentro de filas; invalida la semántica del dataset.",
            observed=global_in_rows,
        )
    else:
        add_check("global_totals_only_rows", QualityStatus.PASS, "No hay medidas globales incrustadas en filas.")

    if not rows and not allow_empty_rows:
        add_check(
            "empty_rows",
            QualityStatus.WARN,
            "El dataset quedó sin filas y quality_policy no lo permite como normal.",
        )
    else:
        add_check("empty_rows", QualityStatus.PASS, "Cardinalidad de filas aceptada por quality_policy.")

    if rows and required_dimensions:
        row_missing_dims = [
            idx
            for idx, row in enumerate(rows)
            if not all(dim in row for dim in required_dimensions)
        ]
        if row_missing_dims:
            add_check(
                "required_dimensions_rows",
                QualityStatus.FAIL,
                "Hay filas sin dimensiones requeridas.",
                expected=required_dimensions,
                observed=row_missing_dims[:10],
            )
        else:
            add_check("required_dimensions_rows", QualityStatus.PASS, "Todas las filas contienen dimensiones requeridas.")
    else:
        add_check("required_dimensions_rows", QualityStatus.PASS, "No aplica validación de dimensiones por fila.")

    statuses = {str(row.get("status") or "") for row in checks}
    if QualityStatus.FAIL in statuses:
        final_status = QualityStatus.FAIL
    elif QualityStatus.WARN in statuses:
        final_status = QualityStatus.WARN
    else:
        final_status = QualityStatus.PASS
    return QualityOutcome(status=str(final_status), checks=checks)
