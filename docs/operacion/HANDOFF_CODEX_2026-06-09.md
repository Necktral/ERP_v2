# Handoff para Codex — Ventana 2026-06-09 (Claude, con Codex fuera)

> **Autor:** Claude (Opus 4.8). **Motivo:** el dueño autorizó explícitamente a Claude a hacer
> merges a `master` durante ~2 días de ausencia de Codex, cerrar cabos sueltos y dejar registro.
> Este documento resume **lo que cambió**, **lo que se decidió** y **lo que queda para Codex**.

## TL;DR
- `master` quedó en un estado **verde y consolidado**; **TODO el backlog de Dependabot fue procesado** (0 PRs abiertos).
- Se subieron dependencias **mayores**: Python 3.12, Django 6.0, y el toolchain de frontend a **TypeScript 6 + ESLint 10**.
- Limpieza de git ejecutada (worktrees, ramas remotas/locales absorbidas).
- **Nada pendiente de Dependabot.** Lo que queda es decisión del dueño / trabajo de Codex (abajo).
- **Próxima fase: FRONTEND**, que el dueño arranca en otro chat con Claude.

## Estado de `master`
- HEAD: `3cc7645e`.
- Gates verdes: **QA CI (Gates 1–3)**, **Security CI**, **Supply Chain CI**, **PM Snapshot**.
- **CD Deploy (VPS): ROJO — pre-existente, NO introducido en esta ventana** (ver "Pendientes").

## Lo que se mergeó (todo por PR gateado con CI verde)
Convención usada: consolidar Dependabot en **olas temáticas** (un PR propio por grupo, patrón del PR #61), no PR-por-PR, para no disparar ~19 corridas de CI.

| PR | Contenido | Dependabot cerrados |
|----|-----------|---------------------|
| **#61** | Python 3.10→**3.12** (Dockerfiles dev/prod a `python:3.12-slim`, supply-chain-ci a 3.12) + **Django 5.2→6.0.6** + cryptography 48 + sentry 2.61 + gunicorn 26 | #25, #27, #28, #30 |
| **#62** | 10 **GitHub Actions** a SHAs nuevos pineados (checkout v6, setup-python v6, setup-node v6, upload-artifact v7, github-script v9, build-push v7, login v4, buildx v4, ssh 1.2.5, trivy 0.36) | #45–#54 |
| **#63** | ruff 0.14→**0.15.16** + bandit 1.8→**1.9.4** + fix de deprecación 3.12 de `datetime.utcnow()` | #32, #34 |
| **#65** | **Ola frontend única** (comparten lockfile): @quasar/extras 2, readdirp 5, chokidar 5, prettier 3.8, autoprefixer 10.5 **+ ESLint 10 + TypeScript 6** | #35, #37, #39, #40, #42, #43, #44 |

(Antes de esta ventana ya estaban en `master`: #59 consolidación, #60 coverage, y 7 patch/minor de Dependabot.)

## Notas técnicas que Codex debe conocer
- **action_pin_guard**: solo exige SHA de 40-hex tras `@`; el comentario `# vX.Y.Z` es informativo (se mantuvo por consistencia).
- **`datetime.utcnow()`** (deprecado en 3.12) → `datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"` en `backend/src/apps/kernels/reporting/contracts.py`. Produce **el string idéntico** (`...Z`), sin cambiar contratos.
- **bandit 1.9** ahora interpreta el texto que sigue a `# nosec` como IDs de test (genera WARNINGs). Si agregas `# nosec`, usa solo `# nosec B###` y pon la justificación en un comentario aparte (ver `notifications/senders.py`).
- **Frontend `qa-frontend-ci`**: el job `qa` corre `qa-frontend-ci` dentro de gate1 (`Makefile:287`), que ejecuta `npm ci + lint + typecheck + test + build` en `node:22`. **`qa` verde garantiza que el frontend compila.** Para reproducir local: `docker compose --profile qa run --rm frontend_ci`.
- **TS 6 + ESLint 10 (lo más delicado):** el typescript-eslint nuevo activa `@typescript-eslint/no-unnecessary-type-assertion`, que da **falso positivo** sobre el widening idiomático de literales en Pinia `state`/`reactive` (p. ej. `'light' as UiThemeMode`). Quitar la aserción **degrada el tipo** del contenedor (el `eslint --fix` rompía `ui.store`). Se corrigió con **tipado real, no supresión**:
  - 6 stores Pinia → interfaz de estado explícita: `state: (): XState => ({...})` sin aserciones.
  - 3 reactive forms → `reactive<T>({...})` o constante inicial tipada.
  - 1 aserción genuinamente redundante (`retail-pos-offline-queue.ts`, contenedor ya tipado) eliminada.
  - **No se desactivó ninguna regla de lint.**

## Limpieza de git ejecutada
- **Worktrees removidos** (consolidados, su contenido está en `master`): erp-acct, erp-comisariato, erp-controls, erp-finca, erp-fleet, erp-intercompany, erp-sim, erp-integ, erp-py312, erp-ci, erp-audit. (Dos dirs residuales root-owned se borraron con sudo del dueño.)
- **Ramas remotas borradas** (15, confirmadas ancestros de `master` con `merge-base --is-ancestor`): accounting-period-reopen, comisariato-credito, controls-sod-detection, finca-sync, fleet-fase-b, intercompany-ops, simulacion-spine-completo, finca-basico, finca-field-link, finca-gl-inventory, fleet-fase-a, ci-load-test-readiness-timeout, docs/auditoria-codigo-2026-06, docs/master-roadmap-2026-06-08, integration/consolidacion-2026-06.
- **Ramas locales borradas**: las 15 anteriores + mis ramas de sesión (chore/deps-*, chore/python-3.12-django-6) + dependabot/.../eslint-10.1.0 (22 en total).
- **`backup/*` NO se tocaron.**

## ⚠️ Ramas CONSERVADAS a propósito (Codex debe evaluarlas)
El método `git diff master..rama` **engaña** (el delta grande es sobre todo lo que `master` ganó después). Verificando los **archivos que cada rama tocó** contra `master`, estas **NO están absorbidas limpiamente** (tienen delta real) — por eso **no se borraron**, ni local ni remotamente:

| Rama | Archivos con delta real | Nota |
|------|------------------------|------|
| `feat/nomina-planilla-legal` | 20 | **Corrige un supuesto previo:** NO está absorbida del todo. Worktree vivo: `erp-field`. |
| `feat/org-company-modules` | 5 | Idem. Worktree vivo: `erp-modules`. |
| `fix/auditoria-mainline` | 3 | Worktree vivo: `erp-fix`. |
| `feat/field-attendance-capture` / `audit/field-attendance-backend` | 4 / 5 | Captura de asistencia de campo. |
| `feat/platform-api-rbac-sync-ci-hardening` | 12 | |
| `feat/governance-r8-coverage-domains` | 1 | |
| `fix/security-exceptions-picomatch-expiry` | 2 | |
| `handoff/pc1-necktral-workstate` | 7 | |

**Acción sugerida para Codex:** revisar si ese delta es trabajo útil por integrar (rebasar sobre `master` y abrir PR) o si ya es obsoleto (cerrar). No los borré porque podían tener trabajo no mergeado.

## Pendientes (decisión del dueño / trabajo de Codex)
1. **CD Deploy (VPS) — rojo pre-existente.** Falla en *todos* los pushes (también antes de esta ventana) en "Build + push backend": `invalid tag "ghcr.io/Necktral/..." : repository name must be lowercase`. El owner del tag va con mayúscula y GHCR exige minúsculas. **No afecta el código ni el desarrollo** (es el eslabón de publicar a un servidor real, que en esta fase no se usa — GitHub es solo acceso al código para las IAs). Fix mínimo: pasar el owner a minúsculas en `cd.yml` (p. ej. `${GITHUB_REPOSITORY_OWNER,,}`). El dueño decidió dejarlo por ahora.
2. **~62 ramas locales históricas** (de trabajo previo de Codex) **sin limpiar** — no estorban en GitHub; se dejaron para que Codex decida cuáles conservar.
3. **Cobertura de línea** de los handlers sync nuevos (finca/fleet) — pendiente menor heredado de #59.
4. Worktrees vivos al cierre: `ERP_v2` (master), `ERP_CRM_context_card`, `erp-field`, `erp-fix`, `erp-modules`.

## Convenciones respetadas en esta ventana
`git add` por ruta explícita (nunca `git add .`); excluir `*:Zone.Identifier` y `excel/`; commits atómicos verdes con footer `Co-Authored-By: Claude Opus 4.8`; **todo a `master` por PR gateado por CI** (nunca push directo); remoto `erp_v2`; comunicación con el dueño en español.
