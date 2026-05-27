# Análisis de Robustez Multiplataforma — Necktral ERP/CRM

> Versión 1.0 — 2026-05-27  
> Objetivo: Identificar fallos potenciales, cuellos de botella, inconsistencias, huecos y sugerencias para robustecer el sistema multiplataforma.

---

## Resumen Ejecutivo

| Área | Estado | Riesgo |
|------|--------|--------|
| Autenticación/2FA | ✅ Robusto | Bajo |
| Sync Engine (offline) | ✅ Sólido, gaps menores | Medio |
| Accounting Kernel | 🔶 Funcional, no blindado | Medio-Alto |
| Billing/Inventory Kernels | 🔴 Solo scaffolding | Alto |
| Frontend multiplataforma | 🔶 Web OK, mobile pendiente | Medio |
| CI/CD | ✅ Maduro, gaps menores | Bajo |
| Seguridad | 🔶 Enterprise-grade, backlog pendiente | Medio |
| Observabilidad | 🔶 Parcial | Medio |

---

## 1. POSIBLES FALLOS (Failure Modes)

### 1.1 Fallos de Concurrencia

| ID | Componente | Fallo | Impacto | Mitigación actual | Recomendación |
|----|-----------|-------|---------|-------------------|---------------|
| F01 | `FiscalPeriodCloseView` | Race condition: dos cierres simultáneos del mismo período | Doble cierre, journal entries duplicados | `UniqueConstraint` en modelo | Agregar `select_for_update()` en el cierre + validación de estado atómico |
| F02 | `JournalDraftPostView` | Posting concurrente del mismo draft | Double-posting si no hay lock | Sin lock explícito visible | Agregar `select_for_update(nowait=True)` antes de transición de estado |
| F03 | `SyncBatchView` | Batches concurrentes del mismo device con secuencias solapadas | Gaps en `last_accepted_sequence` | `last_accepted_sequence` field existe | Implementar `select_for_update` en Device durante batch + validación secuencia estricta |
| F04 | `IntercompanyTransactionConfirmView` | Dos partes confirman simultáneamente | Estado inconsistente entre entidades | Sin evidencia de locking | Lock pesimista en transacción + FSM guard |
| F05 | `RefreshTokenSession` | Token rotation race (múltiples tabs) | Sesión invalidada innecesariamente | `replaced_by_jti` field | Implementar grace period (ventana de 30s para tokens rotados) |

### 1.2 Fallos de Integridad de Datos

| ID | Componente | Fallo | Impacto | Recomendación |
|----|-----------|-------|---------|---------------|
| F06 | `EconomicEvent.payload` | JSONField sin schema validation | Payloads malformados pasan a GL | Agregar JSON Schema validation por `event_type` en `clean()` |
| F07 | `AppliedCommand.result_ref` | JSONField sin tipado fuerte | Refs inconsistentes entre handlers | Definir TypedDict por `command_type` |
| F08 | `BillingDocument` (kernel) | Sin state machine enforced | Transiciones ilegales posibles | Implementar FSM con `django-fsm` o guards manuales |
| F09 | `StockBalance` (kernel) | Sin constraint de no-negativos | Stock negativo posible sin trigger DB | Agregar `CheckConstraint(condition=Q(quantity__gte=0))` |
| F10 | Audit chain | `prev_hash` en `AppliedCommand` es opcional (blank=True) | Cadena rota si primer comando no tiene prev_hash | Definir valor semilla ("genesis") para primer comando por device |

### 1.3 Fallos de Disponibilidad

| ID | Componente | Fallo | Impacto | Recomendación |
|----|-----------|-------|---------|---------------|
| F11 | PostgreSQL single-node | Punto único de fallo | Downtime total | Plan de réplica read-only + failover (Phase 2) |
| F12 | `AUTH_COOKIE_SECURE=False` default | Cookies no seguras en entornos mal configurados | Intercepción de tokens | Forzar `True` en prod.py (verificar) |
| F13 | Gunicorn workers fijo (4) | Saturación bajo carga | Timeout en auth/sync | Auto-scaling workers basado en CPU cores (`2*cores + 1`) |
| F14 | Sin circuit breaker en `integration` módulo | Cascading failure si servicio externo cae | Backend bloqueado | Implementar circuit breaker pattern (tenacity/pybreaker) |

---

## 2. CUELLOS DE BOTELLA (Bottlenecks)

### 2.1 Base de Datos

| ID | Cuello | Evidencia | Impacto | Recomendación |
|----|--------|-----------|---------|---------------|
| B01 | `AuditEvent` sin particionamiento | Tabla crece ilimitadamente (append-only) | Queries lentos en audit trail | Particionar por `timestamp_server` (mensual) |
| B02 | `AppliedCommand` indexado por `received_at` | Volumen alto en sincronización masiva | Full table scan en reportes | Agregar índice compuesto `(company, command_type, received_at)` |
| B03 | `DeviceRequestNonce` sin cleanup | Anti-replay nonces se acumulan indefinidamente | Tabla crece sin límite | Implementar TTL cleanup (cron/management command) — retener solo 48h |
| B04 | `JournalEntry` + `JournalLine` joins | Reportes contables con muchas líneas | Tiempo de respuesta >2s en trial balance | Materializar saldos incrementales (trigger o batch) |
| B05 | CORS + 18 middlewares | Cada request pasa 18 capas | Overhead en latencia P99 | Audit: medir overhead real; considerar bypass para health/readiness |

### 2.2 Sincronización

| ID | Cuello | Evidencia | Impacto | Recomendación |
|----|--------|-----------|---------|---------------|
| B06 | Batch limit 100 commands | Dispositivos con acumulación >100 requieren múltiples requests | Latencia en reconexión tras offline largo | Implementar compresión + batch streaming (chunks progresivos) |
| B07 | Ed25519 verify por cada comando | CPU-bound en batches grandes | Throttle efectivo en sync heavy | Considerar firma por batch (no por comando) para v3 protocol |
| B08 | `transaction.atomic()` por batch completo | Un comando fallido puede bloquear toda la TX | Lock contention en tabla Device | Evaluar savepoints por comando individual |

### 2.3 Frontend

| ID | Cuello | Evidencia | Impacto | Recomendación |
|----|--------|-----------|---------|---------------|
| B09 | Sin service worker / PWA manifest | Offline-first solo en sync engine backend | Frontend no funciona offline | Implementar service worker con cache estratégico |
| B10 | Sin lazy loading de rutas | 20 pages cargadas potencialmente en bundle | TTI elevado en mobile | Implementar `defineAsyncComponent` + route-level code splitting |
| B11 | Axios sin retry automático | Requests fallidos requieren refresh manual | UX degradada en conexiones inestables | Agregar axios interceptor con retry exponential (3 intentos) |

---

## 3. INCONSISTENCIAS

### 3.1 Arquitecturales

| ID | Inconsistencia | Detalle | Impacto | Corrección |
|----|---------------|---------|---------|------------|
| C01 | Dual `manage.py` | Dos archivos manage.py (raíz + src/) | Confusión en desarrollo | Eliminar uno, documentar el canónico |
| C02 | Módulos vs Kernels duplicados | `apps.modulos.accounting` (vacío) + `apps.kernels.accounting` (real) | Confusión de imports | Eliminar módulos-stub o convertir en re-exports explícitos |
| C03 | Sync v1 vs v2 coexistencia | `apps.modulos.sync` (HMAC legacy) + `apps.modulos.sync_engine` (Ed25519) | Dos paths de autenticación device | Deprecar v1 con timeline, sunset header |
| C04 | `test/` duplicación | `login_module/tests/` vs `login_module/src/tests/` | Tests ejecutados selectivamente | Unificar en una sola ubicación |
| C05 | Naming inconsistente | `estacion_servicios` (español) vs `retail_pos` (inglés) | Confusión naming | Adoptar convención única (español canónico según docs) |

### 3.2 De Contratos

| ID | Inconsistencia | Detalle | Impacto | Corrección |
|----|---------------|---------|---------|------------|
| C06 | Error envelope parcial | `ApiErrorEnvelopeMiddleware` existe pero no todos los views lo usan | Respuestas de error heterogéneas | Auditar todas las views: asegurar que `build_error_envelope` se use universalmente |
| C07 | Throttle scopes incompletos | Solo `auth_login`, `auth_refresh`, `auth_logout`, `me_read`, `me_acl_read` | Endpoints de accounting/sync sin throttle específico | Agregar scopes: `sync_batch`, `accounting_report`, `billing_write` |
| C08 | Audit events sin catálogo cerrado | `write_event` acepta cualquier `event_type` string | Eventos no documentados se infiltran | Crear enum/registry de event_types válidos con validación |
| C09 | RBAC permission strings dispersas | `rbac_permission("sync_engine.enroll_device")` hardcoded | Sin catálogo centralizado | Crear archivo `permissions_registry.py` con todas las perms |

### 3.3 De Frontend-Backend

| ID | Inconsistencia | Detalle | Impacto | Corrección |
|----|---------------|---------|---------|------------|
| C10 | Headers custom sin validación FE | Backend requiere `X-Company-Id` pero FE puede omitirlo | 403 sin mensaje claro | Agregar interceptor axios que inyecte automáticamente |
| C11 | Versión API no versionada en URL | `/api/auth/*`, `/api/accounting/*` sin `/v1/` | Breaking changes sin aviso | Implementar versionado: `/api/v1/auth/*` (o header `Accept-Version`) |
| C12 | OpenAPI schema sin validación en FE | `drf-spectacular` genera schema pero FE no lo consume tipado | Drift entre contratos | Generar tipos TypeScript desde OpenAPI (openapi-typescript) |

---

## 4. HUECOS (Gaps)

### 4.1 Funcionales

| ID | Hueco | Estado actual | Riesgo | Prioridad |
|----|-------|---------------|--------|-----------|
| G01 | **Billing kernel sin lógica** | Solo modelos (BillingSequence, BillingDocument, BillingLine) | No se puede facturar | 🔴 CRÍTICO |
| G02 | **Inventory kernel sin lógica** | Solo modelos (Warehouse, InventoryItem, StockBalance) | No hay control de stock | 🔴 CRÍTICO |
| G03 | **Payments kernel sin lógica** | Solo modelos (PaymentTransaction) | No se procesan pagos | 🔴 CRÍTICO |
| G04 | **CEC sin control plane** | Módulo existe pero sin validación cruzada | Sin reconciliación automática | 🟡 ALTO |
| G05 | **Outbox pattern no implementado** | `source_outbox_event_id` en EconomicEvent pero sin outbox real | Eventos perdidos entre módulos | 🟡 ALTO |
| G06 | **Mobile app inexistente** | Frontend es solo web (Quasar sin Capacitor/Cordova) | Sin operación móvil offline | 🟡 ALTO |
| G07 | **Reporting kernel limitado** | Solo vistas de consolidación | Sin exports PDF/Excel, sin scheduled reports | 🟡 MEDIO |
| G08 | **Multi-moneda parcial** | `FxRate` + revaluación existe, pero sin soporte en Billing/Inventory | Inconsistencia en documentos multi-currency | 🟡 MEDIO |

### 4.2 No-Funcionales

| ID | Hueco | Estado actual | Riesgo | Prioridad |
|----|-------|---------------|--------|-----------|
| G09 | **Sin health check endpoint dedicado** | Solo `HealthView` en accounting | Sin readiness/liveness para orquestador | 🟡 ALTO |
| G10 | **Sin métricas Prometheus** | `config.metrics.record_sync_batch` existe pero sin export | No hay dashboards operativos | 🟡 ALTO |
| G11 | **Sin rate limiting en sync batch** | Throttle solo en auth endpoints | Dispositivo comprometido puede saturar | 🟡 ALTO |
| G12 | **Sin backup automatizado** | `compose.prod.yaml` no incluye backup de pgdata | Pérdida de datos posible | 🔴 CRÍTICO |
| G13 | **Sin test E2E** | Backend 72 unit tests, Frontend 1 test | Sin validación de flujos completos | 🟡 ALTO |
| G14 | **Sin chaos testing** | No hay simulación de fallos | Comportamiento desconocido bajo stress | 🟡 MEDIO |
| G15 | **Sin API versioning** | Breaking changes afectan todos los clientes | Imposible evolucionar sin romper | 🟡 MEDIO |
| G16 | **Frontend sin tests** | Solo 1 archivo de test (vitest) | Regresiones no detectadas | 🟡 ALTO |

---

## 5. SUGERENCIAS PARA ROBUSTECER EL SISTEMA MULTIPLATAFORMA

### 5.1 Prioridad Inmediata (Sprint 1-2, semanas 1-4)

#### S01: Blindar concurrencia en operaciones críticas
```python
# accounting/views.py - FiscalPeriodCloseView
with transaction.atomic():
    period = FiscalPeriod.objects.select_for_update(nowait=True).get(pk=period_id)
    if period.status != FiscalPeriod.Status.OPEN:
        raise ValidationError("Period already closed")
    # ... close logic
```

#### S02: Agregar constraint de stock no-negativo
```python
# inventarios/models.py
class StockBalance(models.Model):
    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=Decimal("0")),
                name="ck_stock_balance_non_negative",
            ),
        ]
```

#### S03: Implementar cleanup de nonces expirados
```python
# sync_engine/management/commands/cleanup_expired_nonces.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.modulos.sync_engine.models import DeviceRequestNonce

class Command(BaseCommand):
    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=48)
        deleted, _ = DeviceRequestNonce.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(f"Deleted {deleted} expired nonces")
```

#### S04: Agregar throttle a sync batch
```python
# settings/base.py
"DEFAULT_THROTTLE_RATES": {
    ...
    "sync_batch": "30/min",  # por device
    "accounting_report": "20/min",
}
```

#### S05: Health check unificado
```python
# config/views.py
class SystemHealthView(APIView):
    permission_classes = [AllowAny]
    
    def get(self, request):
        checks = {
            "database": self._check_db(),
            "redis": self._check_redis(),  # si aplica
            "disk": self._check_disk(),
        }
        status_code = 200 if all(checks.values()) else 503
        return Response({"status": "healthy" if status_code == 200 else "degraded", "checks": checks}, status=status_code)
```

### 5.2 Prioridad Alta (Sprint 3-4, semanas 5-8)

#### S06: Implementar FSM en Billing
```python
# Billing document lifecycle
STATES = {
    "DRAFT": ["VALIDATED"],
    "VALIDATED": ["POSTED", "CANCELLED"],
    "POSTED": ["VOIDED"],
    "VOIDED": [],
    "CANCELLED": [],
}

def transition(document, target_state):
    if target_state not in STATES.get(document.status, []):
        raise ValidationError(f"Cannot transition from {document.status} to {target_state}")
    document.status = target_state
```

#### S07: Generar tipos TypeScript desde OpenAPI
```json
// package.json scripts
{
  "generate:api": "openapi-typescript http://localhost:8000/api/schema/ -o src/api/types.ts"
}
```

#### S08: Implementar Service Worker para PWA
```typescript
// frontend/src-pwa/custom-service-worker.ts
import { precacheAndRoute } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { NetworkFirst, CacheFirst } from 'workbox-strategies';

precacheAndRoute(self.__WB_MANIFEST);

// API calls: network-first with fallback
registerRoute(
  ({url}) => url.pathname.startsWith('/api/'),
  new NetworkFirst({ cacheName: 'api-cache', networkTimeoutSeconds: 5 })
);
```

#### S09: Retry interceptor en Axios
```typescript
// frontend/src/boot/axios.ts
import axios from 'axios';

const MAX_RETRIES = 3;
axios.interceptors.response.use(null, async (error) => {
  const config = error.config;
  if (!config || config._retryCount >= MAX_RETRIES) return Promise.reject(error);
  if (error.response?.status >= 500 || !error.response) {
    config._retryCount = (config._retryCount || 0) + 1;
    const delay = Math.pow(2, config._retryCount) * 1000;
    await new Promise(r => setTimeout(r, delay));
    return axios(config);
  }
  return Promise.reject(error);
});
```

#### S10: Backup automatizado en producción
```yaml
# compose.prod.yaml - agregar servicio
  db-backup:
    image: prodrigestivill/postgres-backup-local:16
    environment:
      POSTGRES_HOST: db
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      SCHEDULE: "@daily"
      BACKUP_KEEP_DAYS: 30
    volumes:
      - ./backups:/backups
    depends_on:
      db:
        condition: service_healthy
```

### 5.3 Prioridad Media (Sprint 5-8, semanas 9-16)

#### S11: Capacitor para app móvil nativa
```bash
# Quasar ya soporta Capacitor
quasar mode add capacitor
# Agregar plugins offline
npm install @capacitor/filesystem @capacitor/network @capacitor/preferences
```

#### S12: Event registry cerrado
```python
# audit/event_registry.py
from enum import StrEnum

class AuditEventType(StrEnum):
    # Auth
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGOUT = "LOGOUT"
    TWO_FACTOR_SETUP = "TWO_FACTOR_SETUP"
    TWO_FACTOR_VERIFIED = "TWO_FACTOR_VERIFIED"
    # Sync
    SYNC_BATCH_RECEIVED = "SYNC_BATCH_RECEIVED"
    SYNC_COMMAND_APPLIED = "SYNC_COMMAND_APPLIED"
    SYNC_AUTH_REJECTED = "SYNC_AUTH_REJECTED"
    DEVICE_ENROLLED = "DEVICE_ENROLLED"
    DEVICE_REVOKED = "DEVICE_REVOKED"
    # Accounting
    JOURNAL_POSTED = "JOURNAL_POSTED"
    PERIOD_CLOSED = "PERIOD_CLOSED"
    FX_REVALUATION = "FX_REVALUATION"
    # ... catálogo completo

def validate_event_type(event_type: str) -> None:
    if event_type not in AuditEventType.__members__.values():
        raise ValueError(f"Unknown event type: {event_type}")
```

#### S13: Permissions registry centralizado
```python
# common/permissions_registry.py
"""Catálogo centralizado de permisos RBAC del sistema."""

PERMISSIONS = {
    # Sync Engine
    "sync_engine.create_enrollment_challenge": "Crear challenge de enrollment de dispositivo",
    "sync_engine.enroll_device": "Enrollar dispositivo con challenge",
    "sync_engine.revoke_device": "Revocar dispositivo",
    "sync_engine.list_devices": "Listar dispositivos",
    # Accounting
    "accounting.post_journal": "Postear asiento contable",
    "accounting.close_period": "Cerrar período fiscal",
    "accounting.reverse_entry": "Reversar asiento",
    # Billing
    "billing.create_document": "Crear documento fiscal",
    "billing.void_document": "Anular documento fiscal",
    # ...
}
```

#### S14: Prometheus metrics export
```python
# config/metrics.py - ampliar
from prometheus_client import Counter, Histogram, generate_latest

sync_batch_total = Counter("necktral_sync_batch_total", "Total sync batches", ["status"])
sync_batch_duration = Histogram("necktral_sync_batch_duration_seconds", "Batch processing time")
api_request_duration = Histogram("necktral_api_request_duration_seconds", "API latency", ["method", "endpoint"])

# Exponer en /metrics (solo internal)
class MetricsView(APIView):
    permission_classes = [AllowAny]  # Proteger por IP/network policy
    def get(self, request):
        return HttpResponse(generate_latest(), content_type="text/plain")
```

---

## 6. MATRIZ DE RIESGOS CONSOLIDADA

| Prioridad | ID | Riesgo | Probabilidad | Impacto | Esfuerzo |
|-----------|----|--------|--------------|---------|----------|
| 🔴 P0 | G12 | Sin backup automatizado | Alta | Catastrófico | 2h |
| 🔴 P0 | F01 | Race condition en cierre de período | Media | Alto | 4h |
| 🔴 P0 | G01-G03 | Kernels sin lógica (billing/inventory/payments) | Certain | Bloqueante | 2-4 semanas |
| 🟡 P1 | B03 | Nonces sin cleanup (tabla crece infinito) | Alta | Medio | 2h |
| 🟡 P1 | G11 | Sin throttle en sync batch | Media | Alto | 2h |
| 🟡 P1 | F05 | Token rotation race en multi-tab | Media | Medio | 4h |
| 🟡 P1 | G09 | Sin health check unificado | Alta | Medio | 3h |
| 🟡 P1 | G16 | Frontend sin tests | Alta | Alto | 1 semana |
| 🟡 P1 | C06 | Error envelope inconsistente | Alta | Medio | 1 día |
| 🟡 P1 | G10 | Sin métricas Prometheus | Media | Medio | 1 día |
| 🟢 P2 | B06 | Batch limit 100 insuficiente offline largo | Baja | Medio | 2 días |
| 🟢 P2 | C11 | Sin API versioning | Media | Alto (futuro) | 1 semana |
| 🟢 P2 | G06 | Sin mobile app | Alta | Alto | 2-4 semanas |
| 🟢 P2 | S08 | Sin PWA/service worker | Alta | Medio | 3 días |
| 🟢 P2 | C12 | Drift de tipos FE-BE | Alta | Medio | 1 día |

---

## 7. PLAN DE ACCIÓN RECOMENDADO

### Fase 1: Blindaje Crítico (Semanas 1-2)
- [ ] **S10**: Backup automatizado en compose.prod.yaml
- [ ] **S01**: `select_for_update` en FiscalPeriodCloseView y JournalDraftPostView
- [ ] **S03**: Management command para cleanup de nonces
- [ ] **S04**: Throttle scope para sync_batch
- [ ] **S05**: Health check unificado (`/api/health/`)
- [ ] **S02**: Constraint non-negative en StockBalance

### Fase 2: Consistencia y Observabilidad (Semanas 3-4)
- [ ] **C06**: Auditar y unificar error envelope en todas las views
- [ ] **C07**: Agregar throttle scopes faltantes
- [ ] **S14**: Métricas Prometheus básicas
- [ ] **S12**: Event registry cerrado con validación
- [ ] **S13**: Permissions registry centralizado
- [ ] **F05**: Grace period para token rotation

### Fase 3: Multiplataforma (Semanas 5-8)
- [ ] **S08**: Service worker PWA (cache offline)
- [ ] **S09**: Axios retry interceptor
- [ ] **S07**: Generación de tipos TypeScript desde OpenAPI
- [ ] **S11**: Capacitor setup para mobile
- [ ] **G16**: Suite de tests frontend (≥20 tests)
- [ ] **G13**: Tests E2E con Playwright

### Fase 4: Kernels Funcionales (Semanas 9-16)
- [ ] **G01**: Billing kernel — FSM + tax calc + numerations
- [ ] **G02**: Inventory kernel — movements + FIFO/avg valuation
- [ ] **G03**: Payments kernel — transaction lifecycle
- [ ] **G05**: Outbox pattern implementation
- [ ] **G04**: CEC control plane formalizado

---

## 8. MÉTRICAS DE ÉXITO

| Métrica | Actual | Objetivo Fase 1 | Objetivo Final |
|---------|--------|-----------------|----------------|
| Test coverage backend | 85% | 90% | 95% |
| Test coverage frontend | ~0% | 30% | 70% |
| P99 latency API | Desconocido | <500ms | <200ms |
| Uptime (con backup) | Sin medición | 99.5% | 99.9% |
| Sync batch throughput | ~30 req/min | 60 req/min | 120 req/min |
| Security backlog items | 7 | 3 | 0 |
| Time to recover (TTR) | Desconocido | <1h | <15min |

---

## Referencias

- [ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md](ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md)
- [CONTRACT_PACK_v2.0.md](CONTRACT_PACK_v2.0.md)
- [ADDENDUM_SEGURIDAD_v1.1.md](ADDENDUM_SEGURIDAD_v1.1.md)
- [ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md](ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md)
- [QUALITY_COVERAGE_DIAGNOSTIC.md](QUALITY_COVERAGE_DIAGNOSTIC.md)
- [DIAGNOSTICO_SISTEMA_2026-03.md](DIAGNOSTICO_SISTEMA_2026-03.md)
