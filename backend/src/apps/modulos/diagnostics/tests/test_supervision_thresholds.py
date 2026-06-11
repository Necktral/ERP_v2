"""Umbrales operativos de la supervisión, configurables por settings/env.

Fijan: el default (spike=20, ventana reciente=24h) y que el override por settings
cambia el comportamiento real (alerta de alta frecuencia y bono de recencia) sin
tocar código. Los PESOS del score siguen siendo constantes de diseño — esto solo
tunea lo que depende del volumen de cada despliegue.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.modulos.diagnostics.models import ErrorEvent
from apps.modulos.diagnostics.supervision import build_supervision_summary, score_error


def _err(**kw: Any) -> ErrorEvent:
    defaults: dict[str, Any] = {
        "exception_type": "ValueError",
        "stack_hash": uuid.uuid4().hex,
        "domain": "payments",
        "risk_class": "C1",
        "status": "open",
    }
    defaults.update(kw)
    return ErrorEvent.objects.create(**defaults)


def _alert_codes(summary: dict[str, Any]) -> set[str]:
    return {a["code"] for a in summary["alerts"]}


@pytest.mark.django_db
def test_spike_default_es_20():
    _err(occurrence_count=19)
    assert "alta_frecuencia" not in _alert_codes(build_supervision_summary())
    ErrorEvent.objects.all().delete()
    _err(occurrence_count=20)
    assert "alta_frecuencia" in _alert_codes(build_supervision_summary())


@pytest.mark.django_db
@override_settings(DIAGNOSTICS_SPIKE_THRESHOLD=3)
def test_spike_configurable_por_settings():
    # Un despliegue de bajo volumen puede bajar el umbral sin tocar código.
    _err(occurrence_count=3)
    assert "alta_frecuencia" in _alert_codes(build_supervision_summary())


@pytest.mark.django_db
@override_settings(DIAGNOSTICS_SPIKE_THRESHOLD=500)
def test_spike_alto_silencia_el_ruido():
    _err(occurrence_count=499)
    assert "alta_frecuencia" not in _alert_codes(build_supervision_summary())


@pytest.mark.django_db
def test_ventana_reciente_default_24h():
    viejo = _err(last_seen_at=timezone.now() - timedelta(hours=30))
    _, factors = score_error(viejo)
    assert factors["recency"] == 0


@pytest.mark.django_db
@override_settings(DIAGNOSTICS_RECENT_WINDOW_HOURS=48)
def test_ventana_reciente_configurable():
    viejo = _err(last_seen_at=timezone.now() - timedelta(hours=30))
    _, factors = score_error(viejo)
    assert factors["recency"] > 0  # con ventana de 48h, 30h sigue siendo "reciente"
