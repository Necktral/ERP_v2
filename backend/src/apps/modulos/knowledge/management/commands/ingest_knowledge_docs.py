from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.modulos.knowledge.ingest import ingest_corpus


class Command(BaseCommand):
    help = (
        "Ingesta la documentación interna (docs/**/*.md + READMEs de módulos) al índice "
        "FTS español del RAG. Idempotente (checksum por archivo); se agenda por cron o "
        "se corre tras actualizar docs. Determinista, sin IA."
    )

    def add_arguments(self, parser):
        parser.add_argument("--root", default=None, help="Raíz del repo (default: BASE_DIR/../..)")

    def handle(self, *args, **options):
        root = Path(options["root"]) if options["root"] else Path(settings.BASE_DIR).parent.parent
        r = ingest_corpus(root=root)
        self.stdout.write(
            self.style.SUCCESS(
                f"Knowledge ingest: vistos={r.files_seen} ingresados={r.files_ingested} "
                f"sin_cambio={r.files_unchanged} podados={r.files_removed} chunks={r.chunks_written}"
            )
        )
