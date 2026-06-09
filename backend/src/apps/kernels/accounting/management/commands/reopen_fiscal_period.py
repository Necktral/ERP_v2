from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.kernels.accounting.services import reopen_fiscal_period


class Command(BaseCommand):
    help = "Reabre (CLOSED -> OPEN) un periodo fiscal contable con SoD, guarda cronológica y auditoría."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--reason", type=str, required=True)
        parser.add_argument("--force", action="store_true", default=False)
        parser.add_argument("--allow-same-closer", action="store_true", default=False)

    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        year = int(options["year"])
        month = int(options["month"])
        reason = str(options["reason"])
        force = bool(options.get("force", False))
        allow_same_closer = bool(options.get("allow_same_closer", False))

        try:
            result = reopen_fiscal_period(
                company_id=company_id,
                year=year,
                month=month,
                reason=reason,
                force=force,
                allow_same_closer=allow_same_closer,
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc

        payload = {
            "company_id": int(result.company_id),
            "year": int(result.year),
            "month": int(result.month),
            "status": result.status,
            "period_id": int(result.period_id),
            "was_already_open": bool(result.was_already_open),
            "reopened_at": result.reopened_at,
            "reason": result.reason,
            "force_applied": bool(result.force_applied),
        }
        self.stdout.write(json.dumps(payload, ensure_ascii=False))
