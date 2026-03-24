from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.kernels.reporting.models import ReportDatasetDefinition
from apps.kernels.reporting.registry import list_dataset_specs, to_definition_defaults


class Command(BaseCommand):
    help = "Siembra/actualiza el catálogo de datasets del reporting kernel."

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        updated = 0
        for spec in list_dataset_specs():
            defaults = to_definition_defaults(spec)
            obj, was_created = ReportDatasetDefinition.objects.get_or_create(
                dataset_key=spec.dataset_key,
                defaults=defaults,
            )
            if was_created:
                created += 1
                continue
            changed = False
            for field, value in defaults.items():
                if getattr(obj, field) != value:
                    setattr(obj, field, value)
                    changed = True
            if changed:
                obj.save()
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"reporting catalog seeded (created={created}, updated={updated}, total={len(list_dataset_specs())})"
            )
        )

