# Changelog

## [Unreleased] - 2026-01-05

### Added

- **Módulo HR (Frontend):**
  - Implementación de `HrPositionsPage.vue` para gestión de cargos/posiciones.
  - Implementación de `HrEmployeesPage.vue` para gestión de empleados y asignaciones.
  - Servicio `hr.service.ts` con métodos para interactuar con la API de HR (Positions, Employees, Assignments).
  - Rutas `/hr/positions` y `/hr/employees` protegidas por permisos RBAC (`hr.position.read`, `hr.employee.read`).
  - Integración de `RoleMap` en la creación de asignaciones.
- **Módulo ORG (Frontend):**
  - Implementación de `OrgCompanyProfilePage.vue` y `OrgBranchesPage.vue`.
  - Servicio `org.service.ts`.
- **Configuración:**
  - Plugin `Notify` habilitado en `quasar.config.ts`.
  - Configuración de auditoría (`AUDIT_MODULE_NAME`, `AUDIT_SCHEMA_VERSION`) en `base.py`.

### Fixed

- **Backend:**
  - Corrección de ruta de carga de `.env` en `base.py`.
  - Adición de headers CORS personalizados (`x-company-id`, `x-branch-id`, etc.) en `base.py`.
  - Corrección de error 500 en Login por falta de configuración de auditoría (`AUDIT_MODULE_NAME`, `AUDIT_SCHEMA_VERSION`).
  - Corrección de tipo de dato para `AUDIT_SCHEMA_VERSION` (int en lugar de str).
- **Frontend:**
  - Solución a error `$q.notify is not a function` habilitando el plugin.
  - Tipado estricto en columnas de tablas Quasar (`QTableColumn`).

## [2026-01-08] - Release

### Added

- Endpoint backend: `POST /hr/employees/<id>/provision-user/` para provisionar usuario a empleado.
- Permiso IAM: `iam.users.create` para controlar el acceso a la provisión de usuarios.
- Diálogo y botón en frontend para provisionar acceso desde la UI de empleados.
- Documentación actualizada en todos los módulos sobre el nuevo flujo y seguridad HR.

### Changed

- Lógica de reconciliación HR: ya no se fuerza la membresía a la empresa (COMPANY) por defecto, solo por asignaciones activas y roles mapeados.
- Mejoras de robustez y seguridad en la asignación de memberships.

### Fixed

- Mensajes y validaciones en el flujo de provisionamiento de usuario (backend y frontend).
