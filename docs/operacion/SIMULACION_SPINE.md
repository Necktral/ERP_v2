# Simulación del Spine Económico (carga + funcional)

> Estado real al 2026-06-09. La simulación pasó de un *load-test de autenticación*
> (`simulacion/auth_load_simulation*.js`) a una **simulación de toda la columna
> económica**: un driver **funcional** end-to-end (management command) + una capa de
> **carga** k6 con monitoreo Grafana/InfluxDB.

## Dos capas

| Capa | Qué hace | Dónde |
|---|---|---|
| **Funcional** | Conduce el ciclo de negocio real por etapas (crea/opera/cierra) e idempotente | `manage.py run_business_simulation` |
| **Carga (k6)** | Mete carga sobre los endpoints de lectura del spine, mide p95/errores | `simulacion/spine/spine_load.js` |
| **Orquestación** | Siembra funcional → extrae el scope → corre k6 → junta reportes | `simulacion/spine/run_spine_simulation.sh` |
| **Monitoreo** | Dashboard del spine (p95 por endpoint, error rate, VUs) | `simulacion/dashboards/economic-spine.json` |

## Driver funcional — etapas del spine

`python manage.py run_business_simulation --tag demo --workers 3 --report /tmp/sim.json`

Idempotente por `--tag` (códigos e idempotency-keys estables). Cada etapa se **aísla**:
si una falla se registra y la simulación continúa, de modo que el reporte muestre
exactamente hasta dónde llegó el spine. Etapas, en orden:

1. **org_rbac** — holding/empresa/sucursal, usuarios admin+checker, membresías, rol con permisos del spine (SoD: maker≠checker).
2. **parties_hr** — cliente (Party) + N empleados (HR).
3. **inventory** — bodega + ítem + recepción (costo promedio).
4. **billing** — factura contado: `create_draft` → `issue_doc(apply_inventory=True)` (ingreso/GL + baja de inventario/COGS).
5. **portfolio** — CxC del cliente (saldo vivo).
6. **payroll** — config Nicaragua → período → planilla → entries → `compute_entry` → **aprobación SoD** (`request_period_approval`+`approve_period`) → pago del neto → cierre.
7. **accounting** — conteo de `JournalDraft` por estado generados por el spine.

El reporte JSON trae, por etapa: `status` (OK/FAILED), `ms`, `data` (refs/métricas) y, si falla, `error`. El flag final `ok` es true sólo si **todas** las etapas quedaron OK.

## Capa de carga (k6)

`simulacion/spine/spine_load.js`: login JWT (header) → fija `X-Company-Id`/`X-Branch-Id`
→ golpea endpoints de lectura del spine (inventario, facturación, nómina) en un escenario
`ramping-vus`. Thresholds: `http_req_failed < 2%`; p95 por endpoint (login <900ms,
inventario <700ms, facturación/nómina <800ms).

Variables: `BASE_URL`, `SPINE_USERNAME`/`SPINE_PASSWORD`, `SPINE_COMPANY_ID`,
`SPINE_BRANCH_ID`, `VUS_TARGET`, `SUSTAIN`.

## Correr todo (modo full)

```bash
# 1) Backend + DB arriba (ver simulacion/README.md)
# 2) Spine completo: siembra funcional + carga k6 + reportes
./simulacion/spine/run_spine_simulation.sh demo 10 30s
```

El runner: (1) corre `run_business_simulation --tag demo`, (2) extrae `company_id`/`branch_id`
del reporte funcional, (3) corre `spine_load.js` con ese scope, (4) guarda todo en
`simulacion/reports/spine_<timestamp>/` (`functional.json`, `k6.json`, `k6_summary.txt`).

## Monitoreo

`simulacion/spine/run_spine_simulation.sh` puede acompañarse del stack de monitoreo
(`simulacion/docker-compose.monitoring.yaml`, InfluxDB+Grafana). Importar
`simulacion/dashboards/economic-spine.json` para ver p95 por endpoint, tasa de error y VUs.

## Verificación

- **Funcional**: `pytest apps/modulos/integration/tests/test_business_simulation.py` —
  el spine corre verde end-to-end y es idempotente (re-ejecutar con el mismo `--tag`).
- **Carga**: el run k6 cumple los thresholds p95/errores definidos en el script.

## Pendiente (verticales no en master)

Las etapas de **finca**, **comisariato** y **fleet** viven en ramas feature aún no
integradas; se añadirán como etapas del driver cuando se mergeen. El spine actual cubre
el núcleo económico (org→HR→inventario→facturación→portfolio→nómina→contabilidad).
