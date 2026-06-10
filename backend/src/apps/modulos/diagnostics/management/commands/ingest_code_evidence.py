from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.modulos.diagnostics.code_evidence import ingest_code_evidence
from apps.modulos.diagnostics.coverage import parse_coverage_xml


class Command(BaseCommand):
    help = (
        "Ingesta cobertura por línea (coverage.xml) → CodeUnitEvidence para las líneas que "
        "fallaron: ¿la línea que falló está testeada? Determinista, sin IA."
    )

    def add_arguments(self, parser):
        parser.add_argument("--coverage-xml", default="qa/reports/coverage.xml")
        parser.add_argument("--root", default=None, help="Raíz del repo (default: BASE_DIR/../..)")

    def handle(self, *args, **options):
        root = Path(options["root"]) if options["root"] else Path(settings.BASE_DIR).parent.parent
        path = root / options["coverage_xml"]
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        cov_map = parse_coverage_xml(text)
        res = ingest_code_evidence(cov_map=cov_map)
        self.stdout.write(
            self.style.SUCCESS(
                f"CodeUnitEvidence: creados={res['created']} actualizados={res['updated']} "
                f"archivos_en_cobertura={len(cov_map)}"
            )
        )
