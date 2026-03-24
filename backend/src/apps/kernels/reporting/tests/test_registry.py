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

