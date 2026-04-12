#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PASS_STATUSES = {"passed", "pass", "ok", "success"}


@dataclass(frozen=True)
class HandoffSectionRule:
    section_id: str
    keywords_any: tuple[str, ...]


@dataclass(frozen=True)
class GateReportSpec:
    path: str
    kind: str
    contains: str | None = None


@dataclass(frozen=True)
class ChangeTypeRule:
    rule_id: str
    priority: int
    any_path_patterns: tuple[str, ...]
    all_paths_match_patterns: tuple[str, ...]
    domain_count_gte: int | None
    non_docs_changes_required: bool
    code_changes_required: bool


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Codex governance guard: clasifica cambios y exige evidencia de handoff/gates."
    )
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--contract",
        default="qa/contracts/codex_governance_contract.json",
        help="Ruta al contrato operativo de gobernanza",
    )
    parser.add_argument("--base-ref", default="", help="Ref base opcional, ej. origin/master")
    parser.add_argument(
        "--output",
        default="qa/reports/codex_governance_guard.json",
        help="Ruta del reporte JSON",
    )
    return parser.parse_args()


def _run_git(root: Path, args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=str(root), check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _resolve_base(root: Path, explicit_base: str) -> str:
    if explicit_base:
        base = _run_git(root, ["merge-base", "HEAD", explicit_base])
        if base:
            return base

    for fallback in ("origin/master", "origin/main"):
        base = _run_git(root, ["merge-base", "HEAD", fallback])
        if base:
            return base

    return _run_git(root, ["rev-parse", "HEAD~1"])


def _changed_files(root: Path, base: str) -> list[str]:
    files: set[str] = set()

    if base:
        out = _run_git(root, ["diff", "--name-only", f"{base}...HEAD"])
        files.update(line.strip().replace("\\", "/") for line in out.splitlines() if line.strip())

    for cmd in (
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        out = _run_git(root, cmd)
        files.update(line.strip().replace("\\", "/") for line in out.splitlines() if line.strip())

    return sorted(files)


def _load_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))

    required_top_level = {
        "critical_path_patterns",
        "evidence_file_patterns",
        "required_handoff_sections",
        "change_type_rules",
        "required_sections_by_type",
        "required_gates_by_type",
        "gate_evidence_reports",
        "forbidden_modes_by_type",
        "mode_markers",
    }
    missing = sorted(required_top_level - set(payload.keys()))
    if missing:
        raise ValueError(f"contract missing required keys: {', '.join(missing)}")

    return payload


def _matches_any(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _domain_for_path(rel: str) -> str | None:
    marker = "backend/src/apps/"
    if marker not in rel:
        return None
    tail = rel.split(marker, 1)[1]
    parts = tail.split("/")
    if len(parts) < 3:
        return None
    layer = parts[0]
    app = parts[1]
    if layer not in {"kernels", "modulos"}:
        return None
    return f"{layer}.{app}"


def _parse_handoff_rules(raw_rules: list[dict[str, Any]]) -> list[HandoffSectionRule]:
    parsed: list[HandoffSectionRule] = []
    for row in raw_rules:
        section_id = str(row.get("id", "")).strip()
        keywords_any_raw = row.get("keywords_any", [])
        if not section_id or not isinstance(keywords_any_raw, list):
            raise ValueError("invalid required_handoff_sections entry")
        keywords = tuple(str(item).strip().lower() for item in keywords_any_raw if str(item).strip())
        if not keywords:
            raise ValueError(f"required_handoff_sections.{section_id} has empty keywords_any")
        parsed.append(HandoffSectionRule(section_id=section_id, keywords_any=keywords))
    return parsed


def _parse_gate_specs(raw_gate_specs: dict[str, Any]) -> dict[str, tuple[GateReportSpec, ...]]:
    parsed: dict[str, tuple[GateReportSpec, ...]] = {}
    for gate, rows in raw_gate_specs.items():
        if not isinstance(rows, list):
            raise ValueError(f"gate_evidence_reports.{gate} must be a list")
        specs: list[GateReportSpec] = []
        for row in rows:
            path = str(row.get("path", "")).strip()
            kind = str(row.get("kind", "")).strip()
            contains = row.get("contains")
            contains_text = str(contains).strip() if contains is not None else None
            if not path or not kind:
                raise ValueError(f"invalid gate report spec for {gate}")
            specs.append(GateReportSpec(path=path, kind=kind, contains=contains_text))
        parsed[gate] = tuple(specs)
    return parsed


def _parse_change_type_rules(raw_rules: list[dict[str, Any]]) -> list[ChangeTypeRule]:
    parsed: list[ChangeTypeRule] = []
    for row in raw_rules:
        rule_id = str(row.get("id", "")).strip()
        priority = int(row.get("priority", 0))
        any_path_patterns = tuple(str(item) for item in row.get("any_path_patterns", []) if str(item).strip())
        all_paths_match_patterns = tuple(
            str(item) for item in row.get("all_paths_match_patterns", []) if str(item).strip()
        )

        domain_count_gte_raw = row.get("domain_count_gte")
        if domain_count_gte_raw is None:
            domain_count_gte: int | None = None
        else:
            domain_count_gte = int(domain_count_gte_raw)

        if not rule_id:
            raise ValueError("change_type_rules entry missing id")

        parsed.append(
            ChangeTypeRule(
                rule_id=rule_id,
                priority=priority,
                any_path_patterns=any_path_patterns,
                all_paths_match_patterns=all_paths_match_patterns,
                domain_count_gte=domain_count_gte,
                non_docs_changes_required=bool(row.get("non_docs_changes_required", False)),
                code_changes_required=bool(row.get("code_changes_required", False)),
            )
        )

    parsed.sort(key=lambda row: row.priority, reverse=True)
    return parsed


def _classify_change_type(
    *,
    changed_files: list[str],
    domains_touched: set[str],
    non_docs_changes: bool,
    code_changes: bool,
    rules: list[ChangeTypeRule],
    default_change_type: str,
) -> str:
    domains_count = len(domains_touched)

    for rule in rules:
        if rule.any_path_patterns and not any(_matches_any(path, rule.any_path_patterns) for path in changed_files):
            continue

        if rule.all_paths_match_patterns:
            if not changed_files:
                continue
            if not all(_matches_any(path, rule.all_paths_match_patterns) for path in changed_files):
                continue

        if rule.domain_count_gte is not None and domains_count < rule.domain_count_gte:
            continue

        if rule.non_docs_changes_required and not non_docs_changes:
            continue

        if rule.code_changes_required and not code_changes:
            continue

        return rule.rule_id

    return default_change_type


def _check_gate_evidence(
    *,
    root: Path,
    gate: str,
    specs: tuple[GateReportSpec, ...],
) -> tuple[bool, bool, list[dict[str, Any]]]:
    missing_report = False
    failing_status = False
    details: list[dict[str, Any]] = []

    for spec in specs:
        abs_path = (root / spec.path).resolve()
        if not abs_path.exists() or abs_path.is_dir():
            missing_report = True
            details.append({"path": spec.path, "result": "missing"})
            continue

        if spec.kind == "text_exists":
            details.append({"path": spec.path, "result": "present"})
            continue

        if spec.kind == "text_contains":
            content = _read_text_file(abs_path).lower()
            needle = (spec.contains or "").lower()
            if needle and needle not in content:
                failing_status = True
                details.append({"path": spec.path, "result": "missing_expected_text", "contains": spec.contains})
            else:
                details.append({"path": spec.path, "result": "ok"})
            continue

        if spec.kind == "json_status":
            try:
                payload = json.loads(_read_text_file(abs_path))
            except Exception:  # noqa: BLE001
                failing_status = True
                details.append({"path": spec.path, "result": "invalid_json"})
                continue
            status = str(payload.get("status", "")).strip().lower()
            if status not in PASS_STATUSES:
                failing_status = True
                details.append({"path": spec.path, "result": "failed_status", "status": status})
            else:
                details.append({"path": spec.path, "result": "ok", "status": status})
            continue

        failing_status = True
        details.append({"path": spec.path, "result": "unknown_kind", "kind": spec.kind})

    return missing_report, failing_status, details


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    contract_path = (root / args.contract).resolve()
    output_path = (root / args.output).resolve()

    findings: list[dict[str, Any]] = []

    if not contract_path.exists():
        payload = {
            "status": "failed",
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "findings": [
                {
                    "type": "missing_contract",
                    "detail": f"contract not found: {contract_path}",
                }
            ],
            "critical_paths_touched": [],
        }
        _write_json(output_path, payload)
        print(f"[qa] codex governance guard failed: missing contract {contract_path}")
        return 1

    try:
        contract = _load_contract(contract_path)
        critical_patterns = [str(item) for item in contract.get("critical_path_patterns", [])]
        docs_path_patterns = [str(item) for item in contract.get("docs_path_patterns", [])]
        code_path_patterns = [str(item) for item in contract.get("code_path_patterns", [])]
        evidence_patterns = [str(item) for item in contract.get("evidence_file_patterns", [])]
        handoff_rules = _parse_handoff_rules(contract.get("required_handoff_sections", []))
        gate_specs = _parse_gate_specs(contract.get("gate_evidence_reports", {}))
        change_type_rules = _parse_change_type_rules(contract.get("change_type_rules", []))
        required_sections_by_type = {
            str(key): [str(item) for item in value]
            for key, value in contract.get("required_sections_by_type", {}).items()
        }
        required_gates_by_type = {
            str(key): [str(item) for item in value]
            for key, value in contract.get("required_gates_by_type", {}).items()
        }
        forbidden_modes_by_type = {
            str(key): [str(item) for item in value]
            for key, value in contract.get("forbidden_modes_by_type", {}).items()
        }
        mode_markers = {
            str(key): [str(item).lower() for item in value]
            for key, value in contract.get("mode_markers", {}).items()
        }
        default_change_type = str(contract.get("default_change_type", "single_domain_code"))
    except Exception as exc:  # noqa: BLE001
        payload = {
            "status": "failed",
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "findings": [
                {
                    "type": "invalid_contract",
                    "detail": str(exc),
                }
            ],
            "critical_paths_touched": [],
        }
        _write_json(output_path, payload)
        print(f"[qa] codex governance guard failed: invalid contract ({exc})")
        return 1

    handoff_rule_map = {rule.section_id: rule for rule in handoff_rules}

    base = _resolve_base(root, args.base_ref)
    changed_files = _changed_files(root, base)

    critical_files = [path for path in changed_files if _matches_any(path, critical_patterns)]
    evidence_files = [path for path in changed_files if _matches_any(path, evidence_patterns)]

    domains_touched = {domain for path in changed_files if (domain := _domain_for_path(path))}
    non_docs_changes = any(not _matches_any(path, docs_path_patterns) for path in changed_files)
    code_changes = any(_matches_any(path, code_path_patterns) for path in changed_files)

    change_type = _classify_change_type(
        changed_files=changed_files,
        domains_touched=domains_touched,
        non_docs_changes=non_docs_changes,
        code_changes=code_changes,
        rules=change_type_rules,
        default_change_type=default_change_type,
    )

    evidence_text_parts: list[str] = []
    missing_evidence_files: list[str] = []
    for rel in evidence_files:
        abs_path = (root / rel).resolve()
        if not abs_path.exists() or abs_path.is_dir():
            missing_evidence_files.append(rel)
            continue
        evidence_text_parts.append(_read_text_file(abs_path))

    evidence_text = "\n".join(evidence_text_parts).lower()

    required_sections = required_sections_by_type.get(change_type, [])
    section_presence: dict[str, bool] = {}
    missing_sections: list[str] = []

    for section_id in required_sections:
        rule = handoff_rule_map.get(section_id)
        if rule is None:
            findings.append(
                {
                    "type": "invalid_contract",
                    "detail": f"required section missing definition: {section_id}",
                }
            )
            section_presence[section_id] = False
            missing_sections.append(section_id)
            continue
        present = any(keyword in evidence_text for keyword in rule.keywords_any)
        section_presence[section_id] = present
        if not present:
            missing_sections.append(section_id)

    if required_sections and not evidence_files:
        findings.append(
            {
                "type": "missing_handoff_evidence",
                "detail": "required sections for this change type need a handoff evidence file in diff",
                "change_type": change_type,
            }
        )

    if missing_sections:
        findings.append(
            {
                "type": "handoff_sections_missing",
                "detail": "handoff evidence does not include all required sections for change type",
                "change_type": change_type,
                "missing_sections": missing_sections,
            }
        )

    required_gates = required_gates_by_type.get(change_type, [])
    missing_gates: set[str] = set()
    failing_gates: set[str] = set()
    gate_checks: dict[str, list[dict[str, Any]]] = {}

    for gate in required_gates:
        specs = gate_specs.get(gate)
        if not specs:
            missing_gates.add(gate)
            gate_checks[gate] = [{"result": "missing_gate_mapping"}]
            continue

        missing_report, failing_status, details = _check_gate_evidence(root=root, gate=gate, specs=specs)
        gate_checks[gate] = details
        if missing_report:
            missing_gates.add(gate)
        if failing_status:
            failing_gates.add(gate)

    if missing_gates:
        findings.append(
            {
                "type": "required_gates_missing",
                "detail": "missing gate evidence reports for required gates",
                "change_type": change_type,
                "missing_gates": sorted(missing_gates),
            }
        )

    if failing_gates:
        findings.append(
            {
                "type": "required_gates_failed",
                "detail": "gate evidence present but status/contents indicate failure",
                "change_type": change_type,
                "failing_gates": sorted(failing_gates),
            }
        )

    declared_modes = {
        mode
        for mode, markers in mode_markers.items()
        if any(marker in evidence_text for marker in markers)
    }
    forbidden_modes = set(forbidden_modes_by_type.get(change_type, []))
    forbidden_mode_hits = sorted(mode for mode in declared_modes if mode in forbidden_modes)
    forbidden_mode_violation = bool(forbidden_mode_hits)

    if forbidden_mode_violation:
        findings.append(
            {
                "type": "forbidden_mode_violation",
                "detail": "handoff evidence declares a forbidden mode for this change type",
                "change_type": change_type,
                "forbidden_modes_detected": forbidden_mode_hits,
            }
        )

    if missing_evidence_files:
        findings.append(
            {
                "type": "missing_evidence_files",
                "detail": "some evidence files from diff do not exist in workspace",
                "files": missing_evidence_files,
            }
        )

    status = "failed" if findings else "passed"
    payload = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "contract_file": str(contract_path.relative_to(root).as_posix()),
        "base_commit": base,
        "change_type": change_type,
        "domains_touched": sorted(domains_touched),
        "changed_files_count": len(changed_files),
        "changed_files": changed_files,
        "critical_paths_touched": critical_files,
        "evidence_files_touched": evidence_files,
        "required_sections": required_sections,
        "handoff_sections": section_presence,
        "missing_sections": missing_sections,
        "required_gates": required_gates,
        "missing_gates": sorted(missing_gates),
        "failing_gates": sorted(failing_gates),
        "gate_checks": gate_checks,
        "declared_modes": sorted(declared_modes),
        "forbidden_modes_for_type": sorted(forbidden_modes),
        "forbidden_mode_violation": forbidden_mode_violation,
        "findings": findings,
    }
    _write_json(output_path, payload)

    if findings:
        print("[qa] codex governance guard failed")
        print(f"[qa] change_type={change_type}")
        for finding in findings:
            print(f"[qa] - {finding.get('type')}: {finding.get('detail')}")
        return 1

    print("[qa] codex governance guard passed")
    print(f"[qa] change_type={change_type} domains={len(domains_touched)} files={len(changed_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
