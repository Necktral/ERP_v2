#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate canonical/legacy API route contract.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--output",
        default="qa/reports/route_contract_report.json",
        help="Output report JSON path",
    )
    parser.add_argument(
        "--settings-module",
        default="config.settings.dev",
        help="Django settings module used to inspect URL config",
    )
    return parser.parse_args()


def _normalize_prefix(prefix: str) -> str:
    value = (prefix or "").strip()
    if not value.startswith("/"):
        value = f"/{value}"
    if not value.endswith("/"):
        value = f"{value}/"
    return value


def _module_name(urlconf_name: object) -> str:
    if isinstance(urlconf_name, str):
        return urlconf_name
    return str(getattr(urlconf_name, "__name__", type(urlconf_name).__name__))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    output_path = (root / args.output).resolve()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", args.settings_module)

    import django
    from django.conf import settings
    from django.urls.resolvers import URLResolver

    django.setup()

    from config import urls as project_urls
    from config.routing_policy import legacy_header_config, routing_prefix_contract

    top_level_rows: list[dict[str, str]] = []
    prefix_to_modules: dict[str, list[str]] = defaultdict(list)
    module_to_prefixes: dict[str, set[str]] = defaultdict(set)

    for item in project_urls.urlpatterns:
        if not isinstance(item, URLResolver):
            continue
        prefix = _normalize_prefix(str(item.pattern))
        module = _module_name(item.urlconf_name)
        top_level_rows.append({"prefix": prefix, "module": module})
        prefix_to_modules[prefix].append(module)
        module_to_prefixes[module].add(prefix)

    policy = routing_prefix_contract()
    legacy_cfg = legacy_header_config(settings)

    issues: list[str] = []
    warnings: list[str] = []

    for prefix, modules in sorted(prefix_to_modules.items()):
        if len(modules) > 1:
            issues.append(
                f"duplicate include prefix '{prefix}' maps to multiple modules: {modules}"
            )

    policy_module_map: dict[str, dict[str, object]] = {}
    for domain_key, row in policy.items():
        include_modules = row.get("include_modules", []) or []
        canonical_prefix = str(row.get("canonical_prefix", ""))
        legacy_prefixes = set(row.get("allowed_legacy_prefixes", []) or [])
        for module in include_modules:
            policy_module_map[str(module)] = {
                "domain_key": domain_key,
                "canonical_prefix": canonical_prefix,
                "legacy_prefixes": legacy_prefixes,
            }

    for domain_key, row in sorted(policy.items()):
        canonical_prefix = str(row.get("canonical_prefix", "")).strip()
        if canonical_prefix and canonical_prefix not in prefix_to_modules:
            include_modules = row.get("include_modules", []) or []
            if include_modules:
                issues.append(
                    f"{domain_key}: canonical prefix '{canonical_prefix}' missing from top-level urls"
                )

        for legacy_prefix in row.get("allowed_legacy_prefixes", []) or []:
            if legacy_prefix not in legacy_cfg:
                issues.append(f"{domain_key}: legacy prefix '{legacy_prefix}' missing in deprecation header config")

    for module, prefixes in sorted(module_to_prefixes.items()):
        if module == "list":
            continue
        if len(prefixes) <= 1:
            continue
        policy_row = policy_module_map.get(module)
        if policy_row is None:
            issues.append(
                f"module '{module}' mounted on multiple prefixes without routing policy declaration: {sorted(prefixes)}"
            )
            continue
        canonical_prefix = str(policy_row["canonical_prefix"])
        legacy_prefixes = set(policy_row["legacy_prefixes"])
        if canonical_prefix not in prefixes:
            issues.append(
                f"module '{module}' missing canonical prefix '{canonical_prefix}' (found={sorted(prefixes)})"
            )
        undeclared_aliases = sorted(prefixes - {canonical_prefix} - legacy_prefixes)
        if undeclared_aliases:
            issues.append(
                f"module '{module}' has undeclared legacy aliases: {undeclared_aliases}"
            )
        declared_but_missing = sorted(legacy_prefixes - prefixes)
        if declared_but_missing:
            warnings.append(
                f"module '{module}' has policy legacy prefixes not mounted: {declared_but_missing}"
            )

    status = "failed" if issues else "passed"
    payload = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "top_level_routes": sorted(top_level_rows, key=lambda row: (row["prefix"], row["module"])),
        "policy": policy,
        "legacy_header_prefixes": sorted(legacy_cfg.keys()),
        "issues": issues,
        "warnings": warnings,
    }
    _write_json(output_path, payload)

    if issues:
        print("[qa] route contract guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] route contract guard passed")
    for warning in warnings:
        print(f"[qa] warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
