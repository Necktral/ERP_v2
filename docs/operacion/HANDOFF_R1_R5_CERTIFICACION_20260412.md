# HANDOFF R1→R5 — Certificación integral (2026-04-12)

## Diagnóstico del área
- El bloqueo operativo de certificación quedó acotado a dos puntos: `403` en 3 pruebas API intercompany y falta de evidencia de handoff para gobernanza CI.
- El `403` se reproduce en capa de auth/RBAC cuando el flujo de test no fuerza transporte `header` y el entorno efectivo usa `cookie`.
- No se identificó regressión funcional nueva en lógica de dominio de intercompany (Phase7B).

## Alcance exacto
- Ajuste mínimo del helper `_mk_client` en pruebas Phase7B para forzar `X-Auth-Transport: header` en login y requests subsecuentes.
- Alta de ADR técnico de desbloqueo de certificación en `docs/adr/`.
- Ejecución de validación dirigida y gates exigidos por CI.
- Fuera de alcance: refactor de dominios R1→R5, cambios de semántica de permisos, cambios de contrato HTTP público.

## Contratos impactados
- Contrato de pruebas API intercompany (harness de autenticación en tests).
- Contrato de gobernanza QA (codex governance + blast radius evidence).
- Contrato HTTP público intercompany: sin cambios.
- Contrato de permisos/grants intercompany: sin cambios de semántica.

## Pruebas / validación
- `pytest` dirigido de los 3 casos API intercompany afectados: esperado `PASS`.
- `make qa-pr-blast-radius-guard`: esperado `PASS`.
- `make qa-ci-gate1`: ejecución completa para certificación formal del paquete.
- Evidencia técnica en `qa/reports/*.json` y salida de comandos en contenedor.

## Riesgos remanentes
- Deuda transicional aún viva (no abordada en esta fase):
  - tipado/mapeo HTTP fino en payments,
  - fallback por prefijo en shadow ledger,
  - semántica temporal `time.min`,
  - semántica especial `global_totals_only_measures`.
- Riesgo de entorno: si una corrida externa ignora transporte explícito en tests API sensibles, puede reaparecer señal falsa de autorización.

## Plan de rollback
- Revertir únicamente el cambio del helper de test y este handoff/ADR si aparece efecto colateral no esperado en suite.
- Mantener rollback limitado a artefactos de certificación; no revertir cambios estructurales R1→R5 ya validados.
- Reejecutar gates obligatorios tras rollback para confirmar estado consistente.

## Estado de gates
- Objetivo de cierre: `qa-pr-blast-radius-guard` en verde y `qa-ci-gate1` en verde en contenedor.
- Si `qa-ci-gate1` detecta un nuevo bloqueo no relacionado, el estado final se reporta como `no certificado` con causa exacta.
