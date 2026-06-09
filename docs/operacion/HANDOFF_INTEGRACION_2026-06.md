# Handoff / Bitácora — Landing del backlog consolidado a master (2026-06-09)

> Ventana sin Codex (~2 días). Claude ejecuta el merge a `master` con autorización explícita del
> propietario, gateado por CI (se mergea solo lo que pasa). Remoto de trabajo:
> `erp_v2 → git@github.com:Necktral/ERP_v2.git`. Punto de retorno: tag `pre-landing-2026-06-09` @ `ab447647`.

## A) Diagnóstico del área
Todo el backlog backend pendiente estaba consolidado en una sola rama de integración
(`integration/consolidacion-2026-06`), construida con merges `--no-ff` de 8 ramas ya verificadas
verde por separado: `fix/auditoria-mainline`, `feat/accounting-period-reopen`,
`feat/controls-sod-detection`, `feat/comisariato-credito`, `feat/intercompany-ops`,
`feat/fleet-fase-b`, `feat/finca-sync` (pila finca-basico→field-link→gl-inventory→sync) y
`feat/simulacion-spine-completo`; más el seed RBAC de inventario (4 endpoints inalcanzables) y los
cierres de auditoría `audit=0` en procurement/reporting/dashboard/notifications. La rama estaba
**sin PR** y **detrás de master por 7 commits (solo docs)**. El único bloqueo de CI confirmado
(vía PR #58, subconjunto de la integración) era el gate `qa-migration-safety-guard`: faltaba
metadata de baseline para migraciones nuevas. La historia de migraciones de nómina en la rama es
**lineal 0001→0012** (la divergencia que tumbó la DB de dev `erp_db` era del linaje de esa DB
concreta, no de la rama).

## B) Alcance exacto
**Incluye** (este landing): refrescar la integración con master (merge de los 7 docs) y ratchetear
los contratos de QA para las migraciones/apps nuevas, dejando la rama lista para PR→master verde.
- `qa/contracts/migration_safety_baseline.json`: +12 entradas (fingerprint + risk_class calculados
  con el propio scanner del guard) — `accounting/0014_fiscalperiod_reopen`, `nomina/0011`, `nomina/0012`,
  `comisariato/0001`+`0002`, `controls/0001`+`0002`, `finca/0001`+`0002`+`0003`, `fleet/0001`,
  `notifications/0001`.
- `qa/contracts/architecture_dependency_baseline.json`: +11 edges legítimos
  (`modulos.compras/dashboard/notifications->modulos.audit` por los cierres audit=0;
  `modulos.integration->kernels.accounting/facturacion/inventarios/nomina/portfolio` y
  `->modulos.hr/parties/rbac` por el driver de simulación del spine).
- Este documento de handoff/bitácora (evidencia de gobernanza).

**Excluye**: los majors de dependabot (Django 6, TS 6, ESLint 10, Quasar/extras 2, cryptography 48,
etc.) → pasada deliberada aparte. La planilla PDF (rama `codex/nomina-planilla-legal-rebase`) y
`feat/org-company-modules` se evalúan como deltas separados tras este landing.

## C) Contratos impactados
- **QA contracts** (solo ratchet aditivo, sin cambiar entradas existentes): migration-safety y
  architecture-dependency baselines.
- **Auditoría** (`apps/modulos/audit/contracts.py`): nuevos event_type/subject/reason de
  procurement/reporting/dashboard/notifications (ya en la rama; aditivo, fail-closed preservado).
- **RBAC** (`apps/modulos/rbac/seed_v01.py`): permisos de inventario sembrados + roles nuevos de
  fleet/finca/controls (ya en la rama).
- **Routing/INSTALLED_APPS** (`config/urls.py`, `config/settings/base.py`): apps nuevas
  (controls, finca, comisariato, intercompany, fleet, notifications) — aditivo.
- Sin cambios de comportamiento contable/fiscal en este landing (solo metadata de gates).

## D) Implementación realizada
1. `git merge erp_v2/master` en la integración (7 commits docs, sin conflicto).
2. Ratchet de migration-safety baseline (+12) reutilizando `_scan_migrations`/`_suggest_risk_class`
   del guard → `qa-migration-safety-guard` PASS (126 migraciones).
3. Ratchet de architecture-dependency baseline (+11 edges) → `qa-architecture-dependency-guard` PASS.
4. Creación de esta evidencia de handoff (satisface `qa-codex-governance-guard` para
   change_type=`migrations_or_close_cycle`).

## E) Pruebas / validación
- Guards host-runnables (DB-free) corridos localmente: namespace, analytics, readme, blast-radius,
  pythonpath, action-pin, required-checks, runner-hygiene, reporting-registry, reporting-version,
  architecture, migration-safety, codex-governance → **PASS**.
- Pendiente en contenedor antes del PR: `ruff`, `mypy`, `makemigrations --check` (debe dar
  *No changes*) y **suite pytest completa** (`--create-db`, slot único).
- En GitHub: `gh pr checks` debe quedar **all green** (qa, security, supply-chain, snapshot,
  ai_review_advisory) antes de mergear. Criterio "a la que pase": no se mergea sin CI verde.

## F) Riesgos remanentes
- La integración nunca corrió CI completa antes; el PR es el primer pase end-to-end. Mitigado con
  verificación local previa (gate1 + suite) y gate de CI antes de mergear.
- Edge stale pre-existente `modulos.sync->modulos.sync_engine` (sync legacy retirado): el guard lo
  reporta como *cleanup opportunity*, **no bloquea**. Limpieza opcional futura.
- Las dos ramas laterales (planilla PDF, org-modules) traen líneas PRE-fix ya superadas por master;
  se landean **solo el delta nuevo** para no regresar (NM-01/02/03/07 + sync legacy retirado).

## Plan de rollback
- Reversión inmediata: el PR se mergea como **merge commit** (preserva historia); revertir =
  `git revert -m 1 <merge_sha>` o reset de `master` al tag `pre-landing-2026-06-09` (@ `ab447647`).
- Las migraciones nuevas son **expand/aditivas** (CreateModel/AddField) salvo
  `comisariato/0002` (AlterField de `credit_limit`, high_lock_risk pero reversible por roll-forward);
  ningún `RemoveField`/`DeleteModel` destructivo. Estrategia declarada: `roll_forward_preferred`.
- La integración ya está pusheada a `erp_v2`; nada es irreversible.

## Estado de gates
- `qa-migration-safety-guard`: **verde** (126 migraciones con metadata).
- `qa-architecture-dependency-guard`: **verde** (175 edges; 1 stale no-bloqueante).
- `qa-codex-governance-guard`: **verde** con esta evidencia.
- Resto de gate1 host: **verde**. Gates de contenedor (ruff/mypy/makemigrations/suite) y los de CI
  (security/supply-chain/snapshot): se confirman **gates en verde** en el PR antes de mergear.
