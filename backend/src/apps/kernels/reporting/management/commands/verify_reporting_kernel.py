from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.kernels.reporting.models import ReportDatasetDefinition
from apps.kernels.reporting.registry import list_dataset_specs


class Command(BaseCommand):
    help = "Verifica estado mínimo del reporting kernel."

    def handle(self, *args, **options):
        specs = list_dataset_specs()
        persisted = ReportDatasetDefinition.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"reporting kernel ok: registry={len(specs)} datasets, persisted={persisted}"
            )
        )

