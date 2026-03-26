# ADR — QA Platform Hardening A→F (2026-03-25)

## Estado
Aprobado.

## Contexto
El repositorio requiere endurecimiento de plataforma sin abrir nuevas features de negocio:

- contrato explícito de routing canónico/legacy,
- cobertura por dominios críticos con ratchet,
- gobernanza clara de checks (incluyendo AI Review advisory),
- retiro controlado de compat legacy de kernels,
- ejecución QA reproducible por perfiles,
- clasificación automática de blast radius en PR.

## Decisión
Se ejecuta en 6 fases con enforcement en CI:

1. Routing policy + route contract guard.
2. Coverage by domain guard con baseline versionado.
3. AI review en modo advisory no bloqueante.
4. Kernel compat policy con ratchet y deadline de retiro.
5. Runner QA por perfiles con manifests y trazabilidad de overrides.
6. Guard de blast radius con política adicional para cambios high/extreme.

## Consecuencias
- Menos ambigüedad operativa y de rutas legacy.
- Gates con señal real y trazabilidad por artefactos JSON.
- Menor probabilidad de regresiones arquitectónicas silenciosas.
- Revisión de PR más gobernada por riesgo técnico.
