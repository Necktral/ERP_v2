# Codex Handoff — ERP_v2 (estado 2026-06-07, post-merge #16)

Orientaciones para Codex (ejecuta git/PRs/merges). Claude diseña/construye en worktrees aislados; **no** hace push/merge.

## 0. Reglas de oro (leer primero)
- **Repo home: `Necktral/ERP_v2`** (remote `erp_v2`). ⚠️ `origin = Necktral/Necktral` está **ABANDONADO** y `gh` resuelve ahí por defecto → **usar siempre `gh ... --repo Necktral/ERP_v2`** y `git push erp_v2 ...` (nunca `origin`).
- **`master` real = `erp_v2/master` @ `f4b0ffa`** (`[codex] Add field attendance backend foundation (#16)`). Contiene #16 y #23.
- **NO tocar** los working trees de Claude: `/home/necktral/erp-field` (`feat/nomina-planilla-legal`), `/home/necktral/erp-ci`, ni `/home/necktral/ERP_v2` (rama `handoff/pc1-necktral-workstate`, donde viven ROADMAP.md/CLAUDE.md/este doc).
- Higiene: commits atómicos y verdes; `git add` por ruta explícita; **nunca `git add .`**; excluir `excel/` y `*:Zone.Identifier`.
- Verificación en Docker (runbook): contenedor one-off con `--entrypoint bash` (salta el entrypoint); settings `config.settings.test`, `PYTHONPATH=backend/src`, slot de DB único.

---

## 1. HECHO ✅ (no requiere acción)
- **#16** `audit/field-attendance-backend` → **mergeado** a master (squash, `f4b0ffa`). head mergeado real = `61406344`.
- **#23** `chore/ci-load-test-readiness-timeout` → **mergeado** (`4e5da59`): subió el wait de readiness del job `load-test` a `120x2s`=240s.
- **#14** ya puede re-correr `load-test` verde tras `merge master`.

---

## 2. ACCIÓN PRINCIPAL — aterrizar NÓMINA (Capa 1 completa) a master
Toda la **Capa 1 (ciclo nómina)** está construida y verde, **ya pusheada**: `erp_v2/feat/nomina-planilla-legal` @ `1f58728f` (23 commits de nómina; suite nómina 101 verde + 1 skip de PDF). Contiene: controles asistencia + puente→planilla + régimen INSS + séptimo día + export xlsx + **PDF** + U4 nómina→GL + U5 pagos/cierre + abono→portfolio + **feriados** + **AttendanceReport rollup** + **endpoints HTTP (campo + INSS)**.

⚠️ **Ojo squash:** #16 se mergeó con **SQUASH** → los commits originales de `audit/field-attendance-backend` **no están en la ancestría de master** (master tiene el squash `f4b0ffa`). La rama de nómina está basada en `audit/field-attendance-backend` (base local de Claude @ `893a785e`, **atrasada** vs el head mergeado `61406344`). Si se abre el PR tal cual, el diff arrastraría la base de audit → ruido/conflictos.

**Camino limpio:**
```bash
# Replantar SOLO los 23 commits de nómina sobre el master nuevo (descarta la base ya squasheada)
git fetch erp_v2
git switch feat/nomina-planilla-legal        # o checkout del ref remoto
git rebase --onto erp_v2/master 893a785e feat/nomina-planilla-legal
#   (el squash preserva el árbol de audit → debería aplicar limpio; resolver conflictos menores
#    si los hay en migraciones nomina 0004 / test_field_attendance_services.py)
# Verificar verde (runbook docker): pytest apps/kernels/nomina + makemigrations --check + ruff
git push --force-with-lease erp_v2 feat/nomina-planilla-legal
gh pr create --repo Necktral/ERP_v2 --base master --head feat/nomina-planilla-legal \
  --title "feat(nomina): Capa 1 — ciclo de planilla legal completo" \
  --body "Asistencia→planilla→GL→pagos + INSS + feriados + AttendanceReport + endpoints HTTP + xlsx/PDF."
```
En ese mismo PR: **actualizar el ratchet** (sección 3). Tras merge: **rebuild de imagen** (sección 4).

---

## 3. Resto del stack (después de nómina, en orden de base)
- **#17** `feat/field-attendance-capture`.
- **#15** `feat/platform-api-rbac-sync-ci-hardening` (`/api/v1/` + retira HMAC legacy). ⚠️ Los endpoints de nómina se montan en `api/nomina/...` (esquema actual); al mergear #15, **reubicar el prefijo global** (solo el include, no hay rutas que reescribir).
- **#14** `feat/governance-r8-coverage-domains` (coverage guard) — solo bloqueaba `load-test` (ya resuelto).

---

## 4. Deuda de ARQUITECTURA (ratchet) — en el PR que mergea nómina
En `qa/contracts/architecture_dependency_baseline.json` declarar los **edges nuevos** de `kernels.nomina` (baseline viejo: nómina/portfolio con 0 edges):
- `kernels.nomina -> modulos.audit` (write_event).
- `kernels.nomina -> kernels.accounting` (U4: asiento nómina→GL).
- `kernels.nomina -> kernels.portfolio` (abono de préstamos de planilla).
- `kernels.nomina -> modulos.iam` (approvals: SoD maker-checker de aprobación de campo).
- `kernels.nomina -> modulos.hr` (Employee).
Correr el guard de arquitectura y subir el baseline en el mismo PR.

---

## 5. B2 PDF — REBUILD de imagen obligatorio (tras aterrizar nómina)
- `requirements/base.txt` trae `weasyprint==62.3` **y `pydyf==0.10.0` PINEADO** (weasyprint 62.3 rompe con `pydyf>=0.11`: `'super' object has no attribute 'transform'`). **No "actualizar" pydyf.**
- `docker/backend.Dockerfile.dev` y `.prod` ya incluyen libpango/libpangocairo/libgdk-pixbuf + shared-mime-info + fonts-dejavu-core.
- **`docker compose build backend`** (y rebuild en deploy). Sin rebuild, el endpoint `planilla.pdf` da 500 (lib ausente). La lógica HTML y el endpoint ya están testeados; el render real va tras `importorskip` (verificado en contenedor con el par pineado → produce `%PDF`).

---

## 6. Deuda menor (cuando convenga, fuera del scope de nómina)
- **ruff F401** en `backend/src/apps/kernels/nomina/tests/test_nomina_services.py`: 4 imports sin usar (`DEFAULT_INSS_PATRONAL_LARGE`, `NominaConfig`, `PayrollPeriod`, `PayrollSheet`). Pre-existente; no lo tocó Claude por gobernanza.
- **Cuentas CoA** del asiento U4 (defaults 6201…2308) → ajustar al catálogo real con el contador/junta.
- Ramas locales `feat/pr*`/`fix/*` con upstream `gone` = ruido histórico (limpiar opcional). ~25 PRs de Dependabot abiertos = fuera de scope.

---

## 7. Checklist de verificación por merge (DoD)
- Tests del módulo verdes (pytest en contenedor one-off).
- `makemigrations --check --dry-run` sin cambios.
- `ruff check` limpio en lo tocado.
- Guard de arquitectura verde (con baseline actualizado si entró nómina).
