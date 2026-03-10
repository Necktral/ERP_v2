# Matriz de Ownership y SLA (Fase 6, 7A, 7B)

Version: v1.0  
Fecha: 2026-03-08  
Estado: Activo

## Objetivo

Definir responsables y tiempos de atencion para alarmas criticas del bloque contable/fiscal backend.

## Ownership por dominio

- Adapter B / Billing fiscal:
  - Owner funcional: Operacion de facturacion.
  - Owner tecnico: Backend Facturacion.
- GL Core / FX:
  - Owner funcional: Contabilidad.
  - Owner tecnico: Backend Accounting.
- Intercompany / Consolidacion:
  - Owner funcional: Finanzas corporativas.
  - Owner tecnico: Backend Accounting.
- Backbone eventos (outbox/inbox):
  - Owner tecnico: Plataforma.
- CEC exceptions bloqueantes:
  - Owner funcional: Operacion + Contabilidad.
  - Owner tecnico: Backend CEC.

## SLA por tipo de incidente

- `FiscalPrintJob=FAILED`:
  - Triage: < 30 min.
  - Mitigacion: < 1 h.
- `FiscalStatus=CONTINGENCY` abierto:
  - Triage: < 30 min.
  - Mitigacion: < 4 h.
- `CloseRunBlocked` por CEC/Accounting:
  - Triage: < 30 min.
  - Mitigacion: < 4 h.
- `missing_lines > 0` en GL:
  - Triage: < 30 min.
  - Correccion: < 2 h.
- `stale_revaluation > 0` al cierre mensual:
  - Triage: < 1 h.
  - Correccion: mismo dia habil.
- `open_intercompany > 0` fuera de ventana:
  - Triage: < 1 h.
  - Resolucion: < 1 dia habil.
- `disputed_intercompany > 0` fuera de ventana:
  - Triage: < 1 h.
  - Resolucion: < 2 dias habiles.
- `inbox_failed > 0` o `outbox_failed > 0`:
  - Triage: < 15 min.
  - Resolucion: < 1 h.

## Escalamiento

- Nivel 1: owner tecnico del dominio.
- Nivel 2: owner funcional + lider tecnico.
- Nivel 3: direccion de tecnologia + direccion financiera (si bloquea cierre).

## Regla de gobernanza

- Cambios en `PostingRuleSet` solo por versionado formal.
- No ediciones manuales ad-hoc en caliente sobre datos posteados.
- Toda mitigacion debe dejar evidencia JSON firmada y referencia a incidente.

