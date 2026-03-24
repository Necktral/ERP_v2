from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from apps.kernels.accounting.phase7 import (
    balance_sheet_report,
    general_ledger_queryset,
    pnl_report,
    resolve_period_range,
    trial_balance_queryset,
)
from apps.kernels.accounting.serializers import GeneralLedgerRangeIn, OperationalReconciliationIn, ReportRangeIn
from apps.kernels.accounting.services import reconcile_operational_vs_accounting
from rest_framework.exceptions import ValidationError


def _q2(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _resolve_range_payload(validated: dict[str, Any]) -> tuple[date | None, date | None]:
    period = resolve_period_range(year=validated.get("year"), month=validated.get("month"))
    if period is not None:
        return period
    return validated.get("date_from"), validated.get("date_to")


def _validate_with(serializer_cls, filters: dict[str, Any]) -> dict[str, Any]:
    serializer = serializer_cls(data=filters)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def _trial_balance_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    validated = _validate_with(ReportRangeIn, filters)
    date_from, date_to = _resolve_range_payload(validated)
    qs = trial_balance_queryset(company=company, branch=branch, date_from=date_from, date_to=date_to)

    rows: list[dict[str, Any]] = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    for row in qs:
        debit = Decimal(row["debit_total"])
        credit = Decimal(row["credit_total"])
        net = debit - credit
        rows.append(
            {
                "account_code": str(row["account__code"]),
                "account_name": str(row["account__name"]),
                "account_type": str(row["account__account_type"]),
                "debit_total": _q2(debit),
                "credit_total": _q2(credit),
                "net_balance": _q2(net),
            }
        )
        total_debit += debit
        total_credit += credit

    return {
        "grain": "account",
        "dimensions": ["account_code", "account_name", "account_type"],
        "measures": ["debit_total", "credit_total", "net_balance"],
        "rows": rows,
        "totals": {
            "debit_total": _q2(total_debit),
            "credit_total": _q2(total_credit),
            "net_balance": _q2(total_debit - total_credit),
        },
        "warnings": [],
        "source_summary": {"source_modules": ["ACCOUNTING"]},
        "effective_filters": {
            "date_from": str(date_from) if date_from else "",
            "date_to": str(date_to) if date_to else "",
        },
    }


def _general_ledger_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    validated = _validate_with(GeneralLedgerRangeIn, filters)
    date_from, date_to = _resolve_range_payload(validated)
    qs = general_ledger_queryset(
        company=company,
        branch=branch,
        account_code=str(validated["account_code"]),
        date_from=date_from,
        date_to=date_to,
    )

    rows: list[dict[str, Any]] = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    total_amount_tx = Decimal("0.00")
    for row in qs:
        debit = Decimal(row.debit_base)
        credit = Decimal(row.credit_base)
        amount_tx = Decimal(row.amount_tx)
        rows.append(
            {
                "journal_entry_id": int(row.journal_entry_id),
                "entry_date": str(row.journal_entry.entry_date),
                "description": str(row.journal_entry.description or ""),
                "line_no": int(row.line_no),
                "account_code": str(row.account_code_snapshot),
                "currency": str(row.currency),
                "fx_rate": str(row.fx_rate),
                "amount_tx": _q2(amount_tx),
                "debit_base": _q2(debit),
                "credit_base": _q2(credit),
            }
        )
        total_debit += debit
        total_credit += credit
        total_amount_tx += amount_tx

    return {
        "grain": "journal_entry_line",
        "dimensions": ["journal_entry_id", "entry_date", "line_no", "account_code"],
        "measures": ["amount_tx", "debit_base", "credit_base"],
        "rows": rows,
        "totals": {
            "amount_tx": _q2(total_amount_tx),
            "debit_base": _q2(total_debit),
            "credit_base": _q2(total_credit),
        },
        "warnings": [],
        "source_summary": {"source_modules": ["ACCOUNTING"]},
        "effective_filters": {
            "account_code": str(validated["account_code"]).strip().upper(),
            "date_from": str(date_from) if date_from else "",
            "date_to": str(date_to) if date_to else "",
        },
    }


def _pnl_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    validated = _validate_with(ReportRangeIn, filters)
    date_from, date_to = _resolve_range_payload(validated)
    report = pnl_report(company=company, branch=branch, date_from=date_from, date_to=date_to)
    return {
        "grain": "account",
        "dimensions": ["account_code", "account_name", "account_type"],
        "measures": ["debit_total", "credit_total", "balance"],
        "rows": list(report.get("rows") or []),
        "totals": dict(report.get("totals") or {}),
        "warnings": [],
        "source_summary": {"source_modules": ["ACCOUNTING"]},
        "effective_filters": {
            "date_from": str(date_from) if date_from else "",
            "date_to": str(date_to) if date_to else "",
        },
    }


def _balance_sheet_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    validated = _validate_with(ReportRangeIn, filters)
    as_of = validated.get("as_of")
    if as_of is None:
        period = resolve_period_range(year=validated.get("year"), month=validated.get("month"))
        if period is not None:
            as_of = period[1]
        else:
            as_of = validated.get("date_to")
    report = balance_sheet_report(company=company, branch=branch, as_of=as_of or date.today())

    rows: list[dict[str, Any]] = []
    for section in ("assets", "liabilities", "equity"):
        section_rows = report.get(section, {}).get("rows", [])
        for row in section_rows:
            rows.append({"section": section.upper(), **row})

    return {
        "grain": "account",
        "dimensions": ["section", "account_code", "account_name"],
        "measures": ["debit_total", "credit_total", "balance"],
        "rows": rows,
        "totals": dict(report.get("totals") or {}),
        "warnings": [],
        "source_summary": {"source_modules": ["ACCOUNTING"]},
        "effective_filters": {"as_of": str(report.get("as_of") or "")},
    }


def _operational_reconciliation_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    validated = _validate_with(OperationalReconciliationIn, filters)
    payload = reconcile_operational_vs_accounting(
        company=company,
        branch=branch,
        date_from=validated.get("date_from"),
        date_to=validated.get("date_to"),
    )
    return {
        "grain": "event_type",
        "dimensions": ["source_module", "event_type"],
        "measures": [
            "operational_count",
            "linked_count",
            "posted_count",
            "draft_exception_count",
            "operational_amount",
            "draft_amount",
            "posted_amount",
        ],
        "rows": list(payload.get("by_event_type") or []),
        "totals": dict(payload.get("summary") or {}),
        "warnings": [],
        "source_summary": {"source_modules": ["ACCOUNTING", "BILLING", "INVENTORY"]},
        "effective_filters": {
            "date_from": str(validated.get("date_from") or ""),
            "date_to": str(validated.get("date_to") or ""),
        },
    }


def run_dataset(*, dataset_key: str, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    try:
        if dataset_key == "accounting.trial_balance.period":
            return _trial_balance_payload(company=company, branch=branch, filters=filters)
        if dataset_key == "accounting.general_ledger.transaction":
            return _general_ledger_payload(company=company, branch=branch, filters=filters)
        if dataset_key == "accounting.pnl.period":
            return _pnl_payload(company=company, branch=branch, filters=filters)
        if dataset_key == "accounting.balance_sheet.as_of":
            return _balance_sheet_payload(company=company, branch=branch, filters=filters)
        if dataset_key == "accounting.operational_reconciliation.period":
            return _operational_reconciliation_payload(company=company, branch=branch, filters=filters)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    raise ValueError(f"Dataset contable no soportado: {dataset_key}")

