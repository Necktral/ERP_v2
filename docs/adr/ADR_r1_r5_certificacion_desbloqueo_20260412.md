# ADR — Desbloqueo de Certificación Integral R1→R5 (2026-04-12)

## Estado
Aprobado.

## Contexto
El paquete R1→R5 ya quedó implementado y validado a nivel técnico, pero la certificación integral quedó bloqueada por dos causas operativas:

1. `qa-pr-blast-radius-guard` en `FAIL` por ausencia de ADR/design note para un cambio de alto alcance.
2. Tres pruebas API de intercompany con `403` donde se esperaba `201`, en corrida de contenedor.

Al analizar el flujo real, el `403` ocurre en capa de autorización (auth/RBAC) antes de lógica de dominio Phase7B.  
La causa no fue un cambio funcional de intercompany, sino deriva de entorno en transporte de auth (`cookie` vs `header`) durante el helper de pruebas.

## Decisión
Se aplica un cierre quirúrgico, no-breaking y sin reabrir diseño:

1. Ajustar únicamente el helper `_mk_client` de pruebas Phase7B para forzar `X-Auth-Transport: header` en login y requests subsiguientes.
2. Mantener sin cambios el contrato HTTP público de intercompany, la semántica de grants y la lógica de dominio.
3. Registrar esta decisión en ADR para cumplir gobernanza de blast radius con evidencia técnica real.
4. Ejecutar validación en contenedor: pruebas API afectadas, `qa-pr-blast-radius-guard` y `qa-ci-gate1`.

## Consecuencias
- Se restablece confiabilidad de pruebas intercompany bajo distintos defaults de entorno.
- No se reduce seguridad ni se altera RBAC de producción.
- Se destraba certificación de CI sin introducir features nuevas.
- Permanece deuda transicional fuera de este cierre (no se toca en esta fase):
  - tipado/mapeo HTTP fino en payments,
  - fallback por prefijo en shadow ledger,
  - semántica temporal `time.min`,
  - semántica especial `global_totals_only_measures`.
