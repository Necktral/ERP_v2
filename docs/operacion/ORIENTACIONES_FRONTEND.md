# Orientaciones para el frontend (acumulado)

> Documento donde se anotan las directrices de UI/UX que surgen mientras se trabaja el backend,
> para que el frontend las implemente coherentemente. Escrito por Claude (backend) a pedido del dueño.

## 1. Medidor de fortaleza de contraseña (con indicadores de color)

**Requisito del dueño:** el nivel de confianza de la contraseña debe mostrarse con **indicadores de color
en degradado: verde = buena, rojo = mala** (rojo → amarillo → verde según mejora).

**Backend ya disponible (no hardcodear los niveles):**
- `GET /auth/bootstrap/status/` (público) devuelve `password_policy`:
  ```json
  {
    "min_length": 10,
    "min_classes": 3,
    "classes": ["minúsculas", "mayúsculas", "números", "símbolos"],
    "disallow_common": true,
    "disallow_numeric_only": true
  }
  ```
  Es la **fuente única**: derivada de `AUTH_PASSWORD_VALIDATORS`. El medidor debe consumirla para que
  nunca se desincronice de lo que el backend exige.
- `POST /auth/bootstrap/init/` ahora exige `password_confirm` (debe coincidir con `password`); si no,
  responde 400 con el error en `error.details.password_confirm`.

**Implementado de referencia** (en working tree): `frontend/src/pages/BootstrapWizardPage.vue` — campo de
confirmación + `q-linear-progress` con `:color` calculado (`negative` → `warning` → `positive`) y checklist
de criterios. **Aplicar el MISMO patrón** en los demás formularios de contraseña (p. ej.
`ForcePasswordChangePage.vue`, cambio de contraseña, alta de usuarios). Usar **tokens de color de Quasar**
(`negative/warning/positive`) o `--app-*`, nunca hex fijos, para respetar multi-tema.

**Cálculo sugerido del nivel** (alineado al backend): score = (longitud ≥ `min_length` ? 1 : 0) + nº de clases
presentes (minúscula/mayúscula/número/símbolo); `ratio = score/5`. Color: rojo si no cumple política;
amarillo si parcial; verde cuando cumple `min_length` y `≥ min_classes`.

## 2. Logo y nombre configurables al crear el holding (branding)

**Estado:** el **nombre** ya es configurable hoy (`BootstrapOrgView` recibe `holding_name`/`company_name`).
El **logo NO existe** todavía en el modelo, y el topbar tiene la marca hardcodeada
(`MainLayout.vue` "Necktral Console").

**Diseño recomendado (por qué así):**
- **A nivel HOLDING** (identidad de la consola), con override por empresa opcional a futuro.
- **Guardar el logo como data-URL base64 en un `TextField`, NO como `FileField`/MEDIA.** Razón: el sistema es
  **offline-first** (DB local + memoria + Google Drive + sync); un `FileField` obligaría a un media-server y a
  sincronizar binarios aparte, y la imagen se rompería offline. En base64 viaja dentro del mismo JSON syncable.
- **Preferir SVG** (diminuto, nítido a cualquier escala, ideal multi-tema) o PNG transparente. Tope de tamaño
  (p. ej. rechazar > 256 KB). Considerar `logo` + `logo_dark` (variante para tema oscuro).
- **Frontend:** en el form de `/bootstrap` (paso Organización) un cargador que **redimensiona en cliente a
  ~256 px y convierte a data-URL** antes de enviar; y el topbar lee `display_name`/`logo` del store de bootstrap
  (no texto fijo), eligiendo la variante por tema activo.

**Backend pendiente (lo implemento cuando se confirme):** modelo `HoldingBranding`
(`org_unit` OneToOne a HOLDING, `display_name`, `tagline`, `logo_data_url`, `logo_dark_data_url`, `logo_mime`);
aceptar `logo` opcional en `BootstrapOrgSerializer`; exponer branding en `/auth/bootstrap/session/`. Es aditivo
(migración nueva + ratchet de `migration_safety_baseline.json`).

## 3. Rectificación del diagnóstico multi-empresa (gaps reales por capa)

1. **"Sin switcher de empresa" → sobredimensionado.** SÍ es re-seleccionable vía el ítem "Contexto operativo"
   del drawer (`MainLayout.vue`) que reabre `SelectContextPage` precargada. El gap real es de **ergonomía**: no
   hay quick-switcher en el topbar (el badge es solo lectura). **Frontend:** agregar un switcher en el topbar.
2. **"Holding invisible" → subestima el backend.** El holding existe y está validado (`OrgUnit` HOLDING>COMPANY>
   BRANCH; `iam/selectors.py` resuelve scope holding). El gap real: `/me/acl` **aplana** y no manda `holding_id`.
   **Mixto:** backend = exponer `holding_id` en el ACL (mío, cuando se pida); frontend = agrupar/vista consolidada.
3. **"Branch on-demand" → correcto.** `axios.ts` manda `X-Branch-Id` solo si hay sucursal activa; no hay flujo
   "operación que exige sucursal → pedirla en el momento". **Frontend:** modal "elegí sucursal" cuando la
   operación lo requiera (el backend ya distingue con/sin sucursal).

## 4. IDP — Captura y revisión de documentos (backend F1 listo)

El backend del subsistema IDP (módulo `documents`) ya expone la **fase F1** (captura → OCR → revisión).
Detalle completo en `backend/src/apps/modulos/documents/README.md`. Lo que el frontend debe construir:

**a) Captura/subida** (`POST /api/documents/scans/upload/`, permiso `documents.scan.create`):
- Cámara o selector de archivo → la imagen se manda **en base64** (`image_base64`, acepta data-URL),
  con `doc_type` (`GENERAL`/`INVOICE`/`FUEL_TICKET`/`PAYROLL`) y `content_type?`, `branch_id?`.
- **Offline-first (híbrido):** si no hay red, guardar la imagen local y reintentar el `POST` al
  reconectar (mismo endpoint). El OCR lo corre el servidor; el cliente NO hace OCR.
- Comprimir/redimensionar antes de enviar (tope backend: 8 MB).

**b) Bandeja de revisión** (`GET /api/documents/scans/?status=PROCESSED`, permiso `documents.scan.read`):
- Listar documentos por estado (`PENDING_OCR → PROCESSED → REVIEWED`, o `FAILED`). Mostrar el estado
  con color (p. ej. `PROCESSED` ámbar pendiente de revisar, `REVIEWED` verde, `FAILED` rojo).
- Detalle (`GET /scans/<id>/`): mostrar el `ocr_text` junto a la imagen para cotejar.

**c) Confirmación humana** (`POST /api/documents/scans/<id>/review/`, permiso `documents.scan.review`):
- Form para corregir/confirmar `extracted_fields` (F2 los llenará automáticamente) y opcional `doc_type`
  → marca `REVIEWED`. Es el *human-in-the-loop* del pipeline (el OCR nunca es 100%).

Usar contexto de empresa (`X-Company-Id`) como el resto; permisos vía el ACL (ya sembrados en `company_admin`).

## 5. Destino post-bootstrap → onboarding, NO `/dashboard`

**Problema:** `BootstrapWizardPage.createOrg()` hace `router.push('/dashboard')` al terminar el alta de la
organización. Eso es incorrecto para una empresa recién creada (vacía):
- `/dashboard` **no es público**: su API exige `report.dashboard.read`. (El menú lo mostraba porque el ACL del
  superuser devuelve `["*"]`, pero el backend gateaba con permiso scopeado → daba **403**.)
- El destino correcto tras crear la empresa es el **onboarding** que el propio flujo describe:
  **Puestos → Trabajadores → Asignar → Provisionar** (RR.HH.), no un dashboard sin datos.

**Backend (ya resuelto):** `company_admin` (rol que el bootstrap asigna al dueño) ahora incluye los permisos
de reporting/dashboard (`report.dashboard.read`, `report.dataset.read`, …) — así, si el dueño navega a
`/dashboard` más tarde, **no recibe 403**. Confirmado por `test_company_admin_role_grants_reporting_dashboard_access`.

**Frontend (a cambiar):** en `BootstrapWizardPage.vue`, reemplazar el `router.push('/dashboard')` final por el
**inicio del onboarding** — la ruta de RR.HH. → Puestos (`UI_ROUTE_PATHS.humanResourcesPositions`), o un "home de
onboarding" con los 4 pasos. El dueño ya tiene `hr.*`/`org.*`/`iam.users.create`, así que esa ruta no da 403.
Opcional: usar `is_fresh`/`setup_required` del bootstrap para decidir onboarding vs. dashboard en logins futuros.

## 6. Landing por defecto y módulos restringidos vs. públicos

**Regla general (no solo post-bootstrap):** el **landing de cualquier login debe ser un "home operativo" NO
restringido** — a donde cae todo usuario autenticado con contexto, sin exigir un permiso de módulo. Módulos como
**Dashboard y Reportes son RESTRINGIDOS** (solo entra personal con permiso, p. ej. `report.dashboard.read`):
son **destinos**, nunca la puerta de entrada. El dashboard es **información/análisis**, no un menú ni un landing.

**Hallazgo concreto a corregir (frontend):** en `frontend/src/router/routes.ts` la ruta `/dashboard` **NO declara
`requiredPermissions`** (solo `requiresContext`), mientras que `/analytics` sí exige `report.dashboard.read`. O sea,
la ruta del dashboard está **menos protegida** que la de analítica y que el propio API. **Fix:** agregar
`requiredPermissions: ['report.dashboard.read']` (o el permiso que corresponda) a la ruta `/dashboard`, para que el
control no dependa solo de ocultar el ítem del menú (ocultar ≠ autorizar).

**El menú y las opciones del landing** se arman por `effective_modules = allowed (permisos ACL) ∩ enabled (módulos
de la empresa)` (`MainLayout.vue` + catálogo `org/module_catalog.py`). El home operativo muestra **solo** lo que el
usuario puede ver.

**Secuencia de onboarding (complementa §5) — orden y porqué:**
1. **Puestos** (`POST /hr/positions/`) + **mapeo puesto→roles** (`PUT /hr/positions/{id}/roles/`, `PositionRoleMap`).
   Regla clave: **el PUESTO define el permiso, no la persona** (se arma una vez por puesto y se reutiliza).
2. **Trabajadores** (`POST /hr/employees/`).
3. **Asignar** trabajador → puesto + sucursal (`POST /hr/employees/{id}/assignments/`) → hereda los roles del puesto
   (`RoleAssignment` con `origin=POSITION`).
4. **Provisionar usuario** (`POST /hr/employees/{id}/provision-user/`) → usuario + contraseña temporal, **solo** para
   quienes necesitan acceso al sistema.

**Implicación de diseño:** el "home de onboarding" guía esos 4 pasos; el **dashboard analítico recién tiene sentido
cuando hay datos + un usuario con permiso** (reportes/dashboards van "de último").

## 7. Home de onboarding — contrato completo de los 4 pasos (backend listo y verde)

> **Estado backend:** TODO el recorrido `Empresa → ① Puestos(+roles) → ② Trabajadores → ③ Asignar → ④ Provisionar`
> ya está implementado, cableado y **probado** (módulo `hr`, 15/15 tests verdes). El módulo `human_resources` es
> **core + `default_enabled=True`** → siempre aparece en el menú. El dueño (rol `company_admin` que asigna el
> bootstrap) **ya tiene todos los permisos** de la tabla de abajo, así que ninguna pantalla del flujo da 403.
> Este apartado es la **especificación para que el frontend construya el home de onboarding**. Todo en español,
> tokens `--app-*` (multi-tema). Todos los endpoints exigen contexto de empresa (`X-Company-Id`).

**Regla rectora (repetir en la UI):** *el PUESTO define el permiso, no la persona.* El trabajador **hereda** los
roles de su puesto vía la asignación; la reconciliación es **automática** (RoleAssignment `origin=POSITION`) al
crear asignación / provisionar / cambiar el mapeo de roles / finalizar asignación. **El frontend NO asigna roles
directo al usuario en este flujo.**

### Paso ① — Puestos (con roles)
- **Listar:** `GET /hr/positions/` → `{count, limit, offset, results:[{id, name, code, is_active}]}` · perm `hr.position.read`.
- **Crear:** `POST /hr/positions/` body `{name, code?}` → `201 {id}` · perm `hr.position.create`.
- **Editar:** `PATCH /hr/positions/{id}/` body `{name?, code?, is_active?}` → `{ok:true}` · perm `hr.position.update`.
- **Mapear puesto→roles** (la parte "con roles"): `PUT /hr/positions/{id}/roles/`
  body `{maps:[{role_id, scope_mode:"BRANCH"|"COMPANY"}]}` → `{ok:true}` · perm `hr.position.roles.update`.
  - **Semántica REEMPLAZO TOTAL (replace-all):** el `PUT` desactiva todos los mapeos previos y deja activos solo
    los enviados. Para **quitar** un rol, reenviá la lista sin él; para **vaciar**, mandá `{maps:[]}`.
  - **Selector de roles:** `GET /rbac/roles/` → `{results:[{id, name, description, is_active}]}` · perm `rbac.roles.read` (el dueño lo tiene).
- **⚠️ Regla de scope (decisión de UX, importantísima):**
  - `scope_mode="COMPANY"` → otorga el rol **a nivel empresa** (aplica aunque la asignación no tenga sucursal).
  - `scope_mode="BRANCH"` (default) → el rol **solo se otorga si la asignación tiene `branch_id`** (paso ③).
  - Consecuencia: si los roles de un puesto son **BRANCH**, la asignación del trabajador **debe** incluir sucursal,
    o el trabajador queda **sin permisos efectivos**. La UI debería avisar esto al mapear roles BRANCH.

### Paso ② — Trabajadores
- **Listar:** `GET /hr/employees/` · perm `hr.employee.read`. Cada fila ya trae lo que la UI necesita para pintar estado:
  `{id, employee_code, first_name, last_name, phone, email, is_active, party_id, party_display_name, party_tax_id,
  party_national_id, linked_user_id, linked_username, has_active_assignment, active_assignments:[{id, position_id,
  position_name, branch_id, branch_name, started_at}]}`.
- **Crear:** `POST /hr/employees/` body `{first_name, last_name?, employee_code?, phone?, email?, is_active?, party_id?, linked_user_id?}`
  → `201 {id}` · perm `hr.employee.create`. `party_id` es opcional; si se manda, debe pertenecer a la misma empresa
  (asegura el rol de Party `EMPLOYEE`).
- **Editar:** `PATCH /hr/employees/{id}/` (mismos campos, todos opcionales) · perm `hr.employee.update`.

### Paso ③ — Asignar (trabajador → puesto + sucursal)
- **Listar asignaciones:** `GET /hr/employees/{id}/assignments/` →
  `{results:[{id, is_active, position_id, position_name, branch_id, branch_name, started_at, ended_at}]}` · perm `hr.assignment.read`.
- **Crear:** `POST /hr/employees/{id}/assignments/` body `{position_id, branch_id?}` → `201 {id}` · perm `hr.assignment.create`.
  Si el empleado ya tiene usuario, **reconcilia roles automáticamente** al crear.
- **Finalizar:** `POST /hr/employees/{id}/assignments/{aid}/end/` → idempotente `{ok:true}` · perm `hr.assignment.end`.
- **Selector de sucursales:** `GET /org/branches/` · perm `org.branch.read` (el dueño lo tiene).
- Un trabajador puede tener **varias asignaciones activas**. Recordá la regla de scope del paso ① para `branch_id`.

### Paso ④ — Provisionar acceso (solo a quien necesita entrar al sistema)
- `POST /hr/employees/{id}/provision-user/` body `{username, email?, temp_password?}`
  → `201 {user_id, username, temp_password}` · perms `iam.users.create` **+** `hr.employee.update`.
- **Precondición dura:** el empleado **debe tener una asignación activa** (paso ③); si no → `400` con
  `"El empleado no tiene ninguna asignación activa…"`. Si **ya** tiene usuario vinculado → `409` conflicto.
- **La `temp_password` se devuelve UNA sola vez** en la respuesta (si no se envía, el backend genera una de 12
  caracteres). El usuario nace con `must_change_password=True` → en su primer login cae en la pantalla de cambio
  de contraseña (ver §1). **El frontend DEBE mostrar/permitir copiar la `temp_password` en ese momento**: NO se
  puede recuperar después, solo **regenerar**.
- **Regenerar temporal:** `POST /hr/employees/{id}/reset-temp-password/` → `200 {user_id, username, temp_password}`
  (mismos permisos; requiere linked_user + asignación activa, si no `409`).
- **Revocar acceso:** `POST /hr/employees/{id}/revoke-access/` body `{disable_user?:bool}` → desactiva roles
  `POSITION` y memberships del usuario en la empresa; con `disable_user:true` además desactiva el usuario **solo si**
  no le quedan memberships activas en otra org_unit.

### Orden y dependencias (para no chocar)
1. **③ antes de ④** (provisionar exige asignación activa).
2. **① con roles antes de ③** es lo ideal: así, al provisionar, la reconciliación ya otorga permisos. Si el mapeo de
   roles se hace **después**, no pasa nada: `PUT …/roles/` **reconcilia** a los empleados ya asignados a ese puesto.

### Home de onboarding (UI)
- **4 tarjetas/pasos** con estado **derivado de los `count`** de cada lista: ① `GET /hr/positions/` (`count>0`),
  ② `GET /hr/employees/`, ③ trabajador con `has_active_assignment`, ④ trabajador con `linked_user_id`.
- Es el **landing post-bootstrap** (§5/§6), **no** el dashboard. Mostrar solo lo permitido por `effective_modules`.
- Cada paso con su **descripción/ayuda en español** (qué es y por qué, p. ej. "El puesto define qué puede hacer la
  persona; lo configurás una vez y se reutiliza").

### Endpoint resumen de onboarding (CONSTRUIDO y probado)
Para pintar el home en **una sola llamada** (en vez de 4):

- `GET /hr/onboarding/summary/` · perm `hr.employee.read` (el dueño lo tiene) · scope `request.company`.
- Respuesta:
  ```json
  {
    "positions_count": 1,
    "positions_with_roles": 1,
    "employees_count": 1,
    "employees_assigned": 1,
    "employees_provisioned": 0,
    "next_step": "PROVISIONING",
    "complete": false
  }
  ```
- **`next_step`** = primer paso incompleto en orden canónico; valores:
  `"POSITIONS" → "POSITION_ROLES" → "EMPLOYEES" → "ASSIGNMENTS" → "PROVISIONING" → "DONE"`.
  `complete` es `true` solo cuando `next_step == "DONE"`.
- **Criterios de cada contador:** `positions_with_roles` = puestos con ≥1 mapeo de rol activo;
  `employees_assigned` = trabajadores con ≥1 asignación activa; `employees_provisioned` = trabajadores con usuario.
- **Nota:** provisionar es **opcional por trabajador** (solo quien necesita entrar); aquí se usa como último paso del
  recorrido guiado. La UI puede tratar `PROVISIONING` como paso saltable y dar el onboarding por "suficiente" sin él.
- El frontend igual puede derivar todo de los `count` de cada lista; este endpoint es solo conveniencia/rendimiento.
