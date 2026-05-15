# CAP-04 Tender / Settlement Spine v1

## Decisión

Persistir `payment_method` como snapshot explícito en Billing y Payments para que cierre CEC y futuros flujos contables no dependan de inferencias desde origen, provider, metadata o movimientos de caja.

## Alcance

- `BillingDocument.payment_method` guarda el tender de la venta cuando el origen lo conoce.
- `PaymentIntent.payment_method` guarda el tender del cobro cuando el flujo lo conoce.
- `CASH`, `TRANSFER`, `CREDIT` y `CARD` quedan soportados por el spine común.
- `CARD` queda disponible solo para Billing/Payments en este slice; POS/Fuel no lo aceptan todavía.
- `MIXED` queda fuera hasta tener modelo explícito.

## Compatibilidad

- Registros históricos usan `payment_method=""`.
- CEC prefiere `BillingDocument.payment_method`; si está vacío, conserva el fallback `BillingDocument.source_* -> FuelSale.payment_method`.
- No hay backfill histórico.
- No se activa accounting de `PaymentCaptured`.

## Riesgos Residuales

- Billing todavía no modela tender mixto.
- POS/Fuel todavía no tienen `CARD` como tender operativo.
- `PaymentCaptured` sigue observe-only hasta una regla non-cash posterior con reversas/refunds claras.
