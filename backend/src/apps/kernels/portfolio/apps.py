"""
Portfolio Kernel App Configuration
"""
from django.apps import AppConfig


class PortfolioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.kernels.portfolio"
    verbose_name = "Financial Portfolio"

    def ready(self):
        """Import signals and register event handlers"""
        # Signals are intentionally not registered in this kernel.
        pass
