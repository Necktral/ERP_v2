# Handoff a Codex — módulo `diagnostics` (Mundo B) + estado GitHub

> Escrito por Claude (backend) el 2026-06-10. Claude diseña+construye y valida **local**;
> **Codex ejecuta los PR/merge en GitHub** cuando el acceso esté resuelto.

## Situación de GitHub (por qué esto está local)
El token de `gh` empezó a devolver **401** (REST y GraphQL) a mitad de sesión — es el cobro de
**GitHub Enterprise** sobre la org, no un problema del repo. Los merges #70–#73 sí entraron antes de
que cayera. **GitHub queda a un lado**: Claude construye y valida local; Codex hace PR/merge después.

## Estado del módulo `diagnostics` (Mundo B — plataforma de diagnóstico, todo determinista)
Diseño: `docs/design/AI_DIAGNOSTIC_PLATFORM_SPINE_20260610.md`. Principio: *evidencia primero, sin IA;
los gates bloquean; la IA (apagable) al final.*

**YA en `master` remoto (mergeado por PR):**
- **B-1 (#70)** `ErrorEvent` — captura de fallos, dedupe por `stack_hash`, dominio→C1/C2/C3, redacción.
- **B-2 (#71)** `SecurityFinding` (pip/npm, excepciones con vencimiento) **+ KILL SWITCH de IA**.
- **B-3 (#72)** `DiagnosticRun` — causa raíz determinista (el *por qué*).
- **B-4 (#73)** regression-sentinel + gate de release (un C1 abierto bloquea).

**Construido y validado LOCAL, pendiente de PR/merge (en este orden):**
1. **B-5 — motor IA advisory** — rama `feat/diagnostics-ai-advisory` (commit `eeb257c8`, ya pusheada).
   Migración `0004_aiagentrun`. Detrás del kill switch (`flags.ai_features_enabled()`). Default
   heurístico (sin LLM). 55 tests verdes.
2. **CodeUnitEvidence ("¿la línea que falló está testeada?")** — rama `feat/diagnostics-codeunit`
   (stack sobre B-5). Migración `0005`. Ver su commit.
3. **Supervisión determinista (la cola priorizada del "qué falla y por qué")** — rama
   `feat/diagnostics-supervision` (stack sobre CodeUnit). **SIN migración** (agregación sobre los
   modelos existentes). Endpoint `GET /api/diagnostics/supervision/` + command `supervision_report`.
   75 tests verdes (17 nuevos) + contract-guard. Ver detalle abajo.

> **`master` LOCAL está adelantado**: ya contiene B-5 (FF). El `master` remoto está en `5abd6518`
> (#73). Al restaurar el acceso: mergear el PR de B-5 **primero**, luego CodeUnitEvidence, luego
> Supervisión (stack lineal B-5 → CodeUnit → Supervisión; migraciones 0004 → 0005, sin más; sin colisión).

## Supervisión determinista (rama `feat/diagnostics-supervision`)
La pieza que materializa el principio rector *"saber por qué falla es lo fundamental"*: el ledger ya
guardaba **qué** falla (`ErrorEvent`), **por qué** (`DiagnosticRun`) y si la línea está testeada
(`CodeUnitEvidence`), y los gates daban un veredicto **binario**. Faltaba lo que el operador usa a
diario: una **cola priorizada** que responda *qué está fallando AHORA, qué tan grave y por qué*.
- `supervision.py`: `priority_score` DETERMINISTA y **auditable** (riesgo Necktral + estado + frecuencia
  topada + recencia + cobertura de la línea) con su **desglose**; reglas de alerta (`c1_activo`,
  `regresion`, `alta_frecuencia`, `linea_sin_test`); veredicto de salud (`blocked`/`at_risk`/`healthy`)
  que **fusiona el gate de release**; y enlace al `DiagnosticRun` de causa raíz (el *por qué* ya calculado).
- `GET /api/diagnostics/supervision/` (gate `diagnostics.error.read`; lo lee `platform_observer`) con
  `limit` validado (1..100). Command `supervision_report` (`--json`) para cron/pipeline (offline-first,
  no dispara IA ni escribe). **Sin IA, sin migración.**
- Validado local: ruff/mypy verdes; patrón prohibido CLEAN; `makemigrations --check` sin cambios;
  `pytest src/apps/modulos/diagnostics/tests` → 75 verdes; `test_contract_guards.py` verde.

## Aparte: roles RBAC predefinidos (rama `feat/rbac-predefined-roles`)
Rama pusheada (commit propio `cf6247b9`, toca **solo** `rbac/seed_v01.py` + `tests/test_seed_roles.py`).
**No agrega permisos ni migración**: define 5 roles transversales y su mapeo a permisos ya existentes:
- `platform_observer` (observabilidad: ve+diagnostica, NO gobierna IA),
- `ai_steward` (gobierna el kill switch de IA; SoD vs `company_admin`),
- `accountant` (prepara/aprueba drafts, NO postea/cierra/override),
- `collections_officer` (cartera CxC: aplica pagos, NO ajusta/castiga),
- `viewer` (solo lectura ejecutiva; cero ops).

**Dependencia mínima — apila sobre B-5, NO sobre CodeUnit:** el rol `ai_steward` referencia el permiso
`diagnostics.ai_diagnose.run`, que **lo registra B-5** (no existe en #73). Por eso la rama se basa en
`eeb257c8` (B-5). **No** toca nada de CodeUnit (cero referencias a `code_evidence`). Verificado: sobre
#73 el seed hace hard-fail (permiso inexistente); sobre B-5 pasa.

> **Orden de merge:** B-5 **primero**, luego `feat/rbac-predefined-roles` (en cualquier orden respecto a
> CodeUnit; son independientes entre sí). Validado local: ruff/mypy/static-scan verdes;
> `pytest src/apps/modulos/rbac/tests/test_seed_roles.py src/tests/test_onboarding_e2e.py` → 8 verdes.
> `test_seed_roles.py` fija el SoD (afirma lo que cada rol DEBE y NO debe tener) y detecta drift.

## Cómo validar cada rama (compuerta local, sin CI)
En el contenedor Docker canónico (`docker compose exec -T backend`):
- `ruff check backend/src/apps/modulos/diagnostics` → All checks passed.
- `mypy --config-file mypy.ini backend/src/apps/modulos/diagnostics` → Success.
- `python manage.py makemigrations --check --dry-run` → No changes detected.
- `pytest src/apps/modulos/diagnostics/tests src/tests/test_contract_guards.py --create-db` → verde.
- Host: `python3 qa/architecture_dependency_guard.py …` y `qa/migration_safety_guard.py …` → passed.
- Restaurar `qa/reports/` tras correr guards (`git checkout -- qa/reports/`).

## Invariantes de proceso (respetar al hacer PR/merge)
- `git add` por ruta EXPLÍCITA (nunca `git add .`); **NO** incluir el WIP de frontend del usuario
  (lo borró/reestructura aparte) ni `excel/` ni `*:Zone.Identifier` ni `hr/urls.py`.
- Merge solo con CI verde (cuando GitHub vuelva). Commits con footer
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Remoto `erp_v2`. Español siempre.

## Cabos abiertos (no bloquean diagnostics)
1. **Flake preexistente de accounting**: `/api/accounting/periods/close/` da 401 intermitente
   (AUTH_INVALID_TOKEN) en la suite completa, en tests distintos entre corridas; pasa aislado; es de
   la capa auth/transacciones del kernel accounting, **no** de diagnostics. Fix futuro del kernel.
2. ~~Basura sin trackear `documents/qa/reports/static_scan.txt`~~ **LIMPIADO** (2026-06-10 tarde):
   era un report generado (residuo de #68) que rompía el static-scan local; untracked, sin valor.

## Actualización 2026-06-10 (tarde) — GitHub volvió; PRs creados; ola de hardening
- **PRs en GitHub** (todos verdes al cierre): #74 B-5 → #75 CodeUnit → #76 Supervisión → #79 LLM
  (stack lineal) → **#81 hardening** (base #79, la punta del stack). #77 roles RBAC (sobre B-5);
  #78 HR positions y #80 SAST/bandit (independientes sobre master).
- **Orden de merge sugerido:** 74 → 75 → 76 → 79 → 81; #77/#78/#80 en cualquier momento
  (uniones triviales posibles: #77 y #81 tocan `rbac/seed_v01.py`; #80 y #81 tocan `findings.py`
  vs `domain_map.py` — disjuntos, pero el risk de SAST se beneficia de la calibración de #81).
- **#79 incluye fix**: `requests==2.34.2` pineado en `requirements/base.txt` (el CI no lo tenía
  y el backend no arrancaba — ModuleNotFoundError; el dev container lo tenía de rebote).
- **#80 incluye cableado**: `qa-backend-bandit` ahora emite también `qa/reports/bandit.json`
  (mismos flags/excludes, no gatea) — el artefacto que `ingest_security_findings --bandit-report`
  consume; registrado en el run-manifest.
- **#81 (hardening)**: calibración real C1/C2/C3 del mapa de dominios (rbac/accounts/intercompany/
  compras/retail_pos/comisariato/estacion_servicios fuera de C3) + test centinela; API de triage con
  permisos `diagnostics.*.triage` (en `company_admin`); umbrales `DIAGNOSTICS_SPIKE_THRESHOLD`/
  `DIAGNOSTICS_RECENT_WINDOW_HOURS` por env; `captured(source=...)` para errores fuera de HTTP.
  Sin migración. 27 tests nuevos.

## Siguiente (cuando se decida)
Presupuesto/observabilidad del proveedor LLM (gateway de Mundo A; sigue apagado por defecto);
tenant-scoping fino del read API; auditoría EAU de las decisiones de triage (requiere ampliar el
catálogo de `audit/contracts.py`, hoy con WIP del usuario).
