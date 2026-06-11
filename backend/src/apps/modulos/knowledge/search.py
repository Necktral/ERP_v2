"""Retrieval DETERMINISTA sobre el índice FTS español (funciona SIEMPRE, sin IA).

`search_docs` rankea por `SearchRank` (websearch: soporta frases y "-exclusiones") y
devuelve fragmentos con su fuente (path + heading) — las CITAS son parte del contrato,
con o sin LLM. Mismo índice + misma consulta → mismos resultados.
"""
from __future__ import annotations

from typing import Any

from django.contrib.postgres.search import SearchHeadline, SearchQuery, SearchRank
from django.db.models import F

from .models import KnowledgeChunk

MAX_RESULTS = 20


def search_docs(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), MAX_RESULTS))
    sq = SearchQuery(query, config="spanish", search_type="websearch")
    qs = (
        KnowledgeChunk.objects.annotate(
            rank=SearchRank(F("search"), sq),
            excerpt=SearchHeadline(
                "content",
                sq,
                config="spanish",
                start_sel="**",
                stop_sel="**",
                max_words=60,
                min_words=20,
            ),
        )
        .filter(search=sq)
        .order_by("-rank", "source_path", "order")[:limit]
    )
    return [
        {
            "source_path": c.source_path,
            "heading": c.heading,
            "excerpt": c.excerpt,
            "rank": round(float(c.rank), 6),
        }
        for c in qs
    ]
