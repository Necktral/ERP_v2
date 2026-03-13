# Politica Temporal De Excepcion: NPM Audit Frontend

Emitido: 2026-03-13T04:07:38Z  
Riesgo asociado: `R-001`

## Hallazgo

- Advisory: `GHSA-5c6j-r48x-rmvq`
- Paquete vulnerable: `serialize-javascript`
- Cadena: `@quasar/app-vite -> serialize-javascript`
- Evidencia actual: `qa/reports/npm_audit_latest.json`
- Estado upstream: sin fix disponible (`fixAvailable=false`)

## Justificacion De Excepcion Temporal

- El riesgo se ubica en dependencias de build frontend (toolchain), no en endpoint backend productivo.
- No existe release parcheada utilizable de upstream en la fecha de emision.
- El bloqueo total de entrega no reduce riesgo si no hay version corregida para adoptar.

## Controles Compensatorios Obligatorios

1. Ejecutar `npm audit --json` en cada corrida QA.
2. Mantener lockfile congelado y evitar upgrades no controlados.
3. Revisar semanalmente disponibilidad de parche upstream.
4. Cerrar la excepcion inmediatamente al existir version corregida.

## Fecha De Revision

- Proxima revision obligatoria: 2026-03-20.

## Criterio De Cierre

- `npm audit` sin vulnerabilidades HIGH para esta cadena en la rama de entrega.
