"""RAG de documentación interna — el índice vive en Postgres (FTS español, sin vector DB).

`KnowledgeChunk` es un fragmento de un documento markdown del repo (`docs/` + READMEs
de módulos), particionado por headings. La columna `search` (tsvector, índice GIN) la
mantiene la ingesta con configuración `spanish` (stemming: "cierres" matchea "cierre").
El retrieval es DETERMINISTA y funciona siempre; la síntesis LLM es opcional y va
detrás del kill switch (`synthesis.py`).
"""
from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils import timezone


class KnowledgeChunk(models.Model):
    class Meta:
        app_label = "knowledge"
        ordering = ["source_path", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_path", "order"], name="uniq_knowledgechunk_path_order"
            )
        ]
        indexes = [
            GinIndex(fields=["search"], name="gin_knowledgechunk_search"),
            models.Index(fields=["source_path"]),
        ]

    # Identidad del fragmento dentro del corpus.
    source_path = models.CharField(max_length=512)  # path repo-relativo del .md
    heading = models.CharField(max_length=255, blank=True, default="")
    order = models.PositiveIntegerField(default=0)  # posición del chunk en el archivo

    content = models.TextField()
    file_checksum = models.CharField(max_length=64)  # sha256 del archivo fuente completo

    # tsvector mantenido por la ingesta (heading con peso A, content con peso B).
    search = SearchVectorField(null=True)

    ingested_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"KnowledgeChunk({self.source_path}#{self.order} '{self.heading[:40]}')"
