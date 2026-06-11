from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.modulos.knowledge"
    label = "knowledge"
    verbose_name = "Knowledge (RAG de documentación interna)"
