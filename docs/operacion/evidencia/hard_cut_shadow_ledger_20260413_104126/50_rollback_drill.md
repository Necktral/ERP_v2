# Rollback Drill (Shadow Ledger Legacy Escape)

## Objetivo
Validar que existe recuperación controlada si el hard-cut genera regresión en entorno.

## Procedimiento definido
1. Revertir flags en entorno afectado:
   - ACCOUNTING_SHADOW_PREFIX_FALLBACK_ENABLED=true
   - ACCOUNTING_SHADOW_PREFIX_FALLBACK_STRICT=false
2. Re-ejecutar smoke de shadow ledger + payments.
3. Confirmar recuperación y documentar causa raíz.

## Evidencia de recuperación (simulación controlada)
- Prueba ejecutada: backend/src/tests/test_phase4_shadow_ledger.py::test_project_shadow_ledger_fallbacks_to_shadow_prefix_when_rule_family_missing
- Exit code: 0
- Log: docs/operacion/evidencia/hard_cut_shadow_ledger_20260413_104126/rollback_drill_test.log

## Resultado
- PASS: camino legacy opt-in operativo para rollback controlado.
