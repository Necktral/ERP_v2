from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Warm-up de snapshots de reporting (R4)."

    def handle(self, *args, **options):
        self.stdout.write("R4 pendiente: snapshots/materialization aún no implementados.")

