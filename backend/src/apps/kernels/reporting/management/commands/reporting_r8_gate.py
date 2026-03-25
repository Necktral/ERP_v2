from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.kernels.reporting.observability import build_reporting_observability


def _parse_date(raw: str, *, field_name: str) -> date:
    try:
        return date.fromisoformat(str(raw).strip())
    except Exception as exc:
        raise ValueError(f"{field_name} inválido (esperado YYYY-MM-DD): {raw}") from exc


@dataclass
class GateSummary:
    generated_at: str
    mode: str
    gate_status: str
    window_hours: int
    warn_until: str
    hard_fail_from: str
    thresholds: dict[str, Any]
    metrics: dict[str, Any]
    failure_class: str
    reasons: list[str]


class Command(BaseCommand):
    help = "Evalúa gate R8 de calidad+SLO sobre runs de reporting (WARN→FAIL)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--window-hours",
            type=int,
            default=int(getattr(settings, "REPORTING_R8_GATE_WINDOW_HOURS", 24) or 24),
        )
        parser.add_argument(
            "--warn-until",
            type=str,
            default=str(getattr(settings, "REPORTING_R8_GATE_WARN_UNTIL", "2026-04-07")),
        )
        parser.add_argument(
            "--hard-fail-from",
            type=str,
            default=str(getattr(settings, "REPORTING_R8_GATE_HARD_FAIL_FROM", "2026-04-08")),
        )
        parser.add_argument("--snapshot-p95-max-ms", type=float, default=800.0)
        parser.add_argument("--near-realtime-p95-max-ms", type=float, default=1500.0)
        parser.add_argument("--error-rate-max-pct", type=float, default=0.5)
        parser.add_argument("--today", type=str, default="", help="Override de fecha para pruebas (YYYY-MM-DD).")
        parser.add_argument("--output", type=str, default="", help="Ruta JSON de salida (opcional).")

    def handle(self, *args, **options):
        window_hours = max(int(options["window_hours"]), 1)
        warn_until = _parse_date(options["warn_until"], field_name="warn_until")
        hard_fail_from = _parse_date(options["hard_fail_from"], field_name="hard_fail_from")
        today_raw = str(options.get("today") or "").strip()
        today = _parse_date(today_raw, field_name="today") if today_raw else timezone.localdate()
        mode = "HARD_FAIL" if today >= hard_fail_from else "WARN"

        report = build_reporting_observability(window_hours=window_hours)
        reasons: list[str] = []
        classes: list[str] = []

        quality_fail = int((report.get("quality_status_counts") or {}).get("FAIL") or 0)
        if quality_fail > 0:
            reasons.append(f"quality_fail_runs={quality_fail}")
            classes.append("quality_breach")

        snapshot_p95 = (report.get("latency_ms_by_policy") or {}).get("SNAPSHOT_REQUIRED", {}).get("p95_ms")
        snapshot_limit = float(options["snapshot_p95_max_ms"])
        if isinstance(snapshot_p95, (int, float)) and float(snapshot_p95) > snapshot_limit:
            reasons.append(f"snapshot_p95_ms={float(snapshot_p95):.2f}>{snapshot_limit:.2f}")
            classes.append("latency_regression")

        near_rt_p95 = (report.get("latency_ms_by_policy") or {}).get("near_realtime_cache", {}).get("p95_ms")
        near_rt_limit = float(options["near_realtime_p95_max_ms"])
        if isinstance(near_rt_p95, (int, float)) and float(near_rt_p95) > near_rt_limit:
            reasons.append(f"near_realtime_cache_p95_ms={float(near_rt_p95):.2f}>{near_rt_limit:.2f}")
            classes.append("latency_regression")

        error_rate_pct = float(report.get("error_rate_pct") or 0.0)
        error_limit = float(options["error_rate_max_pct"])
        if error_rate_pct > error_limit:
            reasons.append(f"error_rate_pct={error_rate_pct:.4f}>{error_limit:.4f}")
            classes.append("error_rate_regression")

        if not reasons:
            gate_status = "PASS"
            failure_class = "none"
            exit_code = 0
        elif mode == "WARN":
            gate_status = "WARN"
            failure_class = classes[0]
            exit_code = 0
        else:
            gate_status = "FAIL"
            failure_class = classes[0]
            exit_code = 2

        summary = GateSummary(
            generated_at=timezone.now().isoformat(),
            mode=mode,
            gate_status=gate_status,
            window_hours=window_hours,
            warn_until=warn_until.isoformat(),
            hard_fail_from=hard_fail_from.isoformat(),
            thresholds={
                "snapshot_p95_max_ms": snapshot_limit,
                "near_realtime_p95_max_ms": near_rt_limit,
                "error_rate_max_pct": error_limit,
            },
            metrics={
                "runs_total": report.get("runs_total"),
                "runs_failed": report.get("runs_failed"),
                "error_rate_pct": report.get("error_rate_pct"),
                "quality_status_counts": report.get("quality_status_counts"),
                "snapshot_p95_ms": snapshot_p95,
                "near_realtime_cache_p95_ms": near_rt_p95,
            },
            failure_class=failure_class,
            reasons=reasons,
        )
        payload = asdict(summary)
        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"reporting_r8_gate summary -> {path}"))
        else:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

        if exit_code != 0:
            raise SystemExit(exit_code)
