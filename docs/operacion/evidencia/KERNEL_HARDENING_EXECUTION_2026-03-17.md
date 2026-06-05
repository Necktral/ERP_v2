# Evidencia de Ejecución — Kernel Hardening (2026-03-17)

## Alcance ejecutado

- S0: baseline documental y mapeo matriz->código->tests.
- S1: cobertura adicional de IAM/scope.
- S2: auditoría contractual para Payments/Cash.
- S3: contrato canónico de outbox validado por pruebas.
- S4: freeze de matriz contable por pruebas.
- S6: compat legacy de Billing validada por prueba de deprecación.
- S7: endpoint `inventory/ledger` con paginación y orden estable.
- S8: frontera Payments/Accounting reforzada por pruebas y auditoría.

## Comandos ejecutados

```bash
cd login_module
pytest --ds=config.settings.test -q \
  src/tests/test_iam_scope_contracts.py \
  src/tests/test_phase2_payments_api.py \
  src/tests/test_payments_accounting_boundary.py \
  src/tests/test_accounting_event_matrix_freeze.py \
  src/tests/test_inventory_kernel_flow.py \
  src/tests/test_billing_doc_flow.py \
  src/tests/test_phase1_operational_contracts.py \
  src/tests/test_phase3_outbox_dispatcher.py

python -m pytest --ds=config.settings.test -q \
  src/tests/test_phase3_cec_orchestrator.py \
  src/tests/test_phase3_cec_execute_api.py
```

Resultado:
- tests objetivo en verde.
- advertencia no bloqueante de permisos sobre `.pytest_cache`.

## Nota operativa

- Se detectó colisión inicial por ejecutar dos procesos `pytest` en paralelo contra la misma test DB.
- Reejecución secuencial realizada y validada en verde.
