#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

H3_RE = re.compile(r"^###\s+(.+?)\s*$")
API_TOKEN_RE = re.compile(r"`(/api/[^`]+)`")

SECTION_RULES: dict[str, dict[str, Any]] = {
    "fuel": {
        "prefixes": (
            "/api/fuel/",
            "/api/backend/fuel/",
            "/api/backend/estacion-servicios/",
        ),
        "heading_keywords": ("fuel", "estacion de servicios", "estación de servicios"),
    },
    "reporting": {
        "prefixes": (
            "/api/reporting/",
            "/api/backend/dashboard/",
            "/api/accounting/reports/",
            "/api/metrics/",
            "/api/billing/",
            "/api/legacy/billing/",
        ),
        "heading_keywords": ("reporting", "analytics"),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guard para detectar mezcla de bloques API por heading en README."
    )
    parser.add_argument("--readme", default="README.md", help="Ruta del README a validar")
    parser.add_argument(
        "--output",
        default="qa/reports/readme_section_guard.json",
        help="Ruta de salida del reporte JSON",
    )
    return parser.parse_args()


def _classify_token(token: str) -> str | None:
    for family, rule in SECTION_RULES.items():
        for prefix in rule["prefixes"]:
            if token.startswith(prefix):
                return family
    return None


def _heading_matches(heading: str, keywords: tuple[str, ...]) -> bool:
    lowered = heading.lower()
    return any(keyword in lowered for keyword in keywords)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    readme_path = Path(args.readme).resolve()
    output_path = Path(args.output).resolve()

    if not readme_path.exists():
        payload = {
            "status": "failed",
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "readme": str(readme_path),
            "issues": [{"type": "missing_file", "message": "README no encontrado"}],
        }
        _write_json(output_path, payload)
        print(f"[qa] readme section guard failed: missing {readme_path}")
        return 1

    lines = readme_path.read_text(encoding="utf-8").splitlines()
    current_heading = ""
    issues: list[dict[str, Any]] = []

    for idx, line in enumerate(lines, start=1):
        heading_match = H3_RE.match(line)
        if heading_match:
            current_heading = heading_match.group(1).strip()

        for token in API_TOKEN_RE.findall(line):
            family = _classify_token(token)
            if family is None:
                continue
            keywords = SECTION_RULES[family]["heading_keywords"]
            if _heading_matches(current_heading, keywords):
                continue
            issues.append(
                {
                    "line": idx,
                    "heading": current_heading,
                    "token": token,
                    "expected_family": family,
                    "expected_heading_keywords": list(keywords),
                }
            )

    status = "passed" if not issues else "failed"
    payload = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "readme": str(readme_path),
        "rule_families": {
            key: {
                "prefixes": list(value["prefixes"]),
                "heading_keywords": list(value["heading_keywords"]),
            }
            for key, value in SECTION_RULES.items()
        },
        "issues": issues,
    }
    _write_json(output_path, payload)

    if issues:
        print(f"[qa] readme section guard failed: {len(issues)} issue(s)")
        return 1

    print("[qa] readme section guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
