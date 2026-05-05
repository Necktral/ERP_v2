# Fuel Sale External Idempotency

Version: v1  
Fecha: 2026-05-04  
Estado: implementado en rama `fix/fuel-sale-external-idempotency`

## Objetivo

Agregar idempotencia externa a la creación de ventas Fuel para que un retry de cliente
después de timeout/red móvil devuelva la misma venta sin duplicar efectos económicos.

## Problema

`POST /api/fuel/sales/` creaba `FuelSale` y luego disparaba Inventory y Billing con
keys internas derivadas de `sale.id`. Eso protegía los efectos downstream una vez
existía la venta, pero no daba una key externa estable para repetir la solicitud de
creación completa.

## Decisión

La idempotencia queda almacenada en `FuelSale.idempotency_key`, con unique constraint
condicional por `company + idempotency_key` cuando la key no está vacía.

Reglas:

- sin `idempotency_key`: comportamiento previo intacto;
- misma company + misma key + mismo payload: retorna la `FuelSale` existente;
- misma company + misma key + payload distinto: conflicto `409`;
- replay válido no reejecuta Inventory, Billing, audit ni outbox;
- la key no se scopea por branch para evitar ambigüedad cross-branch dentro de la
  misma empresa.

Campos comparados en replay:

- `branch_id`
- `shift_id`
- `dispense_id`
- `sale_type`
- `payment_method`
- `customer_name`
- `customer_ref`
- `is_fiscal`

## Alcance

Incluye:

- modelo y migración Fuel;
- serializer de creación;
- service-level idempotency;
- status API `201` nuevo, `200` replay, `409` mismatch;
- tests Fuel de replay, mismatch y compatibilidad sin key.

No incluye:

- cambios internos en Inventory o Billing;
- cambios POS/Sync/UI;
- rediseño de compensación;
- framework global de idempotencia.

## Riesgos y mitigaciones

- Carrera concurrente: la creación de `FuelSale` se envuelve en savepoint y, ante
  `IntegrityError`, se recarga la venta existente por company + key y se valida payload.
- Turno cerrado después de la primera venta: el lookup idempotente ocurre antes de
  validar estado del turno para permitir retry estable.
- Payload distinto con misma key: se rechaza explícitamente como conflicto para no
  devolver una venta ambigua.

## Validación esperada

- tests Fuel focales;
- regresiones Inventory, Retail POS y Sync POS cercanas;
- mypy/ruff;
- `makemigrations --check --dry-run`;
- full QA por incluir migración.
