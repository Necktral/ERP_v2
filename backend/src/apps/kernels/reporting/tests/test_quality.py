from __future__ import annotations

from apps.kernels.reporting.enums import QualityStatus
from apps.kernels.reporting.quality import evaluate_dataset_quality
from apps.kernels.reporting.registry import get_dataset_spec


def _base_envelope():
    return {
        "dataset_key": "payments.collection.period",
        "rows": [{"status": "CAPTURED", "payment_count": 1, "amount": "10.00"}],
        "totals": {
            "payment_count": 1,
            "amount": "10.00",
            "cash_sessions_total": 2,
            "cash_sessions_closed": 1,
        },
        "dimensions": ["status"],
        "measures": ["payment_count", "amount", "cash_sessions_total", "cash_sessions_closed"],
        "lineage": {"source_modules": ["PAYMENTS"]},
    }


def test_quality_allows_global_totals_only_measures_for_payments():
    spec = get_dataset_spec("payments.collection.period")
    envelope = _base_envelope()

    outcome = evaluate_dataset_quality(spec=spec, envelope=envelope)
    assert outcome.status == QualityStatus.PASS
    check_map = {str(row["name"]): str(row["status"]) for row in outcome.checks}
    assert check_map["global_totals_only_measures"] == QualityStatus.PASS
    assert check_map["global_totals_only_rows"] == QualityStatus.PASS


def test_quality_fails_when_global_totals_measure_is_missing_from_totals():
    spec = get_dataset_spec("payments.collection.period")
    envelope = _base_envelope()
    envelope["totals"].pop("cash_sessions_total")

    outcome = evaluate_dataset_quality(spec=spec, envelope=envelope)
    assert outcome.status == QualityStatus.FAIL
    check_map = {str(row["name"]): str(row["status"]) for row in outcome.checks}
    assert check_map["global_totals_only_measures"] == QualityStatus.FAIL


def test_quality_fails_when_global_totals_only_measure_is_present_in_rows():
    spec = get_dataset_spec("payments.collection.period")
    envelope = _base_envelope()
    envelope["rows"][0]["cash_sessions_total"] = 1

    outcome = evaluate_dataset_quality(spec=spec, envelope=envelope)
    assert outcome.status == QualityStatus.FAIL
    check_map = {str(row["name"]): str(row["status"]) for row in outcome.checks}
    assert check_map["global_totals_only_rows"] == QualityStatus.FAIL
