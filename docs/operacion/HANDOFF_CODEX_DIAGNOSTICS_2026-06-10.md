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

> **`master` LOCAL está adelantado**: ya contiene B-5 (FF). El `master` remoto está en `5abd6518`
> (#73). Al restaurar el acceso: mergear el PR de B-5 **primero**, luego el de CodeUnitEvidence
> (las migraciones están numeradas en orden: 0004 → 0005, sin colisión).

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
2. **Basura sin trackear** `backend/src/apps/modulos/documents/qa/reports/static_scan.txt` (residuo de
   #68): rompe el static-scan LOCAL (contiene el patrón prohibido); untracked → no afecta CI. Limpiar
   aparte (no se borró por no haberlo creado nosotros).

## Siguiente (cuando se decida)
Proveedor LLM real para B-5 (key + presupuesto/observabilidad del gateway de Mundo A; sigue apagado por
defecto); SAST/bandit con dominio; tenant-scoping fino del read API.
