# Addendum Seguridad v1.0 — Backlog operativo (corto plazo)

Version: v1.0  
Fecha: 2026-02-07  
Estado: **Backlog ejecutable (vivo)**

Este backlog traduce el corto plazo del addendum a issues/epicas listas para carga.

## Estado actual (2026-02-08)

- ✅ Autenticacion por cookies HttpOnly + CSRF en SPA (sin `localStorage`).
- ✅ CSP base enforce + report-only para `connect-src` con endpoint de reportes.
- ✅ Refresh tokens persistidos y revocables por sesion.
- ✅ Politica de contrasenas reforzada (longitud + complejidad).
- ✅ 2FA TOTP para admins (setup + confirmacion + QR).
- ✅ Security CI blocking (gitleaks, pip-audit, npm audit).

---

## EPICA A1 — Hardening anti-XSS en frontend (CSP y sanitizacion)

**Objetivo**
Reducir el riesgo de XSS y reforzar el hardening del frontend/CSP.

**Alcance**
Frontend Vue/Quasar y politicas CSP en backend/proxy.

**Tareas (issues sugeridas)**

- [ ] Auditoria de superficies XSS en frontend (buscar `v-html`, HTML crudo, interpolaciones no escapadas).
- [ ] Remover o sanitizar puntos identificados (documentar cada decision).
- [ ] Endurecer CSP con directivas faltantes (base-uri, object-src, frame-ancestors, connect-src).
- [ ] Remover `unsafe-inline` cuando sea viable (o definir nonces/hashes si aplica).
- [ ] Validar CSP en runtime y registrar excepciones justificadas.

**DoD**

- No hay `v-html` sin sanitizacion.
- CSP estricta aplicada en runtime y verificada.
- PoC de XSS no ejecuta codigo.

**Riesgos**

- CSP muy estricta puede romper UI; iterar con pruebas.

**Labels sugeridas**
`security`, `frontend`, `csp`, `high`

---

## EPICA A2 — Forzar HTTPS y HSTS en produccion

**Objetivo**
Garantizar cifrado obligatorio y evitar downgrade a HTTP.

**Alcance**
Nginx o terminador TLS + settings prod de Django.

**Tareas (issues sugeridas)**

- [ ] Confirmar terminacion TLS y rutas HTTP/HTTPS.
- [ ] Configurar redireccion HTTP->HTTPS en terminador TLS.
- [ ] Agregar HSTS con `max-age` >= 6 meses e `includeSubDomains` si aplica.
- [ ] Alinear settings prod: `SECURE_PROXY_SSL_HEADER`, `SECURE_SSL_REDIRECT`, cookies `Secure`.
- [ ] Documentar hardening minimo en docs.

**DoD**

- `curl -I` confirma redirect y `Strict-Transport-Security`.
- Cookies sensibles marcadas `Secure`.
- Documentacion actualizada.

**Riesgos**

- HSTS sin TLS valido puede bloquear acceso.

**Labels sugeridas**
`security`, `ops`, `hsts`, `high`

---

## EPICA A3 — Rate limiting y control de abuso

**Objetivo**
Limitar abuso de endpoints y prevenir degradacion.

**Alcance**
Nginx/WAF y throttling DRF.

**Tareas (issues sugeridas)**

- [ ] Definir rutas criticas (auth, listados pesados, escrituras masivas).
- [ ] Configurar rate limiting por ruta en Nginx.
- [ ] Configurar throttling en DRF por tipo de endpoint.
- [ ] Ajustar paginacion maxima en listados grandes.
- [ ] Verificar 429 y logging de eventos.

**DoD**

- 429 al exceder limites definidos.
- Uso normal no bloqueado.

**Riesgos**

- Limites muy bajos pueden bloquear usuarios legitimos.

**Labels sugeridas**
`security`, `backend`, `throttle`, `high`

---

## EPICA A4 — Redaccion de datos sensibles en auditoria

**Objetivo**
Evitar fuga de datos sensibles en bitacora sin perder trazabilidad.

**Alcance**
Modulo de auditoria y permisos de lectura.

**Tareas (issues sugeridas)**

- [ ] Definir allowlist por entidad para campos auditables.
- [ ] Implementar filtrado de `before_snapshot`/`after_snapshot`.
- [ ] Sanitizar metadatos (user-agent, IP si corresponde).
- [ ] Validar permisos RBAC de lectura de bitacora.
- [ ] Agregar tests de redaccion y de integridad HMAC.

**DoD**

- Tests fallan si se intenta auditar campos prohibidos.
- Verificacion de integridad sigue pasando.

**Riesgos**

- Filtrado excesivo puede reducir utilidad forense.

**Labels sugeridas**
`security`, `audit`, `backend`, `high`

---

## EPICA A5 — Gobernanza de secretos

**Objetivo**
Evitar secretos en repo y habilitar rotacion segura por entorno.

**Alcance**
CI, documentacion y manejo de variables de entorno.

**Tareas (issues sugeridas)**

- [ ] Agregar verificacion de secretos en CI (si falta).
- [ ] Verificar que no existan secretos en el repo.
- [ ] Separar secrets por entorno (dev/staging/prod).
- [ ] Documentar runbook de rotacion y validaciones.

**DoD**

- CI marca secretos por error.
- Runbook operativo vigente.

**Riesgos**

- Falsos positivos en scanning; ajustar reglas.

**Labels sugeridas**
`security`, `ops`, `secrets`, `high`

---

## EPICA A6 — Contrato unificado de errores API

**Objetivo**
Unificar errores para consistencia y trazabilidad.

**Alcance**
Backend (envelope) y frontend (manejo de errores).

**Tareas (issues sugeridas)**

- [ ] Definir formato `{code, message, details, request_id}`.
- [ ] Mapear errores a `reason_code` de auditoria.
- [ ] Implementar middleware o handler global.
- [ ] Ajustar frontend para leer el envelope.
- [ ] Agregar tests de contrato.

**DoD**

- 100% errores relevantes con mismo formato.
- Tests de contrato pasan.

**Riesgos**

- Requiere despliegue coordinado backend/frontend.

**Labels sugeridas**
`backend`, `frontend`, `contract`, `medium`

---

## EPICA A7 — Observabilidad minima

**Objetivo**
Detectar y diagnosticar incidentes con trazabilidad.

**Alcance**
Backend, frontend y stack de monitoreo.

**Tareas (issues sugeridas)**

- [ ] Integrar Sentry en backend.
- [ ] Integrar Sentry en frontend.
- [ ] Confirmar logs estructurados con `request_id`.
- [ ] Definir metricas minimas (latencia, 401/403, 5xx).
- [ ] Documentar acceso a dashboards y runbook basico.

**DoD**

- Errores reproducibles rastreables por `request_id`.
- Dashboard minimo operativo.

**Riesgos**

- Cuidar PII en eventos de monitoreo.

**Labels sugeridas**
`observability`, `ops`, `medium`
