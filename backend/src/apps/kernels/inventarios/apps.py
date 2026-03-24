from __future__ import annotations

from django.apps import AppConfig


class InventariosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.kernels.inventarios"
    label = "inventarios"
    verbose_name = "Inventarios"
