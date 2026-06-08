# CODEX Gap Register v1

Version: v1  
Fecha: 2026-04-16  
Estado: Registro priorizado de gaps accionables para convergencia

## Criterio de priorización

- `impacto`: efecto en operación real y bloqueo de cierre end-to-end.
- `bloqueante`: impide declarar dominio como `cerrado`.
- `orden`: secuencia recomendada de ejecución (1 = más urgente).

## Top 10 Gaps Priorizados

| orden | gap_id | estado_gap | dominio | tipo_gap | evidencia | impacto | bloqueante | contrato_impactado | blast_radius | accion_recomendada |
|---:|---|---|---|---|---|---|---|---|---|---|
| 1 | `GAP-BILLING-UI-001` | `cerrado` | Billing | `completion_single_domain` | `backend/src/apps/kernels/facturacion/views.py`; `frontend/src/pages/BillingDocumentsPage.vue`; `frontend/src/services/billing.service.ts`; `qa/reports/billing_ui_v1_smoke_staging.json`; `docs/operacion/HANDOFF_GAP_BILLING_UI_001_STAGING_SMOKE_20260416.md` | alto | no | Contrato funcional de operación de documentos (`/api/billing/docs/*`) | Bajo-Medio (solo Billing UI/API del mismo dominio) | CERRADO 2026-04-16: mantener smoke ACL+estado por release candidate y monitorear drift de contrato. |
| 2 | `GAP-PAYMENTS-UI-001` | `abierto` | Payments/Cash | `completion_single_domain` | `backend/src/apps/kernels/payments/urls.py`; sin wiring frontend de `intents`/`cash-sessions` | alto | sí | Contrato de sesión de caja y movimientos (`/api/payments/cash-sessions/*`) | Alto (POS/FUEL/contabilidad operativa) | Crear UI Payments/Cash v1 (apertura/cierre de caja + movimientos + intents). |
| 3 | `GAP-PROCUREMENT-UI-001` | `abierto` | Compras | `completion_single_domain` | `backend/src/apps/modulos/compras/urls.py`; sin rutas/páginas frontend de compras | alto | sí | Contrato de compras (`/api/procurement/docs/*`) | Medio (compras + reporting + accounting) | Construir UI Compras v1 (create/post/void) con smoke principal. |
| 4 | `GAP-REPORTING-UI-OPS-001` | `abierto` | Reporting | `completion_single_domain` | `frontend/src/pages/AnalyticsPage.vue` usa embed; falta UI para `/api/reporting/runs|exports|snapshots|saved-views` | alto | sí | Contrato Reporting kernel R8 (`/api/reporting/*`) | Medio (reporting + dashboard + auditoría de ejecución) | Implementar vistas operativas de run/export/snapshot/saved-view sobre contrato canónico. |
| 5 | `GAP-FUEL-UI-TXN-001` | `abierto` | FUEL | `completion_single_domain` | UI actual: `FuelDashboardPage.vue` + `FuelHealthPage.vue`; faltan acciones de turno/venta/cancelación | alto | sí | Contrato Fuel (`/api/fuel/shifts/*`, `/api/fuel/sales/*`) | Alto (Fuel + Billing + Inventory + Audit) | Entregar UI FUEL transaccional mínima: abrir/cerrar turno, crear/cancelar venta, retry compensación. |
| 6 | `GAP-IAM-RBAC-UI-001` | `abierto` | IAM/RBAC | `completion_cross_domain` | Backend IAM/RBAC activo (`modulos/iam/urls.py`, `modulos/rbac/urls.py`), sin pantallas dedicadas de administración | medio | sí | Contrato de permisos/roles/contexto (ACL y RBAC list APIs) | Medio (impacta HR, ORG, Sync, seguridad funcional) | Definir y ejecutar lote UI IAM/RBAC (roles/permisos/contexto) o congelar API-only con evidencia explícita. |
| 7 | `GAP-DOC-TEST-DRIFT-001` | `abierto` | ORG/HR/RBAC | `contract_closure` | `README.md` referencia `test_org_endpoints_audit.py`, `test_2fa_challenge.py`, `test_pagination_list_endpoints.py` no presentes | medio | sí | Baseline documental de contratos y evidencia de pruebas | Medio (riesgo de falsas señales de cierre) | Alinear README con pruebas reales o agregar las suites faltantes con cobertura verificable. |
| 8 | `GAP-FUEL-ROUTE-DOC-DRIFT-001` | `abierto` | FUEL | `contract_closure` | Diferencias entre documentación de topología Fuel (`docs/README.md`) y policy/código (`backend/src/config/routing_policy.py`, `config/urls.py`) | medio | sí | Canonical vs legacy route contract + headers de deprecación | Medio (riesgo de consumo incorrecto de rutas) | Unificar documentación de rutas Fuel con policy canónica y alias legacy vigentes. |
| 9 | `GAP-STATE-EVENT-OWNERSHIP-001` | `abierto` | Cross-domain (Billing/Inventory/Payments/Reporting/CEC/Audit) | `contract_closure` | No existen aún artefactos operativos `STATE_CATALOG`, `ROUTE_CONTRACT_MATRIX`, `EVENT_CONTRACT_MATRIX`, `OWNERSHIP_MATRIX` v1 | alto | sí | Estados permitidos, ownership de dato y eventos canónicos cross-domain | Alto (riesgo de drift en cierres futuros) | Generar los 4 artefactos contractuales v1 con referencias directas a código/rutas/eventos reales. |
| 10 | `GAP-LEGACY-SHIMS-RETIRE-001` | `abierto` | Release transversal | `release_closure` | Shims activos: `modulos.accounting/facturacion/inventarios/payments/__init__.py`; `sync-hmac` retirado y `sync_engine` queda canonico | medio | no | Plan de deprecación y convergencia release-ready | Medio en release (riesgo de deuda técnica y ambigüedad de import/ruta) | Definir plan de retiro por release para shims/namespaces legacy restantes con fecha y criterios de salida. |

## Notas operativas

- Este registro no corrige gaps automáticamente; define trabajo ejecutable por lotes de convergencia.
- Todo cierre de gap debe actualizar su evidencia y reflejarse en la `CODEX_COMPLETION_MATRIX_v1.md`.
- Si aparece contradicción nueva entre código y docs, se agrega como `contract_closure` antes de abrir implementación amplia.

## Cierres posteriores al corte v1

| gap_id | estado_gap | dominio | tipo_gap | evidencia | impacto | bloqueante | contrato_impactado | accion_cierre |
|---|---|---|---|---|---|---|---|---|
| `GAP-SYNC-BRANCH-SCOPE-001` | `cerrado` | Sync | `security_isolation` | PR #68; commit `8fa283c3`; merge `311cf66e`; `backend/src/apps/modulos/sync_engine/views.py`; `backend/src/tests/test_sync_device_enrollment_flow.py`; `backend/src/tests/test_sync_devices_list.py`; `docs/operacion/HANDOFF_SYNC_DEVICE_BRANCH_SCOPE_P0_20260504.md` | alto | sí | Administración de dispositivos Sync: challenge/list/revoke bajo scope branch | CERRADO 2026-05-04: enforcement por `request.branch`, tests focales y CI remoto verde. |
