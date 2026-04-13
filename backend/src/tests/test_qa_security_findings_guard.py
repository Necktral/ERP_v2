from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def _load_guard_module():
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "qa" / "enforce_security_findings.py"
    spec = importlib.util.spec_from_file_location("qa_enforce_security_findings", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_guard_fails_when_audit_reports_are_missing(tmp_path, monkeypatch):
    module = _load_guard_module()

    _write_json(tmp_path / "qa/contracts/security_exceptions.json", {"exceptions": []})
    args = argparse.Namespace(
        root=str(tmp_path),
        pip_report="qa_pip_audit.json",
        npm_report="qa_npm_audit.json",
        exceptions="qa/contracts/security_exceptions.json",
        output="qa/reports/security_findings_guard.json",
    )
    monkeypatch.setattr(module, "parse_args", lambda: args)

    rc = module.main()
    assert rc == 1
    report = json.loads((tmp_path / "qa/reports/security_findings_guard.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert any("report not found" in issue for issue in report["issues"])


def test_guard_fails_when_audit_report_json_is_invalid(tmp_path, monkeypatch):
    module = _load_guard_module()

    _write_json(tmp_path / "qa/contracts/security_exceptions.json", {"exceptions": []})
    (tmp_path / "qa_pip_audit.json").write_text("{bad json", encoding="utf-8")
    _write_json(tmp_path / "qa_npm_audit.json", {"vulnerabilities": {}})
    args = argparse.Namespace(
        root=str(tmp_path),
        pip_report="qa_pip_audit.json",
        npm_report="qa_npm_audit.json",
        exceptions="qa/contracts/security_exceptions.json",
        output="qa/reports/security_findings_guard.json",
    )
    monkeypatch.setattr(module, "parse_args", lambda: args)

    rc = module.main()
    assert rc == 1
    report = json.loads((tmp_path / "qa/reports/security_findings_guard.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert any("invalid JSON" in issue for issue in report["issues"])
