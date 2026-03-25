from __future__ import annotations

from apps.kernels.reporting.registry import DATASET_REGISTRY


def test_reporting_registry_dataset_keys_are_unique():
    keys = [row.dataset_key for row in DATASET_REGISTRY]
    assert len(keys) == len(set(keys))


def test_reporting_registry_contains_accounting_seed_set():
    keys = {row.dataset_key for row in DATASET_REGISTRY}
    assert "accounting.trial_balance.period" in keys
    assert "accounting.general_ledger.transaction" in keys
    assert "accounting.pnl.period" in keys
    assert "accounting.balance_sheet.as_of" in keys
    assert "accounting.operational_reconciliation.period" in keys


def test_reporting_registry_dashboard_metadata_contract_is_complete():
    for row in DATASET_REGISTRY:
        assert isinstance(row.render_hints, dict)
        assert row.render_hints.get("default_chart")

        assert isinstance(row.drill_metadata, dict)
        assert "supports_drill_down" in row.drill_metadata
        assert "supports_drill_through" in row.drill_metadata

        assert isinstance(row.quality_policy, dict)
        assert "required_totals" in row.quality_policy
        assert "required_dimensions" in row.quality_policy
        assert "allow_empty_rows" in row.quality_policy
