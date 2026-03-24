from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Export de datasets desde runs de reporting (R3)."

    def handle(self, *args, **options):
        self.stdout.write("R3 pendiente: export unificado aún no implementado.")

