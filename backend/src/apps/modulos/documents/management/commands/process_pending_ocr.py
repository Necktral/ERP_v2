from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.modulos.documents.services import process_pending_documents


class Command(BaseCommand):
    help = "Procesa con OCR los documentos en estado PENDING_OCR (pipeline IDP, etapa OCR)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        n = process_pending_documents(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"OCR procesado en {n} documento(s)."))
