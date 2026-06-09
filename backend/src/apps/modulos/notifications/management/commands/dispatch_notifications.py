"""Drena OutboxEvents FLEET pendientes y emite notificaciones (idempotente).

Uso (cron sugerido, cada minuto):
    python manage.py dispatch_notifications
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.modulos.notifications.services import dispatch_fleet_notifications


class Command(BaseCommand):
    help = "Consume OutboxEvents FLEET y emite NotificationRecords (in-app en Fase A)."

    def handle(self, *args, **options):
        result = dispatch_fleet_notifications()
        self.stdout.write(
            self.style.SUCCESS(
                f"notifications: processed={result['processed']} emitted={result['emitted']}"
            )
        )
