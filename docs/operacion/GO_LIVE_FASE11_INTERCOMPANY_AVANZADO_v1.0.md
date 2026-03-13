# GO LIVE Fase 11 Intercompany Avanzado v1.0

## Objetivo

Cerrar F11 en staging con:

- happy path y blocked path certificados;
- SLA 24h estricto aplicado;
- gate final en PASS;
- evidencia firmada lista para promoción.

## Scope y defaults

- `COMPANY_ID=5`
- `BRANCH_ID=6`
- timezone operativa: `America/Managua`
- severidad de gate: cero backlog crítico

## Precheck

Comando canónico:

```bash
OUT_DIR=docs/operacion/evidencia/phase11_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
./qa/run_phase11_go_live.sh precheck
```

El precheck valida:

- F8/F9/F10 en PASS desde evidencia activa;
- manifiesto F11 exportable;
- matriz explícita con `CompanyLink + LinkGrant WRITE`;
- catálogo de `IntercompanyDisputeReason` activo.

## Certificación F11

```bash
OUT_DIR=docs/operacion/evidencia/phase11_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
./qa/run_phase11_go_live.sh certify
```

Artefactos esperados:

- `22_phase11_happy.json`
- `23_phase11_blocked.json`
- `20/21` manifests de paridad

## Ciclo operativo y estabilidad

```bash
OUT_DIR=docs/operacion/evidencia/phase11_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
./qa/run_phase11_go_live.sh cycle
```

Regla de estabilidad:

- 2 corridas limpias consecutivas;
- máximo 6 intentos;
- 120s entre intentos.

## Gate final

```bash
OUT_DIR=docs/operacion/evidencia/phase11_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
./qa/run_phase11_go_live.sh gate
```

Gate PASS requiere:

- paridad sin drift;
- evidencia happy y blocked válidas;
- `open/disputed/outside_sla/stale_confirmed/open_blocking_exceptions` en umbral.

## Summary y hash

```bash
OUT_DIR=docs/operacion/evidencia/phase11_go_live_<TS> \
./qa/run_phase11_go_live.sh summary
```

Entregables:

- `30_phase11_summary.json`
- `31_phase11_result_matrix.md`
- `32_phase11_summary.sha256`

## Operación continua

Usar `qa/phase11_cycle.cron.example`:

- ciclo cada 5 min;
- gate diario;
- summary diario.

## Triggers de incidente (rollback lógico)

- `go_live_passed=false`;
- `open_intercompany_blocking_exception_count > 0` sostenido;
- `disputed_outside_sla_count > 0` fuera de ventana;
- `inbox_failed/outbox_failed > 0` sostenido.

Acciones:

1. congelar ejecución automática de ciclo;
2. resolver disputa/excepción y rerun de `cycle`;
3. rerun de `gate` y `summary`;
4. documentar RCA en evidencia del día.
