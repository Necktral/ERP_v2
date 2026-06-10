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
