# ERP_v2 — Roadmap activo

## Estados
- `[DOING]` → en ejecución ahora (solo UNO a la vez)
- `[DONE]`  → terminado y commiteado
- `[TODO]`  → próximo en la fila
- `[BLOCKED]` → esperando algo externo

## Jerarquía de ensamblaje (orden de importancia)
**Capa 0 Consolidar** → **Capa 1 Ciclo nómina** → **Capa 2 Datos reales** → **Capa 3 Control/anti-fraude** → **Capa 4 Columna económica/visibilidad** → **Capa 5 Frontend/móvil** → **Capa 6 Módulos futuros.**
Se baja por capas: no se sube de capa sin cerrar (o decidir saltar) la anterior.

---

## CAPA 0 — Consolidar lo construido (que master diga la verdad)
Riesgo real: trabajo terminado y verde pero FUERA de master. **Los merges/PRs (git) los ejecuta CODEX**, no Claude (Claude diseña/construye en worktree aislado `erp-field`; Codex aterriza a master).

- [DONE] Sesión 2026-06-07 — rama aislada `feat/nomina-planilla-legal` (worktree `/home/necktral/erp-field`), ~120 tests verdes:
  - [DONE] Field attendance — controles: SoD aprobación, IR CATORCENA ×26, `has_inss` real, `day_value` traslados, RBAC `nomina.field.*` · `96ca636d`
  - [DONE] Puente asistencia → planilla (`apply_field_attendance_to_*`) · `3cdd2c95`
  - [DONE] Régimen INSS: afiliación fechada + elección por período + **auto-clasificación CON/SIN INSS** + SoD período · `bce363a7`
  - [DONE] **Séptimo día** + feriados + `salary_type=DAILY` + base INSS correcta (Fase A) · `741934db`
  - [DONE] Export **planilla legal .xlsx** (todas las casillas + grupos + firmas) · `23f33a98`
- [TODO] Aterrizar `feat/nomina-planilla-legal` → master (review + merge; sobre `audit/field-attendance-backend`)
- [TODO] Phantom coverage: commit de tests no trackeados (nomina, compras, org, dashboard, retail_pos, test_contract_guards)
- [TODO] Merge `fix/security-exceptions-picomatch-expiry` → master
- [TODO] Merge `chore/qa-architecture-dependency-ratchet` → master
- [TODO] Merge `feat/governance-r8-coverage-domains` → master
- [TODO] Merge `audit/field-attendance-backend` (base de mi rama) + `feat/field-attendance-capture`
- [TODO] API versioning: merge `feat/platform-api-rbac-sync-ci-hardening` (`/api/v1/`, 41 archivos, requiere CI verde)
- [TODO] QA gates: resolver `qa-security` vs `qa-final-static-scan`; verificar coverage gates post-merge
- [TODO] (lint, fuera de scope) `ruff F401` imports sin usar en `apps/kernels/nomina/tests/test_nomina_services.py` (DEFAULT_INSS_PATRONAL_LARGE, NominaConfig, PayrollPeriod, PayrollSheet) — detectado al construir el rollup; NO tocado por gobernanza §5.
- [TODO] **Ratchet de arquitectura**: al mergear el trabajo de nómina, declarar en `architecture_dependency_baseline.json` los edges nuevos: `kernels.nomina->modulos.audit/integration`, `kernels.nomina->kernels.accounting` (U4), `kernels.nomina->kernels.portfolio` (abono). nómina/portfolio hoy tienen 0 edges en el baseline (quedó viejo).

## CAPA 1 — Completar el ciclo de NÓMINA (corazón operativo)
Spine: **asistencia → planilla → contabilidad → pagos**. El cálculo legal YA es correcto (séptimo día incluido); falta GL, pagos, PDF, endpoints.

- [DONE] **U4 — Nómina → contabilidad**: aprobar período → outbox `PayrollPeriodApproved` → `JournalDraft` balanceado (asiento del costo de planilla; débito gastos = crédito pasivos; SIN INSS deja líneas INSS en 0). Best-effort/idempotente. Commits `f21ff1ab` (config) `bdc1af44` (evento) `45f73533` (regla+wiring+tests). 98 tests verdes. Cuentas CoA por defecto (ajustar al catálogo real del contador con la junta).
- [DONE] **U5 — Pagos + cierre**: `register_payroll_payment` (neto) + auto `APPROVED→PAID` + `close_period` `PAID→CLOSED` + audit. Commit `032a7146`. 63 tests verdes. (Abono préstamos→portfolio y endpoints HTTP → follow-up abajo.)
- [DONE] Abono de préstamos/adelantos de planilla → `portfolio` (baja el saldo del crédito, best-effort). `portfolio.apply_payroll_abono` + `nomina.register_payroll_loan_deduction`. Commit `9c039c1e`. 101 tests verdes.
- [DONE] **B2 — PDF de la planilla** (WeasyPrint). Comparte `build_planilla_matrix` con el .xlsx (mismas casillas). `planilla_pdf.py`: `build_planilla_html` (puro, testeable sin la lib) + `render_planilla_pdf` (import lazy). Endpoint `planilla.pdf` (RBAC `nomina.sheet.read`). Dep + libs cairo/pango en Dockerfile dev/prod; **`pydyf==0.10.0` pineado** (weasyprint 62.3 rompe con pydyf≥0.11). Render real verificado en contenedor (PDF `%PDF`). Worktree `erp-field`, commits `3c5eb88f`+`694d35f3`+`1f58728f`, suite nómina 101 verde +1 skip.
  - [TODO] (ops) **Rebuild de la imagen backend** para que el render real funcione en runtime (`docker compose build backend`). Sin rebuild, el endpoint 500ea al renderar (la lib no está en la imagen viva); la lógica/endpoint ya están testeados.
- [DONE] **Endpoints HTTP** (grupo, alcance operable) — exponer la capa de servicios para operar. Se montan en `api/nomina/...` con el esquema actual (cuando Codex aterrice `/api/v1/` reubica el prefijo global).
  - [DONE] **Asistencia de campo (flujo diario)**: abrir día / listar / detalle · pase de lista · cuadrillas · reporte de cuadrilla · eventos · traslados · consolidar · listar consolidaciones · **aprobación SoD maker-checker** (approve-request → approvals/<uuid>/approve, approver≠maker; no se expone el approve crudo) · aplicar a planilla. RBAC `nomina.field.*`. `views_field.py`. Commits `ebe9c46a`+`b917fda4`, 4 tests HTTP.
  - [DONE] **Régimen INSS**: afiliación maestra fechada (historial + nueva, cierra la previa) · override por período · resolver por afiliación · **auto-clasificar CON/SIN INSS** (mueve el entry a la hoja hermana). RBAC `nomina.inss.*`. `views_inss.py`. Commits `9a53088e`+`265af70f`, 6 tests HTTP. Suite nómina 98 verde.
  - [BLOCKED] Endpoints **reportes/dashboard** (holidays_for_period + AttendanceReport + datasets) — **diferido**: dependen de módulos de reporting/dashboard aún sin construir; no tiene sentido exponer endpoints hasta tener esas piezas (decisión del usuario 2026-06-07).
- [DONE] **Calendario de feriados** (catálogo precargado NI). Modelo `Holiday` en 3 ejes (legal_type / date_kind FIXED·EASTER·ONE_OFF / applies_to_payroll) + `easter_sunday()` para Semana Santa. Data migration con el catálogo nacional (9 obligatorios + locales/patronales + asuetos estatales con `applies_to_payroll=False`). Servicio `holidays_for_period()` que materializa los feriados que caen en el período → **el revisor de la planilla ubica** los días que aplican (geografía GENERAL, sin auto-resolución por finca, por decisión del usuario). Worktree `erp-field`, commits `d3941593`+`b7de7c9f`+`eb8dba80`, 15 tests + suite nómina (81) verdes. Lista legal exacta a confirmar con contador/MITRAB (seed idempotente).
  - [TODO] (follow-up opcional) Auto-poblar `holiday_worked_days` cruzando `holiday_dates_for_period()` con la asistencia, si se quiere quitar el paso manual del revisor.
- [DONE] **`AttendanceReport` rollup** (des-huerfanizado). Antes solo existía en `0001_initial` (sin servicio/test). Ahora se deriva de la asistencia de campo consolidada/aprobada como reporte legal de período: nueva fuente `AttendanceSource.FIELD` + unique `(período,empleado,fuente)` (idempotente); `aggregate_attendance_report_detail` (desglose por casilla, misma clasificación que el puente a planilla) + `rollup_field_attendance_report(_for_period)` con auditoría. Worktree `erp-field`, commits `ccb63861`+`84669109`+`8083fb33`, 7 tests + suite nómina (88) verdes.

## CAPA 2 — Datos reales y operación
- [TODO] Seed: estructura de **Agrícola Santa Isabel** (empresa/fincas/zonas/cargos/empleados).
- [TODO] Import: flujo planillas Excel históricas → nomina kernel (las 53 hojas reales).

## CAPA 3 — Control crítico / anti-fraude (debilidades del backend)
- [TODO] Verticales SoD: maker-checker en anulaciones (`estacion.cancel_sale`, `retail_pos.void_ticket`) + fix flaky JWT.
- [TODO] Portfolio: RBAC en endpoints (anti-fraude) + diferidos (estados de allocation, due dates, reversa).

## CAPA 4 — Columna económica / visibilidad
- [TODO] Parties: API (CRUD) + outbox HR/Parties (datos maestros propagados).
- [TODO] Reporting: datasets económicos (aging CxC/CxP, cobros — "pack del contador").
- [TODO] Aterrizar F0 CEC gates + F1 motor de costeo (FIFO/STANDARD) → master.

## CAPA 5 — Frontend / móvil
- [BLOCKED] Frontend del flujo económico + planilla (esperando decisión rama `main` vs nueva).
- [TODO] Mobile (Taskflow) para operación de campo (POS/caja/asistencia).

## CAPA 6 — Módulos futuros
- [BLOCKED] **manejo_finca** (cuadrillas/zonas/tareas/insumos/avances) — esperando spec del ingeniero. Asistencia referencia por código/soft-FK (no lo posee).

---

## Log de sesiones
| Fecha | Tarea | Estado |
|---|---|---|
| 2026-06-07 | Análisis inicial del repo | DONE |
| 2026-06-07 | Nómina/planilla: asistencia + INSS + séptimo día + export xlsx (rama `feat/nomina-planilla-legal`) | DONE |
| 2026-06-07 | Calendario de feriados: catálogo `Holiday` + seed NI + `holidays_for_period` (revisor ubica) | DONE |
| 2026-06-07 | AttendanceReport rollup: des-huerfanizado, derivado de asistencia de campo (fuente FIELD) | DONE |
| 2026-06-07 | Endpoints HTTP asistencia de campo (flujo diario + SoD maker-checker) | DONE |
| 2026-06-07 | Endpoints HTTP régimen INSS (afiliación + elección + auto-clasificación) | DONE |
| 2026-06-07 | B2 — PDF de la planilla legal (WeasyPrint, comparte build_planilla_matrix) | DONE |
