from django.apps import AppConfig


class DiagnosticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.modulos.diagnostics"
    label = "diagnostics"
    verbose_name = "Diagnostics (observabilidad de errores)"

    def ready(self) -> None:
        # Conecta el receiver de `got_request_exception` (captura best-effort).
        from . import capture  # noqa: F401
