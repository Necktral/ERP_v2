from __future__ import annotations

from apps.kernels.reporting.contract_compat import compare_contract_manifests


def _base_manifest() -> dict:
    return {
        "manifest_version": 1,
        "datasets": [
            {
                "dataset_key": "accounting.pnl.period",
                "schema_version": "1.0.0",
                "semantic_version": "1.0.0",
                "filters_schema": {"date_from": {"type": "date", "required": False}},
                "dimensions": ["account_code"],
                "measures": ["amount"],
                "quality_policy": {
                    "required_totals": ["amount"],
                    "required_dimensions": ["account_code"],
                    "allow_empty_rows": False,
                },
                "export_capabilities": ["json", "csv"],
            }
        ],
    }


def test_structural_change_requires_schema_bump():
    baseline = _base_manifest()
    current = _base_manifest()
    current["datasets"][0]["dimensions"] = ["account_code", "account_name"]
    issues = compare_contract_manifests(baseline=baseline, current=current)
    assert any("requires schema_version bump" in issue for issue in issues)


def test_structural_change_with_schema_bump_passes():
    baseline = _base_manifest()
    current = _base_manifest()
    current["datasets"][0]["dimensions"] = ["account_code", "account_name"]
    current["datasets"][0]["schema_version"] = "1.1.0"
    issues = compare_contract_manifests(baseline=baseline, current=current)
    assert not any("requires schema_version bump" in issue for issue in issues)


def test_semantic_change_requires_semantic_bump():
    baseline = _base_manifest()
    current = _base_manifest()
    current["datasets"][0]["quality_policy"]["allow_empty_rows"] = True
    issues = compare_contract_manifests(baseline=baseline, current=current)
    assert any("requires semantic_version bump" in issue for issue in issues)


def test_semantic_change_with_semantic_bump_passes():
    baseline = _base_manifest()
    current = _base_manifest()
    current["datasets"][0]["quality_policy"]["allow_empty_rows"] = True
    current["datasets"][0]["semantic_version"] = "1.0.1"
    issues = compare_contract_manifests(baseline=baseline, current=current)
    assert not any("requires semantic_version bump" in issue for issue in issues)


def test_new_dataset_must_be_complete():
    baseline = _base_manifest()
    current = _base_manifest()
    current["datasets"].append(
        {
            "dataset_key": "fuel.sales.by_shift.daily",
            "schema_version": "1.0.0",
            "semantic_version": "1.0.0",
            "filters_schema": {},
            "dimensions": [],
            "measures": ["sales_count"],
            "quality_policy": {"required_totals": ["sales_count"]},
            "export_capabilities": ["json"],
        }
    )
    issues = compare_contract_manifests(baseline=baseline, current=current)
    assert any("new dataset invalid" in issue for issue in issues)
