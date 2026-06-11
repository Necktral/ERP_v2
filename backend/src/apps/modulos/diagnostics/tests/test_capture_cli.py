"""Tests de `captured(source=...)`: la puerta al ledger FUERA del ciclo HTTP.

Fijan: que el fallo se registra con origen visible (endpoint=source, method="CLI"),
que SIEMPRE se re-lanza (la captura observa, no se traga errores), que respeta el
interruptor del subsistema, que es best-effort (un fallo de la captura no reemplaza
al original) y que dedupea por stack_hash como cualquier otro error.
"""
from __future__ import annotations

import pytest

from apps.modulos.diagnostics import capture as capture_mod
from apps.modulos.diagnostics.capture import captured
from apps.modulos.diagnostics.models import ErrorEvent


def _boom() -> None:
    raise RuntimeError("falla-de-comando")


@pytest.mark.django_db
def test_registra_con_origen_y_relanza():
    with pytest.raises(RuntimeError):
        with captured(source="command:cerrar_planilla"):
            _boom()
    ev = ErrorEvent.objects.get()
    assert ev.endpoint == "command:cerrar_planilla"
    assert ev.method == "CLI"
    assert ev.exception_type == "RuntimeError"


@pytest.mark.django_db
def test_sin_fallo_no_registra_nada():
    with captured(source="command:ok"):
        pass
    assert ErrorEvent.objects.count() == 0


@pytest.mark.django_db
def test_respeta_el_interruptor_del_subsistema(monkeypatch):
    monkeypatch.setattr(capture_mod, "diagnostics_enabled", lambda: False)
    with pytest.raises(RuntimeError):
        with captured(source="command:apagado"):
            _boom()
    assert ErrorEvent.objects.count() == 0


@pytest.mark.django_db
def test_best_effort_el_fallo_original_no_se_reemplaza(monkeypatch):
    from apps.modulos.diagnostics import services as svc

    def _captura_rota(**kwargs):
        raise OSError("la captura misma falló")

    monkeypatch.setattr(svc, "record_error_event", _captura_rota)
    # El error ORIGINAL (RuntimeError) debe propagarse, no el OSError de la captura.
    with pytest.raises(RuntimeError, match="falla-de-comando"):
        with captured(source="command:x"):
            _boom()


@pytest.mark.django_db
def test_dedupea_por_stack_hash():
    for _ in range(2):
        with pytest.raises(RuntimeError):
            with captured(source="command:repetido"):
                _boom()
    ev = ErrorEvent.objects.get()
    assert ev.occurrence_count == 2
