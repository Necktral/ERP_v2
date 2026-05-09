from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.modulos.integration.services import collect_outbox_health, dispatch_outbox_events


class Command(BaseCommand):
    help = "Despacha eventos pendientes del outbox con politica de retry/DLQ."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--source-module", type=str, default="")
        parser.add_argument("--max-attempts", type=int, default=5)
        parser.add_argument("--json", action="store_true", default=False)
        parser.add_argument("--health-only", action="store_true", default=False)
        parser.add_argument("--no-local-consumers", action="store_true", default=False)

    def handle(self, *args, **options):
        source_module = str(options.get("source_module") or "").strip()
        health_before = collect_outbox_health(source_module=source_module)

        if bool(options.get("health_only", False)):
            if bool(options.get("json", False)):
                self.stdout.write(json.dumps(health_before.as_dict(), ensure_ascii=False, sort_keys=True))
                return
            self.stdout.write(
                "outbox health: "
                f"pending={health_before.pending_count} "
                f"dispatchable={health_before.dispatchable_pending_count} "
                f"retry={health_before.retry_count} failed={health_before.failed_count} "
                f"oldest_pending_age_seconds={health_before.oldest_pending_age_seconds}"
            )
            return

        summary = dispatch_outbox_events(
            limit=int(options["limit"]),
            source_module=source_module,
            max_attempts=int(options.get("max_attempts") or 5),
            allow_noop_for_operational_events=bool(options.get("no_local_consumers", False)),
        )
        health_after = collect_outbox_health(source_module=source_module)
        if bool(options.get("json", False)):
            self.stdout.write(
                json.dumps(
                    {
                        "dispatch": {
                            "attempted": int(summary.attempted),
                            "sent": int(summary.sent),
                            "retried": int(summary.retried),
                            "failed": int(summary.failed),
                        },
                        "health_before": health_before.as_dict(),
                        "health_after": health_after.as_dict(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                "outbox dispatched: "
                f"attempted={summary.attempted} sent={summary.sent} "
                f"retried={summary.retried} failed={summary.failed} "
                f"pending={health_after.pending_count} retry={health_after.retry_count} "
                f"failed_total={health_after.failed_count} "
                f"oldest_pending_age_seconds={health_after.oldest_pending_age_seconds}"
            )
        )
