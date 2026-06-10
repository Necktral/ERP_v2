from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.modulos.diagnostics.findings import (
    ExceptionRule,
    RawFinding,
    ingest_findings,
    load_exceptions,
    parse_npm_findings,
    parse_pip_findings,
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


class Command(BaseCommand):
    help = (
        "Ingesta hallazgos de seguridad (pip-audit/npm-audit) al ledger SecurityFinding, "
        "aplicando el contrato de excepciones con vencimiento. Determinista, sin IA."
    )

    def add_arguments(self, parser):
        parser.add_argument("--pip-report", default="qa_pip_audit.json")
        parser.add_argument("--npm-report", default="qa_npm_audit.json")
        parser.add_argument("--exceptions", default="qa/contracts/security_exceptions.json")
        parser.add_argument("--root", default=None, help="Raíz del repo (default: BASE_DIR/../..)")

    def handle(self, *args, **options):
        root = Path(options["root"]) if options["root"] else Path(settings.BASE_DIR).parent.parent
        pip_payload = _load_json(root / options["pip_report"])
        npm_payload = _load_json(root / options["npm_report"])
        exc_payload = _load_json(root / options["exceptions"])

        raw: list[RawFinding] = []
        sources: list[str] = []
        if pip_payload:
            raw += parse_pip_findings(pip_payload)
            sources.append("pip")
        if npm_payload:
            raw += parse_npm_findings(npm_payload)
            sources.append("npm")
        exceptions: list[ExceptionRule] = load_exceptions(exc_payload)

        result = ingest_findings(raw_findings=raw, exceptions=exceptions, sources=sources)
        self.stdout.write(
            self.style.SUCCESS(
                f"SecurityFinding ingest: creados={result.created} "
                f"actualizados={result.updated} resueltos={result.resolved} "
                f"fuentes={','.join(result.sources) or '-'}"
            )
        )
