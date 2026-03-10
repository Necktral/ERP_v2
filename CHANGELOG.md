# Changelog

## [Unreleased]

### Added

- **Seguridad (Backend):** modo cookie opcional (`AUTH_TOKEN_TRANSPORT`) + middleware CSRF para cookies.
- **QA:** Correccion de tests de integracion 2FA y mejoras de tipado estatico.
- **Auditoria (Backend):** redaccion de metadata/snapshots y reason codes `TOKEN_MISMATCH`, `INVALID_OLD_PASSWORD`, `CSRF_FAILED`.
- **Frontend:** soporte de cookie transport (CSRF header desde cookie + `withCredentials`).
- **Nginx:** hardening de headers de seguridad + rate limits por ruta (auth/api).
- **Docs (Operación):** pack operativo Import/Export & Sourcing (empresa + plantillas: RFQ, landed cost, checklist, términos).
- **HR (Backend/Frontend):** endpoint `POST /api/hr/employees/<id>/reset-temp-password/` + evento de auditoría `HR_EMPLOYEE_TEMP_PASSWORD_RESET` + acción UI en empleados.
- **HR (Backend/Frontend):** endpoint `POST /api/hr/employees/<id>/revoke-access/` + evento de auditoría `HR_EMPLOYEE_ACCESS_REVOKED` + acción UI en empleados.
- **Infra PROD:** `compose.prod.yaml` (backend+db+web), Nginx SPA + proxy `/api/`, `.env.prod.example` y Dockerfiles PROD (backend y web).
- **FUEL (Backend):** base del módulo Estación de Servicios bajo `/api/fuel/` + endpoint `GET /api/fuel/health/`.
- **FUEL (Backend):** endpoints operativos MVP:
  - `POST /api/fuel/shifts/open/`
  - `POST /api/fuel/shifts/<shift_id>/close/`
  - `POST /api/fuel/dispenses/`
  - `POST /api/fuel/sales/`
  - `POST /api/fuel/sales/<sale_id>/cancel/`
- **FUEL (Tests):** test de flujo (turno → despacho → venta → cierre) + constraint de turno único.
- **RBAC:** roles `fuel_*` y permisos `fuel.*` en `seed_rbac_v01`.
- **Auditoría (contrato):** extensión del contrato con `event_type`, `reason_code` y `subject_type` para FUEL.
- **Observabilidad (Backend):** middleware de logging por request en `/api/*` con `request_id` y latencia.
- **Observabilidad (Backend):** logging estructurado JSON con metadatos de request y actor.
- **Seguridad (Backend):** `throttle_scope` en endpoints sensibles de auth y bootstrap.
- **QA (Backend):** overrides por env para `me_read` y `me_acl_read`.
- **Docs (QA):** troubleshooting de Gate 3 por throttling y uso de `.env` en Docker Compose.
- **Paginación (Backend):** helper común limit/offset + respuesta estándar `{count, limit, offset, results}` en listados ORG/HR/RBAC/SYNC.
- **Índices (DB):** índices en OrgUnit, EmploymentAssignment, Role/Permission con migraciones.
- **CD (CI/CD):** workflow de despliegue con build/push a GHCR y deploy via SSH.
- **Docs (Operación):** guía `CD_DEPLOY_v1.0.md` y actualización de índice operativa.
- **Tests (Backend):** cobertura para listados paginados y anti-replay 2FA.
- **Fase 8 (Producción):** comandos operativos `export_phase8_release_baseline`, `verify_phase8_precutover`, `evaluate_phase8_rollback` y script `qa/run_phase8_go_live.sh` para ejecución controlada.
- **Runbooks (Operación):** `GO_LIVE_FASE8_PRODUCCION_v1.0.md` con pre-corte, cutover, burn-in de 14 días y rollback formal.
- **Contabilidad/Gobernanza (Backend):** cierre de fases operativas F9, F10, F11 y F12 en staging con toolchains canónicos y evidencia firmada.
- **SRE (QA):** runners canónicos `qa/run_phase9_go_live.sh`, `qa/run_phase10_go_live.sh`, `qa/run_phase11_go_live.sh`, `qa/run_phase12_go_live.sh` y plantillas cron asociadas.

### Changed

- **Seguridad (Backend):** `cryptography` actualizado a `46.0.5` para cubrir advisories reportados por auditoría.
- **Seguridad (Frontend):** actualización de toolchain de testing/build (`vitest` y lockfile asociado) para reducir riesgo por cadena `vite/esbuild` en auditorías.
- **Seguridad (Supply Chain):** actualización patch-level de dependencias Python (`Django 5.2.12`, `sentry-sdk 1.45.1`, `cryptography 42.0.8`) con cobertura de CVEs reportadas por `pip-audit`.
- **Seguridad (Secrets):** eliminación de credenciales demo hardcodeadas en tests, scripts de simulación, workflows y documentación operativa; ahora usan variables/placeholder no sensibles.
- **Security CI:** gitleaks ejecutado con configuración explícita del repo (`.gitleaks.toml`) y política determinista de exclusión para `backend/**` (legado) y `docs/operacion/evidencia/**`.
- **Documentación:** `docs/contexto_nucleos.md` queda como estado ejecutivo por fases y roadmap; blueprint completo consolidado en `docs/ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md`.
- **Versionado operativo:** evidencia masiva en `docs/operacion/evidencia/**` pasa a política de no versionado GitHub (artefactos locales/CI con hash).
- **Auth (Backend):** refresh/logout con scopes `auth_refresh` y `auth_logout`.
- **QA:** Gate 3 (k6) falla por 429 en `/auth/me` y `/auth/me/acl` si los overrides no llegan al contenedor (compose usa `.env`).
- **Docs (Operación):** índice de templates del pack Import/Export + corrección de placeholders en contrato proveedor.
- **FUEL (Backend):** `GET /api/fuel/health/` queda público (sin auth) para monitoreo.
- **Frontend:** paginación server-side en ORG/HR + servicios con `limit/offset` + `AppDataTable` pasa eventos/attrs.
- **Auth (Backend):** challenge 2FA one-time (DB-backed) con consumo atómico y binding suave.
- **Auth (Backend):** logout/refresh en cookie-mode limpian cookies en rutas idempotentes de error.
- **Infra PROD:** `compose.prod.yaml` usa imágenes con tags de release.

### Fixed

- **CI (GitHub Actions):** en `auth-load-simulation.yml` se corrige la ruta de publicación del artifact `backend-log` para apuntar al archivo realmente generado en `simulacion/reports/backend.log`.
- **Tests (Backend):** `test_axes_lockout` se habilita sin skip forzado.
- **Seguridad (Backend):** 2FA Anti-Replay endurecido con bloqueo pesimista (`select_for_update`) y eliminación inmediata del challenge tras consumo.
- **Seguridad (Backend):** `LogoutView` limpia cookies incondicionalmente al usar transporte `cookie`, garantizando idempotencia incluso con tokens inválidos.
- **Seguridad (Backend):** `POST /api/auth/2fa/verify/` mantiene contrato `400` para replay/challenge inválido en modo cookie incluso con cookies presentes (sin interferencia CSRF/context auth).

## [2026-01-13] - Release

### Added

- **Módulo HR (Frontend):**
  - Implementación de `HrPositionsPage.vue` para gestión de cargos/posiciones.
  - Implementación de `HrEmployeesPage.vue` para gestión de empleados y asignaciones.
  - Servicio `hr.service.ts` con métodos para interactuar con la API de HR (Positions, Employees, Assignments).
  - Rutas `/hr/positions` y `/hr/employees` protegidas por permisos RBAC (`hr.position.read`, `hr.employee.read`).
  - Integración de `RoleMap` en la creación de asignaciones.
  - Columna "Asignación" (badge) y acciones PC-first (asignar, terminar, provisionar).
- **Módulo ORG (Frontend):**
  - Implementación de `OrgCompanyProfilePage.vue` y `OrgBranchesPage.vue`.
  - Servicio `org.service.ts`.
- **ORG Multi-company (Backend + Frontend):**
  - Endpoint `GET/POST /api/org/companies/` (listado por memberships + creación bajo holding).
  - Auditoría contractual: `ORG_COMPANY_CREATED` permitido y emitido en POST.
  - Clonado de accesos del creador (roles/grants) al crear una nueva company.
  - Permiso RBAC nuevo: `org.company.create` (asignado a `company_admin`).
  - UI: página `OrgCompaniesPage.vue` (ORG · Empresas) con tabla PC-first + dialog de creación.
- **UX Bootstrap/Login:**
  - En primer arranque, `/login` muestra CTA para crear usuario inicial en `/bootstrap`.
- **UI Density:**
  - Modo `compact` más perceptible (padding de páginas, gutters, densidad real de tablas).
- **Configuración:**
  - Plugin `Notify` habilitado en `quasar.config.ts`.
  - Configuración de auditoría (`AUDIT_MODULE_NAME`, `AUDIT_SCHEMA_VERSION`) en `base.py`.

### Fixed

- **Backend:**
  - Corrección de ruta de carga de `.env` en `base.py`.
  - Adición de headers CORS personalizados (`x-company-id`, `x-branch-id`, etc.) en `base.py`.
  - Corrección de error 500 en Login por falta de configuración de auditoría (`AUDIT_MODULE_NAME`, `AUDIT_SCHEMA_VERSION`).
  - Corrección de tipo de dato para `AUDIT_SCHEMA_VERSION` (int en lugar de str).
  - Auditoría contractual: `module` de eventos ajustado a `AUTH`.
  - Endpoint `GET /api/auth/me/`: `roles` incluye roles scoped (`RoleAssignment`) y legacy (`UserRole`).
- **Frontend:**
  - Solución a error `$q.notify is not a function` habilitando el plugin.
  - Tipado estricto en columnas de tablas Quasar (`QTableColumn`).
  - Lint: eliminación de imports/funciones no usados en `HrEmployeesPage.vue`.

- **HR (Backend/Frontend):**
  - Se corrige el endpoint documentado de provisión: `POST /api/hr/employees/<id>/provision-user/`.
  - Se agrega migración y campo `is_setup_complete` en `accounts.User` para evitar error 500 al crear usuarios en BD existentes.
  - Se normaliza `email` vacío a `NULL` en provisionamiento para evitar violación de unicidad en `accounts_user.email`.
- **ORG (Backend):**
  - Permisos por método en Company Profile: `GET` usa `org.company.read`, `PUT` usa `org.company.update`.
  - URLs ORG con nombres de ruta (`org-companies`, `org-company-profile`, etc.).

## [2026-01-08] - Release

### Added

- Endpoint backend: `POST /api/hr/employees/<id>/provision-user/` para provisionar usuario a empleado.
- Permiso IAM: `iam.users.create` para controlar el acceso a la provisión de usuarios.
- Diálogo y botón en frontend para provisionar acceso desde la UI de empleados.
- Documentación actualizada en todos los módulos sobre el nuevo flujo y seguridad HR.

### Changed

- Lógica de reconciliación HR: ya no se fuerza la membresía a la empresa (COMPANY) por defecto, solo por asignaciones activas y roles mapeados.
- Mejoras de robustez y seguridad en la asignación de memberships.

### Fixed

- Mensajes y validaciones en el flujo de provisionamiento de usuario (backend y frontend).
