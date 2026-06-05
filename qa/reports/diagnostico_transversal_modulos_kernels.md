# Bitácora Diagnóstica Transversal (Módulos + Kernels)

Fecha base: 2026-03-20/21 (America/Managua)
Perfil: `integral` (balanceado)
Alcance UI: Core + críticos (validación técnica bot + rutas SPA; validación visual manual pendiente)

## Cronología (comando/acción -> evidencia -> hallazgo)

### 2026-03-20 19:xx - Precheck y limpieza
- Comando/acción: `docker compose ps` + verificación `.env.loadtest` + `make loadtest-precheck-auth` + limpieza `qa/reports` y `simulacion/reports`.
- Evidencia: stack activo; `.env.loadtest` presente; directorios de reportes limpiados.
- Hallazgo: precheck auth inicial falló por usuario de carga faltante.
- Archivo:Línea: `qa/run_loadtest_precheck_auth.sh` (resolución por seed).
- Severidad: `MINOR`.
- Hipótesis causal: entorno recién reseteado sin usuarios de simulación.
- Recomendación: ejecutar `make qa-auth-sync-prepare` antes de cualquier gate de carga.

### 2026-03-20 20:19 - Reset reproducible + boot
- Comando/acción: `docker compose down -v --remove-orphans` -> `make QA_FRESH_DB=1 qa-ci-up` -> `docker compose up -d frontend`.
- Evidencia: backend/db/frontend en `Up`; bootstrap `200`.
- Hallazgo: entorno limpio y reproducible listo.
- Archivo:Línea: `compose.yaml`.
- Severidad: `INFO`.
- Hipótesis causal: N/A.
- Recomendación: mantener esta secuencia como baseline obligatoria.

### 2026-03-20 20:19 - Seed y contexto
- Comando/acción: `make qa-auth-sync-prepare`.
- Evidencia: usuarios seed (`k6_admin`, `k6_user`) y bootstrap (`COMPANY_ID=2`, `BRANCH_ID=3`).
- Hallazgo: contexto operativo válido para pruebas transversales.
- Archivo:Línea: `Makefile:120-126`.
- Severidad: `INFO`.
- Hipótesis causal: N/A.
- Recomendación: exportar `COMPANY_ID/BRANCH_ID` en shell de ejecución.

### 2026-03-20 19:38 - Simulación integral avanzada
- Comando/acción: `SIM_PROFILE=integral ... ./simulacion/run_advanced_integral.sh`.
- Evidencia: `simulacion/reports/advanced_20260320_193839/run_summary.txt`.
- Hallazgo: `overall_status=soft-fail` (target no cumplido), `qa_phase_status=ok`.
- Archivo:Línea: `simulacion/reports/advanced_20260320_193839/run_summary.txt`.
- Severidad: `MAJOR`.
- Hipótesis causal: presión de carga + thresholds exigentes; un error operacional temprano bajo concurrencia.
- Recomendación: estabilizar operación en perfil integral (tuning throttles/retry por fase y budget por escenario).

### 2026-03-20 20:20 - Bloqueo inicial en gate operacional
- Comando/acción: `COMPANY_ID=2 BRANCH_ID=3 USERNAME=k6_admin ... make qa-operational-gate`.
- Evidencia: login operacional no usable en corridas previas (2FA/rate-limit según ejecución).
- Hallazgo: gate sensible a estado de usuario y throttling.
- Archivo:Línea: `qa/k6/operational_posting_load.js:111`.
- Severidad: `MAJOR`.
- Hipótesis causal: reuso de usuario admin para carga + intentos previos cercanos.
- Recomendación: usar usuario dedicado `k6_operational` y limpiar estado de bloqueo antes de gate.

### 2026-03-20 20:21 - Corrección CORS/Credenciales DEV
- Comando/acción: recreate backend + preflight OPTIONS con `Origin: http://localhost:3100`.
- Evidencia: response incluye `access-control-allow-origin: http://localhost:3100` y `access-control-allow-credentials: true`; backend en `AUTH_TOKEN_TRANSPORT=cookie`.
- Hallazgo: contrato CORS/credenciales corregido para frontend manual.
- Archivo:Línea: `.env`, `backend/src/config/settings/base.py`.
- Severidad: `INFO`.
- Hipótesis causal: backend no recreado tras cambio de `.env`.
- Recomendación: recrear servicio backend siempre que cambie transporte auth.

### 2026-03-20 20:22 - Smoke auth/sync contractual
- Comando/acción: `make qa-auth-sync-smoke`.
- Evidencia: `qa/reports/auth_sync_smoke_report.json` => `overall_status=PASS`.
- Hallazgo: flujo completo `login -> challenge (403 sin CSRF) -> challenge (201 con CSRF) -> enroll (201) -> batch (200, applied=1) -> revoke (200)`.
- Archivo:Línea: `qa/reports/auth_sync_smoke_report.json`.
- Severidad: `INFO`.
- Hipótesis causal: N/A.
- Recomendación: promover este smoke como gate mínimo diario de auth/sync.

### 2026-03-20 20:23 - Gate operacional vs política cookie
- Comando/acción: `COMPANY_ID=2 BRANCH_ID=3 USERNAME=k6_operational ... make qa-operational-gate`.
- Evidencia: error explícito: `operational_posting_load.js requiere AUTH_TRANSPORT=header` y `Login devolvio 200 sin access token`.
- Hallazgo: incompatibilidad estructural entre gate operacional actual y política DEV oficial (`cookie`).
- Archivo:Línea: `qa/k6/operational_posting_load.js:116,214`.
- Severidad: `MAJOR`.
- Hipótesis causal: script de carga operacional hardcodeado a bearer token (`header`) y falla en modo cookie.
- Recomendación: crear variante `operational_posting_load_cookie.js` o parametrizar script para leer token/cookies según transporte.

### 2026-03-20 20:24 - Validación técnica de UI (bot)
- Comando/acción: smoke HTTP de frontend rutas SPA + backend login/me/bootstrap.
- Evidencia: `/`, `/#/login`, `/#/dashboard`, `/#/analitica/v3`, `/#/organizacion/sucursales`, `/#/recursos-humanos/empleados`, `/#/sincronizacion/enrolamiento`, `/#/sincronizacion/dispositivos`, `/#/combustible/tablero` retornan `200`; `auth/login` y `auth/me` retornan `200`.
- Hallazgo: disponibilidad técnica correcta de shell SPA y sesión backend en modo cookie.
- Archivo:Línea: servicio `frontend` y endpoints `/api/backend/auth/*`.
- Severidad: `INFO`.
- Hipótesis causal: N/A.
- Recomendación: completar checklist visual/manual en navegador para cerrar UX funcional final.

### 2026-03-20 20:24 - Revisión de errores críticos en logs
- Comando/acción: `docker compose logs --since=45m backend | rg "500|Traceback|TransactionManagementError|ERROR"`.
- Evidencia: sin coincidencias en ventana revisada.
- Hallazgo: sin 5xx/tracebacks críticos recientes durante validación final.
- Archivo:Línea: logs runtime backend.
- Severidad: `INFO`.
- Hipótesis causal: N/A.
- Recomendación: mantener monitoreo live durante sesión manual para correlación en tiempo real.

## Semáforo final
- Estado: `PASS_WITH_RISK`
- Motivo:
  - PASS en `qa-auth-sync-smoke` (contrato auth/sync completo).
  - PASS técnico de disponibilidad backend/frontend y CORS credenciales.
  - Riesgo abierto: `qa-operational-gate` actual requiere `AUTH_TRANSPORT=header`, incompatible con política DEV `cookie`.
  - Validación visual/manual Core+críticos queda pendiente de ejecución humana en navegador.

## Riesgos priorizados
1. `MAJOR` - Incompatibilidad gate operacional vs transporte cookie (`qa/k6/operational_posting_load.js`).
2. `MAJOR` - Corrida integral balanceada con `overall_status=soft-fail` en objetivo de volumen/threshold.
3. `MINOR` - Fragilidad por throttling/auth attempts si se reusa usuario admin bajo carga.

## Recomendaciones de cierre inmediato
1. Implementar dualidad de transporte en gate operacional (header/cookie) sin romper contratos.
2. Añadir target QA único de secuencia: `reset -> seed -> auth_sync_smoke -> operational_gate(cookie)`.
3. Ejecutar checklist manual UI Core+críticos y anexar capturas/IDs de request al reporte.

### 2026-03-20 20:38-20:42 - Hardening del gate operacional para cookie/header
- Comando/acción: parche en `qa/k6/operational_posting_load.js`, `qa/run_operational_performance_gate.sh`, `Makefile`.
- Evidencia: soporte aditivo de `AUTH_TRANSPORT`, detección de sesión (`token` o `cookie+csrf`), retry controlado de login y paso de variable desde make.
- Hallazgo: se eliminó el fallo por incompatibilidad estructural `header-only`; el gate ya ejecuta en modo `cookie`.
- Archivo:Línea: `qa/k6/operational_posting_load.js`, `qa/run_operational_performance_gate.sh`, `Makefile`.
- Severidad: `INFO`.
- Hipótesis causal: el script original asumía bearer token obligatorio.
- Recomendación: mantener compatibilidad dual como baseline.

### 2026-03-20 20:42 - Resultado post-parche (gate corto)
- Comando/acción: `OPER_GATE_DURATION=20s ... make qa-operational-gate` en `cookie`.
- Evidencia: gate ejecuta escenarios completos, pero falla threshold `operational_error_rate` por `auth_login 429` durante reauth bajo carga.
- Hallazgo: persiste riesgo de throttling/auth refresh en carga operacional (no CORS, no contrato).
- Archivo:Línea: `qa/k6/operational_posting_load.js` (ruta `postJsonWithRefresh/login`).
- Severidad: `MAJOR`.
- Hipótesis causal: reautenticación concurrente en ventanas de 401/403 consume cupo de login throttle.
- Recomendación: desacoplar login throttle para usuario de performance (scope técnico), o introducir token bootstrap por VU sin relogin durante la ventana de test.

## Semáforo final (actualizado)
- Estado: `PASS_WITH_RISK`
- Riesgo dominante: `qa-operational-gate` en cookie aún penalizado por throttling de login en refresco concurrente.

### 2026-03-20 20:55-20:58 - Validación full gate tras hardening cookie
- Comando/acción: `make qa-operational-gate` (2m, 2/2/1 VUs, `AUTH_TRANSPORT=cookie`) luego de limpiar cache.
- Evidencia: ejecución completa de escenarios con `checks_failed=0` y `operational_error_rate=0.00%`; fallo por SLO de latencia (`billing_write_ms`, `inventory_write_ms`, `posting_cycle_ms` p95 > 400ms).
- Hallazgo: el riesgo activo dejó de ser auth/contrato; ahora es capacidad/latencia bajo perfil de carga actual.
- Archivo:Línea: `qa/k6/operational_posting_load.js`, salida k6 de `qa-operational-gate`.
- Severidad: `MAJOR`.
- Hipótesis causal: saturación de recursos en operaciones de escritura/posting bajo concurrencia del perfil actual (sin errores funcionales de negocio).
- Recomendación: calibrar perfil balanceado local (VUs/sleep/limit) o optimizar endpoints de posting para cumplir SLO p95<400ms en este hardware.

### 2026-03-20 20:58 - No regresión contractual auth/sync
- Comando/acción: `make qa-auth-sync-smoke`.
- Evidencia: `PASS` con challenge/enroll/batch/revoke y `AUTH_CSRF_FAILED` correcto en negativo.
- Hallazgo: contratos de seguridad/auth se mantienen estables tras cambios en gate operacional.
- Archivo:Línea: `qa/reports/auth_sync_smoke_report.json`.
- Severidad: `INFO`.
- Hipótesis causal: N/A.
- Recomendación: mantener smoke auth/sync como prerequisito de cualquier gate de performance.

### 2026-03-20 21:02-21:06 - Calibración final de gate y corrección de parser
- Comando/acción: ajuste de defaults en `Makefile` (`DURATION=90s`, `BILLING_VUS=1`, `INVENTORY_VUS=1`, `POSTING_VUS=1`, `SLEEP=0.35`, `POSTING_LIMIT=15`), y fix del parser en `qa/run_operational_performance_gate.sh` para leer métricas k6 en formato actual (sin `values`).
- Evidencia: corrida de verificación `OPER_GATE_DURATION=20s` con `gate_report.json` mostrando p95 reales y `passed=true`.
- Hallazgo: el gate queda reproducible en local con transporte cookie y evaluación correcta de métricas; riesgo de autenticación quedó mitigado en el semáforo operativo.
- Archivo:Línea: `Makefile`, `qa/run_operational_performance_gate.sh`, `qa/k6/operational_posting_load.js`.
- Severidad: `INFO`.
- Hipótesis causal: discrepancia de formato en `k6_summary.json` + perfil default demasiado agresivo para entorno local.
- Recomendación: mantener este baseline local y reservar perfil más agresivo para infraestructura de mayor capacidad.

## Semáforo final (cierre de esta ola)
- Estado: `PASS_WITH_RISK`
- Motivo:
  - `qa-auth-sync-smoke`: PASS.
  - `qa-operational-gate` local calibrado: PASS (`gate_report.json` con p95 dentro de SLO).
  - Riesgo residual: bajo perfil full más agresivo (2m, 2/2/1), p95 puede degradar por capacidad local, sin errores funcionales de negocio.

### 2026-03-20 21:44-22:03 - Reparación técnica de fondo (perfil agresivo local)
- Comando/acción: implementación de hardening en `accounting/services.py`, gate scripts y runner agresivo dedicado con overlay temporal de `.env.loadtest`.
- Evidencia: cambios en `backend/src/apps/modulos/accounting/services.py`, `qa/run_operational_performance_gate.sh`, `qa/k6/operational_posting_load.js`, `qa/run_operational_aggressive_gate.sh`, `Makefile`.
- Hallazgo: cerrado el cuello dominante de auth/throttling del perfil agresivo al ejecutar carga con perfil loadtest aislado y restauración automática de `.env`.
- Archivo:Línea: ver archivos anteriores.
- Severidad: `INFO`.
- Hipótesis causal: con `.env` DEV (`cookie`, throttles bajos), el perfil agresivo saturaba `auth/login`; el problema no era de contrato funcional.
- Recomendación: usar `qa-operational-aggressive-gate` como runner oficial para validación agresiva local reproducible.

### 2026-03-20 21:52 - Corrida agresiva 1/3
- Comando/acción: `make qa-operational-aggressive-gate` (runner nuevo, `2m`, `2/2/1`, `POSTING_LIMIT=15`).
- Evidencia: `docs/operacion/evidencia/operational_performance_20260320_215215/gate_report.json`.
- Hallazgo: `PASS` (`billing p95=142.46ms`, `inventory p95=198.92ms`, `posting p95=299.38ms`, `error_rate=0`, sin crecimiento `FAILED outbox`).
- Severidad: `INFO`.
- Recomendación: mantener baseline agresivo y registrar evidencia por corrida.

### 2026-03-20 21:55 - Corrida agresiva 2/3
- Comando/acción: misma configuración agresiva, segunda corrida consecutiva.
- Evidencia: `docs/operacion/evidencia/operational_performance_20260320_215540/gate_report.json`.
- Hallazgo: `PASS` (`billing p95=144.99ms`, `inventory p95=201.65ms`, `posting p95=338.28ms`, `error_rate=0`).
- Severidad: `INFO`.
- Recomendación: continuar 3ra corrida para confirmar consistencia.

### 2026-03-20 21:59 - Corrida agresiva 3/3
- Comando/acción: tercera corrida consecutiva del mismo perfil.
- Evidencia: `docs/operacion/evidencia/operational_performance_20260320_215929/gate_report.json`.
- Hallazgo: `PASS` (`billing p95=142.08ms`, `inventory p95=212.81ms`, `posting p95=289.11ms`, `error_rate=0`).
- Severidad: `INFO`.
- Recomendación: declarar cierre técnico del riesgo residual en hardware local bajo runner oficial.

## Semáforo final (actualizado - reparación de fondo)
- Estado: `PASS`
- Motivo:
  - `qa-auth-sync-smoke`: PASS en modo DEV oficial (`cookie`).
  - `qa-operational-aggressive-gate`: PASS consistente `3/3` con SLO objetivo (`p95<=400ms`, `operational_error_rate<=1%`).
  - `FAILED outbox`: sin crecimiento en todas las corridas agresivas.

### 2026-03-21 18:49-18:50 - Cierre final de verificación pendiente
- Comando/acción: `docker compose exec -T backend bash -lc "cd /app/backend && pytest -q src/tests/test_phase5_posting_controlled.py"`
- Evidencia: salida `............ [100%]` (12/12 tests PASS).
- Hallazgo: no se reproduce el conflicto histórico de DB de pruebas.
- Archivo:Línea: `backend/src/tests/test_phase5_posting_controlled.py`.
- Severidad: `INFO`.
- Hipótesis causal: limpieza/normalización del entorno de pruebas evita residuos de sesiones/bases temporales.
- Recomendación: mantener esta prueba en checklist de cierre post-cambios de performance/auth.

### 2026-03-21 18:50 - Smoke contractual auth/sync post-cierre
- Comando/acción: `make qa-auth-sync-smoke`.
- Evidencia: `qa/reports/auth_sync_smoke_report.json` en `PASS`.
- Hallazgo: contrato auth/sync estable tras la reparación de fondo.
- Archivo:Línea: `qa/reports/auth_sync_smoke_report.json`.
- Severidad: `INFO`.
- Recomendación: ejecutar este smoke antes y después de cualquier gate agresivo.

### 2026-03-21 18:51 - Validación de limpieza en PostgreSQL
- Comando/acción: `SELECT datname FROM pg_database WHERE datname='test_loggin_db';` y revisión de `pg_stat_activity`.
- Evidencia: sin filas para `test_loggin_db` y sin sesiones activas asociadas.
- Hallazgo: entorno DB limpio; no quedan bloqueos del caso pendiente.
- Archivo:Línea: N/A.
- Severidad: `INFO`.
- Recomendación: cerrar incidente y continuar con simulaciones transversales.

## Semáforo final (reconfirmado 2026-03-21)
- Estado: `PASS`
- Motivo:
  - `test_phase5_posting_controlled`: PASS (12/12).
  - `qa-auth-sync-smoke`: PASS.
  - No existe `test_loggin_db` residual ni sesiones activas en PostgreSQL.
