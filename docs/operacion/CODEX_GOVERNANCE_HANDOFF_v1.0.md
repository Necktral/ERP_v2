# CODEX GOVERNANCE HANDOFF v1.1

Versión: v1.1  
Fecha: 2026-04-11  
Estado: **Política operativa (vigente)**

## Objetivo

Estandarizar el uso de Codex en `ERP_CRM` bajo gobernanza estricta: cambios acotados, trazables, auditables y alineados con contratos de arquitectura/QA del repositorio.

## Instrucción persistente para Codex

```text
INSTRUCCIONES PARA CODEX — ERP_CRM

ROL
Actúa como Software Engineer ejecutor bajo dirección de arquitectura. No defines producto ni arquitectura final.

OBJETIVO
Inspeccionar, proponer, implementar y validar cambios acotados, preservando auditabilidad y contratos del repositorio.

REGLAS NO NEGOCIABLES
1. Inspecciona primero (árbol, contratos y tests) antes de editar.
2. No inventes arquitectura, datos ni flujos fuera de lo soportado por el repo.
3. No mezcles bounded contexts sin declarar impacto.
4. Contabilidad es núcleo conceptual:
   - preservar hechos económicos y auditabilidad;
   - Shadow Ledger es proyección determinista, no segunda contabilidad.
5. Ownership por dominio:
   - `apps/kernels/accounting`: verdad contable y cierre.
   - `apps/kernels/facturacion`: facturación/documentos fiscales.
   - `apps/kernels/inventarios`: existencias y costo.
   - `apps/kernels/payments`: caja, cobros/pagos y conciliación.
   - `apps/kernels/reporting`: proyección/consulta, sin tomar ownership transaccional.
   - `apps/modulos/cec`: control plane (gates, evidencia, excepciones), no source-of-truth operativo.
6. Cross-domain permitido solo con contrato explícito y sin romper `qa/contracts/architecture_dependency_baseline.json`.
7. Evita complejidad innecesaria; cambios mínimos pero suficientes.
8. En zonas críticas (accounting/payments/iam/cec/migrations), no usar autonomía alta.
9. Si una decisión clave depende de supuestos no verificables, detente y declara el supuesto.

PROTOCOLO OBLIGATORIO DE HANDOFF
A) Diagnóstico del área
B) Alcance exacto
C) Contratos impactados
D) Implementación realizada
E) Pruebas / validación
F) Riesgos remanentes y siguiente paso
```

## Política por Tipo de Cambio

### `docs_only`

- Modos permitidos: `Suggest`, `Auto Edit`.
- Evidencia mínima: resumen corto de diagnóstico y alcance.
- Gates ligeros recomendados: `qa-readme-section-guard`, `qa-pr-blast-radius-guard`.

### `single_domain_code`

- Requiere handoff completo A-F.
- Gates mínimos: `qa-architecture-dependency-guard` + `qa-route-contract-guard`.
- Si toca APIs/eventos, declarar compatibilidad y pruebas afectadas.

### `cross_domain`

- Requiere handoff A-F + **blast radius explícito**.
- Debe justificar contrato/API/evento impactado y compatibilidad.
- Gates mínimos: `qa-architecture-dependency-guard`, `qa-route-contract-guard`, `qa-pr-blast-radius-guard`.

### `migrations_or_close_cycle`

- Modo restringido: no `Full Auto`; `Auto Edit` solo para cambios mecánicos revisables.
- Requiere handoff A-F + **plan de rollback** + **estado de gates**.
- Gates mínimos: `qa-makemigrations-check`, `qa-migration-safety-guard`, `qa-architecture-dependency-guard`.

### `security_or_supply_chain`

- Modo restringido: no `Full Auto`.
- Requiere handoff A-F + **estado de excepciones de seguridad** + **estado de gates**.
- Gates mínimos: `qa-validate-security-exceptions`, `qa-security-findings-enforce`.

## Plantilla de tarea por sesión

```text
TAREA PARA CODEX

OBJETIVO
[resultado esperado]

CONTEXTO FUNCIONAL
[kernel/modulo/flujo]

TIPO DE CAMBIO
[docs_only | single_domain_code | cross_domain | migrations_or_close_cycle | security_or_supply_chain]

ALCANCE
[incluir]
[excluir]

ARCHIVOS O ZONAS SOSPECHOSAS
[rutas]
[endpoints]
[tests]

RESTRICCIONES
- no tocar dominios fuera de alcance sin justificar;
- no romper contratos/API/eventos existentes;
- no alterar comportamiento contable/fiscal sin declarar impacto;
- no agregar dependencias sin necesidad real.

SALIDA ESPERADA
1. Diagnóstico del área
2. Alcance exacto
3. Contratos impactados
4. Implementación realizada
5. Pruebas / validación
6. Riesgos remanentes

VALIDACIÓN MÍNIMA
- `make qa-codex-governance-guard`
- `make qa-architecture-dependency-guard`
- `make qa-route-contract-guard`
- `make qa-reporting-contract-version-guard`
- `make qa-migration-safety-guard`
```

## Criterio de cumplimiento

Un cambio se considera conforme solo si:

1. La clasificación por tipo de cambio es consistente con el diff.
2. La evidencia de handoff cubre las secciones obligatorias del tipo.
3. No hay violación de modo prohibido para el tipo.
4. Los gates requeridos por tipo aparecen con evidencia en `qa/reports`.
5. No se rompe baseline contractual de arquitectura.
