from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.modulos.diagnostics.gates import evaluate_release_gates


class Command(BaseCommand):
    help = "Evalúa los gates de release sobre el ledger; falla (exit≠0) si hay C1 abierto."

    def handle(self, *args, **options):
        result = evaluate_release_gates()
        counts = result["counts"]
        self.stdout.write(
            f"release-gates: blocked={result['blocked']} "
            f"c1_errors_open={counts['c1_errors_open']} "
            f"c1_findings_open={counts['c1_findings_open']} "
            f"regressions={counts['regressions']}"
        )
        if result["blocked"]:
            raise CommandError("release bloqueado: " + "; ".join(result["blockers"]))
        self.stdout.write(self.style.SUCCESS("release-gates: OK (sin C1 abierto)"))
