# Codex Handoff — ERP_v2 (estado 2026-06-07)

Orientaciones para Codex (ejecuta git/PRs/merges). Claude diseña/construye en worktrees aislados; **no** hace push/merge.

## 0. Reglas de oro (leer primero)
- **Repo home: `Necktral/ERP_v2`** (remote `erp_v2`). ⚠️ `origin = Necktral/Necktral` está **ABANDONADO** y `gh` resuelve ahí por defecto → **usar siempre `gh ... --repo Necktral/ERP_v2`**.
- `master` real = `erp_v2/master` (hoy `35985b7e`, Merge PR #22).
- **NO tocar** el working tree `/home/necktral/erp-field` (worktree de Claude, rama `feat/nomina-planilla-legal`) ni `/home/necktral/erp-ci`.
- Higiene: commits atómicos y verdes; `git add` por ruta explícita; **nunca `git add .`**; excluir `excel/` y `*:Zone.Identifier`.
- Verificación en Docker (runbook): contenedor one-off con `--entrypoint bash` para saltar el entrypoint; settings `config.settings.test`, `PYTHONPATH=backend/src`, slot de DB único.

---

## 1. LISTO YA — fix del job `load-test` (solo push + PR)
Rama **`chore/ci-load-test-readiness-timeout`** @ `9bf5bfe6` (worktree local `/home/necktral/erp-ci`, **sin push**). Cambio: sube el wait de "Wait for backend readiness" de `30x2s`→`120x2s` (240s) en `.github/workflows/auth-load-simulation.yml`. Único check rojo de #14.

```bash
git -C /home/necktral/erp-ci push erp_v2 chore/ci-load-test-readiness-timeout
gh pr create --repo Necktral/ERP_v2 --base master \
  --head chore/ci-load-test-readiness-timeout \
  --title "ci(load-test): subir wait de readiness a 240s" \
  --body "Fix del único check rojo de #14: el backend no llega a healthy en 60s en runner frío."
```
**Después de mergear:** en #14 hacer `merge master` (sin código) para que su check `load-test` re-corra con 240s.

---

## 2. Consolidar NÓMINA a master (Capa 0) — orden de dependencias
Toda la **Capa 1 (ciclo nómina)** está construida y verde en el worktree de Claude `feat/nomina-planilla-legal` @ `1f58728f` (~25 commits, suite nómina 101 verde + 1 skip de PDF). **No está pusheada todavía** → para que Codex pueda abrir su PR, **pedir a Claude/usuario `git push erp_v2 feat/nomina-planilla-legal`**.

Orden de aterrizaje (cada rama es base de la siguiente):
1. **#16** `audit/field-attendance-backend` → master.
2. **`feat/nomina-planilla-legal`** (Claude) → base `audit/field-attendance-backend`. Contiene: controles asistencia + puente→planilla + régimen INSS + séptimo día + export xlsx + **PDF** + U4 nómina→GL + U5 pagos/cierre + abono→portfolio + **feriados** + **AttendanceReport rollup** + **endpoints HTTP (campo + INSS)**.
3. **#17** `feat/field-attendance-capture`.
4. **#15** `feat/platform-api-rbac-sync-ci-hardening` (`/api/v1/` + retira HMAC legacy). ⚠️ Mis endpoints de nómina se montan en `api/nomina/...` (esquema actual); al mergear #15, **reubicar el prefijo global** — no hay rutas que reescribir, solo el include.
5. **#14** `feat/governance-r8-coverage-domains` (coverage guard).

---

## 3. Deuda de ARQUITECTURA (ratchet) — al aterrizar nómina
En `qa/contracts/architecture_dependency_baseline.json`, declarar los **edges nuevos** de `kernels.nomina` (hoy el baseline está viejo, nómina/portfolio con 0 edges):
- `kernels.nomina -> modulos.audit` (write_event, ya existía de facto).
- `kernels.nomina -> kernels.accounting` (U4: asiento nómina→GL).
- `kernels.nomina -> kernels.portfolio` (abono de préstamos de planilla).
- `kernels.nomina -> modulos.iam` (approvals: SoD maker-checker de aprobación de campo).
- `kernels.nomina -> modulos.hr` (Employee).
Correr el guard de arquitectura y subir el baseline en el mismo PR que mergea nómina.

---

## 4. B2 PDF de planilla — REBUILD de imagen obligatorio
- `requirements/base.txt` ahora trae `weasyprint==62.3` **y `pydyf==0.10.0` PINEADO** (weasyprint 62.3 rompe con `pydyf>=0.11`: `'super' object has no attribute 'transform'`). **No "actualizar" pydyf.**
- `docker/backend.Dockerfile.dev` y `.prod` ya incluyen libpango/libpangocairo/libgdk-pixbuf + shared-mime-info + fonts-dejavu-core.
- **Tras aterrizar nómina: `docker compose build backend`** (y en deploy, rebuild de la imagen). Sin rebuild, el endpoint `planilla.pdf` da 500 al renderizar (la lib no está en la imagen viva). La lógica HTML y el endpoint ya están testeados; el render real va tras `importorskip`.

---

## 5. Deuda menor (limpiar cuando convenga, fuera del scope de nómina)
- **ruff F401** en `backend/src/apps/kernels/nomina/tests/test_nomina_services.py`: 4 imports sin usar (`DEFAULT_INSS_PATRONAL_LARGE`, `NominaConfig`, `PayrollPeriod`, `PayrollSheet`). Pre-existente; no lo tocó Claude por gobernanza.
- **Cuentas CoA** del asiento U4 (defaults 6201…2308) → ajustar al catálogo real con el contador/junta.

---

## 6. Checklist de verificación por merge (DoD)
- Tests del módulo verdes (pytest en contenedor one-off).
- `makemigrations --check --dry-run` sin cambios.
- `ruff check` limpio en lo tocado.
- Guard de arquitectura verde (con baseline actualizado si entró nómina).
