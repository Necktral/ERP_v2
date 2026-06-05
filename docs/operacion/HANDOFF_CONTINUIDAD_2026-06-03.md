# Handoff de continuidad — Hardening de unidades (2026-06-03)

> Resumen para continuar en otra ventana sin perder contexto. **Lo hecho** + **lo que falta**.
> Plan maestro: `/home/necktral/.claude/plans/vas-a-elaborar-un-luminous-floyd.md`.
> Arquitectura de referencia: `docs/ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md` (invariantes, §5 ownership, §6 envelope, §9 state machines).

## Contexto del proyecto
- ERP/CRM Django (kernels en `backend/src/apps/kernels`, módulos en `backend/src/apps/modulos`).
- Objetivo: llevar **cada unidad** (11 módulos + 7 kernels) a nivel avanzado = capacidades de dominio **+** endurecimiento (auditoría detallada, RBAC+SoD por usuario, integración outbox/inbox, idempotencia, máquinas de estado), con pruebas unitarias + de integración con kernels. Orden: **por valor de negocio**, unidad por unidad.
- **Git/GitHub**: el remoto del trabajo es **`erp_v2` → git@github.com:Necktral/ERP_v2.git** (rama por defecto `master`, donde está TODO). El remoto `origin` (Necktral/Necktral) quedó **deslindado** (no se le sube nada). Futuro push: `git push erp_v2 master`.

## Cómo correr (operativa)
- Backend corre en el contenedor `erpcrm_backend` (compose en `/home/necktral/ERP_v2`).
- Tests rápidos (DB reutilizada): dentro del contenedor `cd /app/backend && export DJANGO_SETTINGS_MODULE=config.settings.test PYTEST_DB_BASE_NAME=test_erp_db PYTEST_DB_SLOT=devloop; pytest --reuse-db -p no:cacheprovider`.
- Tras cambios de modelo: `--create-db` una vez (recrea schema del slot). Migraciones: `DJANGO_SETTINGS_MODULE=config.settings.dev python -m config.manage makemigrations <app>` y `migrate <app>`.
- Suite canónica (CI): `pytest` sin slot (DB por pid). Baseline actual: **917 passed**.

## LO HECHO (esta fase — 15 commits, suite 869 → 917)
1. **Tests de los 11 módulos sin tests** (common, parties, integration, rbac, iam, hr, cec, accounts, audit, estacion_servicios, sync_engine) → suite 698 → 869. `pytest.ini` testpaths actualizado; `__init__.py` añadidos a iam/ y sync_engine/ (eran namespace packages).
2. **Fase 0 — fundación transversal** (reutilizable por todas las unidades):
   - App **`activity`**: `DeviceRegistry`, `UserSession` (duración), `ActivityEvent` (telemetría ligera), `WorkSession` (clock-in/out + horas). Dimensión "horas/dispositivo".
   - **SoD/maker-checker** `iam.ApprovalRequest` + `iam/approvals.py` (request/approve/reject/cancel/mark_executed): el solicitante no puede auto-aprobar; el aprobador necesita el permiso en el scope. Auditado (`IAM_APPROVAL_*`).
   - **API admin RBAC por usuario**: `rbac/services.py` (assign_role/revoke con scope+audit) + endpoints `/api/rbac/assignments/…`, `/users/<id>/effective-permissions/`.
   - **Helper de auditoría de servicio** `audit/service_audit.py` (`emit_service_event`, `build_audit_request`).
3. **Unidad #1 facturacion**: SoD en anulación (`void_sod.py`) + **Notas de Crédito** (`credit_notes.py`, `related_doc`+`credited_total`, reusa create_draft + adaptador A/B `issue_credit_note`, outbox `CreditNoteIssued`). Nota fiel: interfaz fiscal A/B (§7) y máquina de estados fiscal (§9) **ya estaban completas**.
4. **Unidad #2 inventarios**:
   - **Reversa de movimiento** de primera clase (`reversal.py`, `reversal_of`/`reversed_at`, invariante #1) — reusa post_receive/post_issue.
   - **Remisiones** (`remisiones.py`, modelos `Remision/RemisionLine/RemisionPhoto`): despacho punto A → recepción/cotejo físico por bodeguero punto B → entrada a inventario vía `post_receive`; fotos del gerente de compras por referencia; máquina de estados DRAFT→DISPATCHED→RECEIVED/CANCELLED; origen genérico (compra/traslado).
   - **Invariante #8 — política de costo versionada** (`costing.py`, modelo `InventoryCostPolicy`): versionada por scope (empresa/sucursal con fallback), `set_cost_policy` versiona, `resolve_costing_method` default WEIGHTED_AVERAGE; **estampado** `StockMovement.cost_policy_version` en post_receive/issue/adjust/transfer (anti-patrón #4, reproducibilidad #11).
- Toda nueva auditoría registrada en `apps/modulos/audit/contracts.py` (ALLOWED_EVENT_TYPES / SUBJECT_TYPES / REASON_CODES).

## LO QUE FALTA (prioridad)
1. **FEFO por tipo de producto** (pedido del usuario): perecederos / agroquímicos / carnes despachan **FEFO** (first-expired-first-out). Los datos ya existen en `InventoryItem`: `track_expiry`, `track_lots`, `shelf_life_days`, `storage_condition`, `category`. La selección de lote FEFO ya existe en los flujos de issue. **Refinamiento pendiente**: que el **método de costeo/despacho se resuelva por producto/categoría** (no solo por company/branch) — p.ej. `resolve_costing_method(company, branch, item)` que devuelva FEFO cuando `item.track_expiry` (o categoría perecedera), y atar FEFO al motor de costo. Modelar quizá `cost_method_override` por categoría/item o un `CostPolicyRule` por `storage_condition`/`category`.
2. **Motor de cálculo FIFO/STANDARD real**: hoy el cómputo sigue siendo promedio ponderado móvil; la política #8 ya gobierna/versiona el método pero el engine no cambia el cálculo aún.
3. **Resto del roadmap por valor** (cada unidad con misma DoD: dominio+audit+RBAC/SoD+outbox+idempotencia+state machine+tests): **payments** (estados pago/CashSession, SoD refund/cierre), **accounting** (HUECO CRÍTICO `audit=0`; SoD posting/cierre período; reproducibilidad), **nomina** (outbox→accounting/payments; puente HR), **portfolio** (audit=0/rbac=0), **reporting**, seguridad/backbone (iam/rbac/audit/integration), **cec**, verticales (estacion_servicios/retail_pos), personas (parties→CRM, hr contratos/asistencia/licencias).
4. **Merge cleanup**: el árbol tiene WIP pre-existente sin commitear (payments/portfolio/compras/org + migraciones/tests sin trackear) y basura (Zone.Identifier, .mypy_cache, evidencias, .tar.gz) → decidir qué commitear y gitignorar antes de un PR limpio. `compose.yaml` (hardening frontend setpriv) sigue sin commitear.
5. **Test flaky**: `src/tests/test_retail_pos_api.py` falla intermitente con `AUTH_INVALID_TOKEN` (401) bajo carga (JWT expira en un test largo). Pasa 15/15 aislado. Endurecer: subir TTL de access en settings.test o relogin dentro del test.

## Convenciones aprendidas (para mantener consistencia)
- Servicios `@transaction.atomic`, idempotencia por `idempotency_key`, errores tipados (`common.domain_errors` / subclases de error del kernel).
- Auditar cada acción con efecto vía `write_event` (o `emit_service_event`); registrar nuevos event_type/subject/reason en `audit/contracts.py`.
- Máquinas de estado como tabla `_ALLOWED_TRANSITIONS` + `can_transition_to` (patrón `cec.CloseRun`).
- Efectos cross-contexto por `publish_outbox_event` (envelope §6.2); el puente contable se dispara por el outbox event (`accounting.link_operational_event_to_accounting`).
- Tests: paquete `tests/` por unidad (ya en `pytest.ini`), helper `_scope()`/SimpleNamespace request, login real `/api/auth/login/` + headers `X-Company-Id/X-Branch-Id` para API.
