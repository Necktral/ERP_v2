from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission

from .search import search_docs
from .synthesis import synthesize_answer


class KnowledgeSearchView(APIView):
    """RAG de documentación interna: retrieval determinista SIEMPRE; síntesis opcional.

    `GET ?q=...&limit=8&synthesize=1` — los resultados traen fuente (path + heading) y
    extracto resaltado. Con `synthesize=1` Y el kill switch encendido, `answer` trae la
    respuesta del LLM con citas [n]; si la IA está apagada o falla, `answer` es null y
    los resultados deterministas quedan igual (la búsqueda nunca depende de la IA).
    """

    permission_classes = [rbac_permission("knowledge.docs.read")]

    def get(self, request):
        query = (request.query_params.get("q") or "").strip()
        if not query:
            return Response({"detail": "q requerido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            limit = int(request.query_params.get("limit", "8"))
        except (TypeError, ValueError):
            return Response({"detail": "limit debe ser entero."}, status=status.HTTP_400_BAD_REQUEST)

        results = search_docs(query, limit=limit)
        answer = None
        if request.query_params.get("synthesize") in ("1", "true"):
            answer = synthesize_answer(query, results)
        return Response(
            {
                "query": query,
                "results": results,
                "answer": answer,
                "ai_used": answer is not None,
            },
            status=status.HTTP_200_OK,
        )
