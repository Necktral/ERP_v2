"""Evalúa vencimientos de documentos y mantenimientos vencidos, y publica al outbox.

Uso (cron sugerido, diario):
    python manage.py fleet_run_alerts [--company-id N] [--horizon-days 30]
Luego `dispatch_notifications` entrega las notificaciones resultantes.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.modulos.fleet.alerts import run_fleet_alerts
from apps.modulos.iam.models import OrgUnit


class Command(BaseCommand):
    help = "Evalúa documentos por vencer y mantenimientos vencidos → OutboxEvent FLEET."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--horizon-days", type=int, default=30)

    def handle(self, *args, **options):
        companies = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY)
        if options["company_id"]:
            companies = companies.filter(id=options["company_id"])
        total_docs = total_maint = 0
        for company in companies:
            result = run_fleet_alerts(company=company, horizon_days=options["horizon_days"])
            total_docs += len(result["documents"])
            total_maint += len(result["maintenance"])
        self.stdout.write(
            self.style.SUCCESS(f"fleet_run_alerts: documents={total_docs} maintenance={total_maint}")
        )
