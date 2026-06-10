"""Supervisión determinista de fallos por línea de comandos (headless/cron/pipeline).

Imprime la cola priorizada del *qué falla y por qué* sin levantar el API — sirve para un
cron de ops o un paso del pipeline (offline-first: solo necesita la DB). `--json` para
consumo por máquina; sin flags, un resumen legible. No dispara IA ni escribe nada.
"""
from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.modulos.diagnostics.supervision import build_supervision_summary


class Command(BaseCommand):
    help = "Imprime la supervisión determinista de fallos (salud + alertas + cola priorizada)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20, help="Tamaño de la cola (máx 100).")
        parser.add_argument("--json", action="store_true", help="Salida JSON para máquinas.")

    def handle(self, *args, **options):
        limit = max(1, min(int(options["limit"]), 100))
        summary = build_supervision_summary(limit=limit)

        if options["json"]:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, default=str))
            return

        counts = summary["counts"]
        health = summary["health"]
        styler = {
            "blocked": self.style.ERROR,
            "at_risk": self.style.WARNING,
            "healthy": self.style.SUCCESS,
        }.get(health, self.style.NOTICE)
        self.stdout.write(styler(f"supervisión: salud={health}"))
        self.stdout.write(
            f"  activos={counts['total_active']} "
            f"C1={counts['by_risk']['C1']} C2={counts['by_risk']['C2']} C3={counts['by_risk']['C3']} "
            f"regresiones={counts['regressions']} sin_test={counts['uncovered_active']}"
        )

        for alert in summary["alerts"]:
            self.stdout.write(f"  [{alert['level']}] {alert['code']}: {alert['message']}")

        self.stdout.write("  cola priorizada:")
        for item in summary["queue"]:
            why = "con causa" if item["has_diagnosis"] else "sin diagnóstico"
            self.stdout.write(
                f"    #{item['priority_score']:>5} {item['risk_class']} {item['status']:<10} "
                f"{item['exception_type']} @ {item['location'] or item['endpoint']} "
                f"(x{item['occurrence_count']}, {item['coverage_state']}, {why})"
            )
