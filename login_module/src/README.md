# Necktral ERP/CRM

Sistema ERP/CRM modular con backend Django + DRF y frontend Quasar. Incluye RBAC, auditoría contractual, HR, ORG, IAM y sincronización.

## Estructura del repo

- `login_module/`: backend Django/DRF (código en `login_module/src/`)
- `frontend/`: consola web (Vue 3 + Quasar)
- `compose.yaml`: entorno Docker (backend + Postgres)
- `system_wis/`: entorno virtual Python (dev)

## 🚀 Inicio rápido (Docker)

1. Configura variables

```bash
cp .env.example .env
```

2. Levanta servicios

```bash
docker compose up -d
```

URLs por defecto:

- Frontend (Quasar): http://localhost:3000
- Backend (Django/DRF): http://localhost:8000

Nota: el contenedor `backend` corre migraciones automáticamente al iniciar (ver `compose.yaml`).

### Reset total de DB (instalación fresca)

```bash
docker compose down -v
docker compose up -d
curl http://localhost:8000/api/auth/bootstrap/status/
```

## 💻 Desarrollo local

### Backend (venv)

```bash
source system_wis/bin/activate
pip install -r requirements/dev.txt

cd login_module
python src/manage.py migrate --noinput
python src/manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## ✅ Tests y análisis

### Backend

- Tests:
  ```bash
  source system_wis/bin/activate
  cd login_module
  pytest
  ```
- Lint (ruff):
  ```bash
  source system_wis/bin/activate
  cd login_module
  ruff check .
  ```

### Frontend

- Lint:
  ```bash
  cd frontend
  npm run lint
  ```
- Tests: actualmente `npm run test` es un placeholder.

## Auditoría (contrato)

- Los eventos de auditoría se emiten con `module=AUTH` y `schema_version=1`.
- Para trazabilidad: se encadenan hashes y se firma con HMAC.

## Historial de cambios

Ver [CHANGELOG.md](CHANGELOG.md).

Bitácora de desarrollo (registro detallado y cronológico): ver [BITACORA.md](../../BITACORA.md).

### ORG (Organización)

- `GET /api/org/company/profile/` — Ver perfil de la empresa (requiere permiso: org.company.read)
- `PUT /api/org/company/profile/` — Actualizar perfil de la empresa (requiere permiso: org.company.update)
- `GET /api/org/companies/` — Listar compañías accesibles por membresía (requiere permiso: org.company.read)
- `POST /api/org/companies/` — Crear compañía bajo el holding y clonar accesos del creador (requiere permiso: org.company.create)
- `GET /api/org/branches/` — Listar sucursales (requiere permiso: org.branch.read)
- `POST /api/org/branches/` — Crear sucursal (requiere permiso: org.branch.create)
- `PATCH /api/org/branches/{branch_id}/` — Actualizar sucursal (requiere permiso: org.branch.update)

### HR (Recursos Humanos)

- `GET /api/hr/positions/` — Listar puestos
- `POST /api/hr/positions/` — Crear puesto
- `PATCH /api/hr/positions/<int:position_id>/` — Actualizar puesto
- `PUT /api/hr/positions/<int:position_id>/roles/` — Mapear puesto a roles
- `GET /api/hr/employees/` — Listar empleados
- `POST /api/hr/employees/` — Crear empleado
- `PATCH /api/hr/employees/<int:employee_id>/` — Actualizar empleado
- `POST /api/hr/employees/<int:employee_id>/assignments/` — Asignar puesto/sucursal
- `POST /api/hr/employees/<int:employee_id>/assignments/<int:assignment_id>/end/` — Finalizar asignación
- `POST /api/hr/employees/<id>/provision-user/`
  - Crea un usuario vinculado al empleado con contraseña provisional.
  - Valida asignación activa y fuerza cambio de contraseña en primer login.
  - Requiere permisos `iam.users.create` y `hr.employee.update`.
- `POST /api/hr/employees/<id>/reset-temp-password/`
  - Resetea la contraseña provisional del usuario vinculado al empleado.
  - Payload opcional: `{ "temp_password": "..." }`.
  - Responde `409` si el empleado no tiene `linked_user` o no tiene asignación activa.
  - Auditoría: emite `HR_EMPLOYEE_TEMP_PASSWORD_RESET` (metadata sin password).

## Comandos de gestión

- `python manage.py seed_rbac_v01` — Siembra roles, permisos y mapeos estándar (idempotente, auditable)
- `python manage.py bootstrap_company --company-name ... --branch-name ... --admin-username ...` — Bootstrap de empresa, sucursal y admin
  - El comando es idempotente: si la empresa, sucursal o holding ya existen (por código o nombre), los reutiliza y reactiva si estaban desactivados.
  - Si usas `--no-input`, todos los parámetros son obligatorios y el comando falla si falta alguno.
  - AdminGrant siempre se crea con `org_unit=company` y se reactiva si estaba desactivado.
  - Membership y RoleAssignment también se reactivan si estaban off.
  - Validado por el test: `tests/test_bootstrap_company_command.py`.

## Auditoría contractual

- Todos los endpoints de escritura generan eventos en apps.audit con reason_code y event_type según contrato.
- Ejemplo: `HR_POSITION_CREATED`, `ORG_BRANCH_CREATED`, `RBAC_SEEDED_V01`.
- El contrato de auditoría es estricto y validado por tests.

## Tests automáticos

- `tests/test_hr_position_role_automation.py`: Valida automatización de roles por puesto y auditoría.
- `tests/test_seed_rbac_v01_command.py`: Valida comando seed_rbac_v01, creación de permisos y evento de auditoría.
- `tests/test_bootstrap_company_command.py`: Valida robustez, idempotencia y grants correctos del comando bootstrap_company.
- `tests/test_org_endpoints_audit.py`: Valida permisos RBAC por método en endpoints ORG y la trazabilidad/auditoría contractual de operaciones clave.

## Permisos y roles

- Catálogo estándar en apps/rbac/seed_v01.py
- Roles: company_admin, branch_manager, hr_manager, etc.
- Permisos: hr.position.create, org.branch.create, etc.

## Buenas prácticas

- Siempre ejecutar los comandos de seed y bootstrap en entornos nuevos.
- Validar con tests antes de desplegar.
- Consultar la auditoría para trazabilidad de cambios críticos.

## Seguridad y memberships HR

- La reconciliación de memberships ya no fuerza acceso a la empresa (COMPANY) por defecto.
- Solo se asignan memberships por asignaciones activas y roles mapeados.
- Mejora la robustez y evita accesos innecesarios.

## Permisos IAM

- Nuevo permiso: `iam.users.create` para controlar el provisionamiento de usuarios desde HR.

---

Actualizado: 2026-01-14.
