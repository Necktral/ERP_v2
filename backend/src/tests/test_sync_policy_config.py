from __future__ import annotations

import ast
from pathlib import Path

from django.conf import settings
from django.test import override_settings

from apps.modulos.sync_engine.services import SyncPolicy, get_policy

SYNC_POLICY_SETTING_NAMES = (
    "SYNC_MAX_COMMANDS_PER_BATCH",
    "SYNC_MAX_PAYLOAD_BYTES",
    "SYNC_MAX_DEVICE_CLOCK_SKEW_SECONDS",
    "SYNC_SEQ_TOLERANT",
)


def _src_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _get_policy_keyword_sources(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "get_policy":
            for stmt in node.body:
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
                    return {
                        keyword.arg: ast.unparse(keyword.value)
                        for keyword in stmt.value.keywords
                        if keyword.arg is not None
                    }
    raise AssertionError(f"get_policy return expression not found in {path}")


def test_sync_policy_settings_are_declared_with_preserved_defaults():
    for name in SYNC_POLICY_SETTING_NAMES:
        assert hasattr(settings, name)

    assert get_policy() == SyncPolicy(
        max_commands_per_batch=100,
        max_payload_bytes=64_000,
        max_device_clock_skew_seconds=6 * 3600,
        seq_tolerant=True,
    )


@override_settings(
    SYNC_MAX_COMMANDS_PER_BATCH=7,
    SYNC_MAX_PAYLOAD_BYTES=2_048,
    SYNC_MAX_DEVICE_CLOCK_SKEW_SECONDS=123,
    SYNC_SEQ_TOLERANT=False,
)
def test_sync_engine_policy_honors_declared_settings_overrides():
    assert get_policy() == SyncPolicy(
        max_commands_per_batch=7,
        max_payload_bytes=2_048,
        max_device_clock_skew_seconds=123,
        seq_tolerant=False,
    )


def test_stale_audit_policy_copy_matches_runtime_policy_expressions():
    root = _src_root()
    runtime_policy = _get_policy_keyword_sources(root / "apps/modulos/sync_engine/services.py")
    audit_policy_copy = _get_policy_keyword_sources(root / "apps/modulos/audit/services.py")

    assert set(runtime_policy) == {
        "max_commands_per_batch",
        "max_payload_bytes",
        "max_device_clock_skew_seconds",
        "seq_tolerant",
    }
    assert audit_policy_copy == runtime_policy
