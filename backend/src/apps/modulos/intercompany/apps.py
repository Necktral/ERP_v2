from __future__ import annotations

from django.apps import AppConfig


class IntercompanyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.modulos.intercompany"
    label = "intercompany"
    verbose_name = "Intercompany (consolidación de grupo)"
