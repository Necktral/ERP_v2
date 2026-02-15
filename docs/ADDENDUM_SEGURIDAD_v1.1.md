# Addendum Seguridad v1.1 — Resolución de Vulnerabilidades de Autenticación

Version: v1.1
Fecha: 2026-02-09
Estado: **Implementado / Verificado**
Referencias: [Addendum v1.0](ADDENDUM_SEGURIDAD_v1.0.md)

## Propósito

Este documento detalla la corrección de dos vulnerabilidades críticas identificadas en el flujo de autenticación durante las pruebas de carga y auditoría de seguridad del 09/02/2026.

## Vulnerabilidades Corregidas

### 1. Ataque de Reproducción (Replay Attack) en 2FA

- **Identificación**: La simulación de carga (`auth_load_simulation_extended.js`) demostró que, bajo condiciones de alta concurrencia, el mismo código TOTP/Challenge podía ser consumido múltiples veces antes de que el servidor invalidara el registro `TwoFactorChallenge`.
- **Causa Raíz**: Condiciones de carrera (Race Condition) entre la lectura del estado del challenge y su actualización (`used_at`).
- **Solución Implementada**:
  - Se introdujo un bloqueo pesimista a nivel de base de datos (`select_for_update`) dentro de una transacción atómica para serializar el consumo.
  - Se cambió la estrategia de invalidación: en lugar de actualizar una marca de tiempo, el challenge ahora se **elimina físicamente** (`.delete()`) tras su validación exitosa. Esto elimina matemáticamente la posibilidad de reutilización.
- **Verificación**: Validación mediante escenario `adminTwoFaFlow` en k6 con usuarios concurrentes intentando canjear el mismo token.

### 2. Persistencia de Sesión en Logout fallido (Cookie Zombies)

- **Identificación**: Al solicitar `/api/auth/logout/` con un token de refresco inválido o expirado, el backend respondía con un error 401 pero **no ordenaba al navegador borrar las cookies de sesión**.
- **Impacto**: El usuario percibía un error en la interfaz, pero sus cookies de autenticación (HttpOnly) permanecían válidas en el navegador, manteniendo la sesión "viva" técnicamente.
- **Solución Implementada**:
  - Se modificó `LogoutView` y `RefreshView` para emitir los headers `Set-Cookie: ...; Max-Age=0` de forma **incondicional** antes de cualquier validación de lógica de negocio (token).
  - Un logout fallido ahora garantiza un estado "limpio" en el cliente (Idempotencia).

## Estado Actual

El sistema ha pasado las pruebas de regresión de seguridad (`simulacion/run_simulation.sh`) confirmando la mitigación efectiva de ambos vectores.
