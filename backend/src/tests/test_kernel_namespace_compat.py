from __future__ import annotations

import importlib

from django.conf import settings


def test_kernels_are_loaded_from_canonical_namespace() -> None:
    installed = set(settings.INSTALLED_APPS)
    assert "apps.kernels.accounting.apps.AccountingConfig" in installed
    assert "apps.kernels.facturacion" in installed
    assert "apps.kernels.inventarios" in installed
    assert "apps.kernels.payments.apps.PaymentsConfig" in installed


def test_modulos_compat_namespace_resolves_to_kernels_modules() -> None:
    module_pairs = (
        ("apps.modulos.accounting.models", "apps.kernels.accounting.models"),
        ("apps.modulos.facturacion.models", "apps.kernels.facturacion.models"),
        ("apps.modulos.inventarios.models", "apps.kernels.inventarios.models"),
        ("apps.modulos.payments.models", "apps.kernels.payments.models"),
    )
    for legacy, canonical in module_pairs:
        assert importlib.import_module(legacy) is importlib.import_module(canonical)
