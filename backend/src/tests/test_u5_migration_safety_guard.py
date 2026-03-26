from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
GUARD_SCRIPT = REPO_ROOT / "qa" / "migration_safety_guard.py"
BASELINE_REL = Path("qa/contracts/migration_safety_baseline.json")
OUTPUT_REL = Path("qa/reports/migration_safety_guard.json")
MIGRATION_REL = Path("backend/src/apps/modulos/demo/migrations/0001_initial.py")


def _write_migration(root: Path, content: str) -> Path:
    path = root / MIGRATION_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_baseline(root: Path, entry: dict[str, str] | None) -> None:
    payload: dict[str, object] = {"version": 1, "generated_at": "2026-03-25T00:00:00Z", "migrations": {}}
    if entry is not None:
        payload["migrations"] = {MIGRATION_REL.as_posix(): entry}
    baseline_path = root / BASELINE_REL
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _run_guard(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(GUARD_SCRIPT),
            "--root",
            str(root),
            "--baseline",
            BASELINE_REL.as_posix(),
            "--output",
            OUTPUT_REL.as_posix(),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_fails_when_migration_has_no_baseline_entry(tmp_path: Path) -> None:
    migration = """from django.db import migrations


class Migration(migrations.Migration):
    dependencies = []
    operations = []
"""
    _write_migration(tmp_path, migration)
    _write_baseline(tmp_path, entry=None)

    proc = _run_guard(tmp_path)

    assert proc.returncode == 1
    assert "missing baseline metadata for migrations" in proc.stdout


def test_fails_addindexconcurrently_without_atomic_false(tmp_path: Path) -> None:
    migration = """from django.db import migrations


class Migration(migrations.Migration):
    dependencies = []
    operations = [
        migrations.AddIndexConcurrently(model_name="demo", index=None),
    ]
"""
    _write_migration(tmp_path, migration)
    _write_baseline(
        tmp_path,
        {
            "risk_class": "online_safe",
            "rollout_strategy": "expand",
            "rollback_strategy": "roll_forward_preferred",
            "owner": "team-demo",
            "ticket_ref": "U5-TEST-1",
            "fingerprint": _fingerprint(migration),
        },
    )

    proc = _run_guard(tmp_path)

    assert proc.returncode == 1
    assert "uses AddIndexConcurrently but migration.atomic != False" in proc.stdout


def test_fails_risky_ops_marked_as_metadata_only(tmp_path: Path) -> None:
    migration = """from django.db import migrations


class Migration(migrations.Migration):
    dependencies = []
    operations = [
        migrations.RemoveField(model_name="demo", name="old_field"),
    ]
"""
    _write_migration(tmp_path, migration)
    _write_baseline(
        tmp_path,
        {
            "risk_class": "metadata_only",
            "rollout_strategy": "expand",
            "rollback_strategy": "roll_forward_preferred",
            "owner": "team-demo",
            "ticket_ref": "U5-TEST-2",
            "fingerprint": _fingerprint(migration),
        },
    )

    proc = _run_guard(tmp_path)

    assert proc.returncode == 1
    assert "cannot be classified as metadata_only" in proc.stdout


def test_passes_for_valid_migration_metadata(tmp_path: Path) -> None:
    migration = """from django.db import migrations


class Migration(migrations.Migration):
    atomic = False
    dependencies = []
    operations = [
        migrations.AddIndexConcurrently(model_name="demo", index=None),
    ]
"""
    _write_migration(tmp_path, migration)
    _write_baseline(
        tmp_path,
        {
            "risk_class": "online_safe",
            "rollout_strategy": "expand",
            "rollback_strategy": "roll_forward_preferred",
            "owner": "team-demo",
            "ticket_ref": "U5-TEST-3",
            "fingerprint": _fingerprint(migration),
        },
    )

    proc = _run_guard(tmp_path)

    assert proc.returncode == 0
    report_path = tmp_path / OUTPUT_REL
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
