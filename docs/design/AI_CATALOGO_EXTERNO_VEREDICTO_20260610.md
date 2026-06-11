# Veredicto del catálogo externo "IA en ERP" (2026-06-10) — leer ANTES de usarlo

Otra IA entregó un catálogo de ~120 formas de integrar IA en Necktral ("ia en erp.txt",
en poder del dueño). Esta nota fija el veredicto para que NADIE (Codex incluido) lo tome
como plan literal. **El código real manda.**

## Qué vale del catálogo (confirmado contra el repo)
- La espina de gobernanza coincide con nuestro blueprint (`AI_PLATFORM_GOVERNANCE_SPINE_20260610.md`):
  la IA nunca escribe en tablas críticas; propone → humano aprueba → comando de dominio → auditoría;
  niveles L0–L5 con **L5/C1 prohibido**; structured outputs para todo lo que entra al sistema.
- La lista "Lo que NO haría" (sin SQL libre, sin token admin, sin chatbot pegado a la DB) es correcta.
- Rutas con solver (OR-Tools), no con LLM: el solver calcula, el LLM explica. Criterio correcto.
- Referencias externas reales y bien usadas (OWASP GenAI, NIST AI RMF, MCP spec).

## Correcciones (lo que afirma y es FALSO o ya está resuelto)
1. **"El diccionario ya contempla AgentRun/DecisionProduct/ModelEvaluation"** → FALSO en código.
   Solo existen en `docs/archive/`. Verificado en la auditoría de factibilidad
   (`docs/operacion/FACTIBILIDAD_IA_2026-06.md`). El autor leyó documentación vieja, no el repo.
2. **No conoce Mundo B.** Sus ítems de "IA para auditoría/anomalías/PR-review/tests" ya están
   resueltos SIN IA en `apps.modulos.diagnostics` (PRs #70–#81): ledger de errores, supervisión
   priorizada determinista, gates de release, SAST con riesgo por dominio, causa raíz, triage.
   Principio nuestro (mejor que el suyo): *evidencia determinista primero, IA advisory al final*.
3. **Ignora los topes duros del sistema**: offline-first y sin runner async ⇒ voz realtime,
   streaming y agentes de voz en POS (ítems 11-13, 62-63) son inviables hoy; el catálogo
   los lista como opciones normales sin marcarlo.
4. **No menciona el kill switch** (`apps.modulos.diagnostics.flags.ai_features_enabled()` =
   env `AI_FEATURES_ENABLED` **Y** `AIControl` runtime). TODA pieza de IA, de cualquier mundo,
   DEBE chequearlo. Es invariante, no opción.
5. **120 ítems sin priorización por el negocio real** (holding cafetalero, 1 dev backend):
   ganadería, comercio internacional, ChatGPT App, knowledge graphs = especulativo hoy.
   Tomado como roadmap, son años; tomado como menú de referencia, vale.

## Lo que SÍ se toma (decisión del dueño, 2026-06-10)
En orden: **(1) IDP F2** — extracción de campos sobre lo que `documents` F1 ya captura
(determinista primero; LLM detrás del kill switch después del merge train);
**(2) RAG sobre documentación interna** (retrieval determinista + síntesis LLM opcional);
**(3) CEC explainer / paquete contador** (read-only). Conciliación draft-first queda
diferida hasta que la espina económica madure.
