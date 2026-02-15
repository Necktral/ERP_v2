# Rotación de secretos — Runbook operativo

Versión: v1.0  
Fecha: 2026-02-02  
Estado: **Procedimiento operativo (vivo)**

## Propósito

Ejecutar rotación de secretos sin downtime y con posibilidad de rollback, manteniendo trazabilidad.

## Alcance

- `AUDIT_HMAC_KEY`
- Secretos de sync (por dispositivo)

## Procedimiento (dual key)

1. **Generar nueva clave**
   - Registrar ticket y responsable.
   - Generar clave fuerte (mínimo 32 bytes aleatorios).

2. **Activar modo dual**
   - Configurar `KEY_CURRENT` (nueva) y `KEY_PREVIOUS` (vieja).
   - Desplegar a producción.

3. **Observar**
   - Revisar métricas/errores de firma y auditoría.
   - Validar que no haya incremento de 401/403/5xx.

4. **Promover clave**
   - Pasada la ventana de rotación, mover `KEY_CURRENT` a nueva.
   - Retirar `KEY_PREVIOUS`.

5. **Auditar**
   - Registrar fecha/hora, responsable y motivo.
   - Guardar evidencia (logs y métricas).

## Rollback

Si aparecen fallos, restaurar `KEY_CURRENT` a la clave previa y repetir verificación.

## Checklist

- [ ] Ticket abierto y aprobado
- [ ] Clave generada y almacenada en vault
- [ ] Modo dual activo
- [ ] Observación sin errores críticos
- [ ] Promoción y retiro de clave previa
- [ ] Evidencia archivada
