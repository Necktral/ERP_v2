from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.kernels.reporting.observability import build_reporting_observability
from apps.modulos.dashboard.observability import build_dashboard_observability


class Command(BaseCommand):
    help = "Exporta snapshot operacional de métricas R8 (reporting + dashboard)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--window-hours",
            type=int,
            default=int(getattr(settings, "REPORTING_OBSERVABILITY_WINDOW_HOURS", 24) or 24),
        )
        parser.add_argument(
            "--output",
            type=str,
            default="",
            help="Ruta de salida JSON (opcional).",
        )

    def handle(self, *args, **options):
        window_hours = max(int(options["window_hours"]), 1)
        payload = {
            "generated_at": timezone.now().isoformat(),
            "window_hours": window_hours,
            "reporting": build_reporting_observability(window_hours=window_hours),
            "dashboard": build_dashboard_observability(window_hours=window_hours),
        }

        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"observability snapshot exported to {path}"))
            return

        self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
