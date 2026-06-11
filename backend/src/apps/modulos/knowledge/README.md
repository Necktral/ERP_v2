# Módulo `knowledge` — RAG de documentación interna

Búsqueda sobre la documentación del repo (`docs/**/*.md` + READMEs de módulos + README raíz)
con **retrieval determinista que funciona SIEMPRE** y síntesis LLM **opcional** detrás del
kill switch. Segundo slice de Mundo A (tras IDP F2), decidido sobre el catálogo externo
(`docs/design/AI_CATALOGO_EXTERNO_VEREDICTO_20260610.md`).

## Arquitectura (nada nuevo que instalar)
- **Índice = tablas en el MISMO Postgres** del compose: FTS nativo en **español**
  (`tsvector` + GIN; stemming: "cierres" encuentra "cierre"). Sin vector DB, sin servicio nuevo.
- **LLM**: el mismo enchufe OpenAI-compat de diagnostics — `KNOWLEDGE_LLM_BASE_URL` (vacío
  hereda `DIAGNOSTICS_LLM_BASE_URL`: un solo llama-server local sirve a ambos). El contenedor
  llega al host por `host.docker.internal`.

## Pipeline
```
docs/*.md ──ingest_knowledge_docs──▶ KnowledgeChunk (chunk por heading, checksum, tsvector)
                                          │
GET /api/knowledge/search/?q=...  ──▶ retrieval determinista (rank + extracto + FUENTE)
                  └─ &synthesize=1 ──▶ + respuesta LLM con citas [n] SI el kill switch está ON
                                       (apagado/caído ⇒ answer=null y los resultados quedan)
```

## Reglas duras
- Las **citas** (path + heading) son parte del contrato, con o sin LLM.
- La síntesis usa SOLO los fragmentos recuperados; si no alcanzan: "La documentación no cubre esto."
- La IA jamás es requisito: kill switch OFF ⇒ buscador útil igual.

## API
| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/api/knowledge/search/?q=&limit=&synthesize=` | `knowledge.docs.read` | Busca; con `synthesize=1` intenta síntesis con citas. |

## Operación
- `python manage.py ingest_knowledge_docs` — idempotente (checksum por archivo, poda los
  borrados); correr tras actualizar docs (cron o post-merge).
