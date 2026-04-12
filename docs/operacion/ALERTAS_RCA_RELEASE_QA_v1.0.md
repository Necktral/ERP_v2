# RCA de Alertas Release/QA v1.0

Versión: v1.0  
Fecha: 2026-03-26  
Estado: **Activo**

## Objetivo

Clasificar alertas por severidad para separar:

- `bloqueante`
- `warning controlado`
- `ruido esperado`

y definir acción correctiva trazable por cada caso.

## Matriz de severidad y causa raíz

| Alerta | Severidad | Clasificación | Estado | Evidencia | Causa raíz | Acción correctiva |
|---|---|---|---|---|---|---|
| Mezcla semántica FUEL/Reporting en `README.md` | MAJOR | bloqueante documental | RESUELTA EN RAMA | `README.md` (secciones API) | Inserción de bloque R8 sin reubicar bullets de fuel | Reordenar bloques y agregar guard `qa-readme-section-guard` |
| `release_evidence_u6.json` con faltantes ambiguos | MAJOR | bloqueante de trazabilidad | RESUELTA EN RAMA | `qa/reports/release_evidence_u6.json` | Desalineación entre `qa-ci` y exportador U6 | Integrar `qa-security-findings-enforce` en Gate 1 y política `CI-only` para artifacts supply-chain |
| Gate R8 en modo `WARN` | MINOR | warning controlado | VIGENTE | `qa/reports/reporting_r8_gate.json`, runbook R8 | Ventana temporal de enforcement | Mantener monitoreo; `WARN` hasta 2026-04-07 y `FAIL` desde 2026-04-08 |
| `429 Too Many Requests` en logs de carga auth | INFO | ruido esperado | VIGENTE | `qa/reports/backend_gate3_tail.log` | Activación de throttle bajo perfil de carga | Tratar como esperado salvo fallos de gate (`failure_class != none`) |
| Warning de locale en DB (`no usable system locales were found`) | INFO | ruido esperado | VIGENTE | `qa/reports/db_gate3_*_tail.log` | Imagen/entorno sin utilitario `locale` | No bloqueante por sí mismo; elevar solo si deriva en error funcional |

## Criterio operativo de salida

- Bloqueante: corregir antes de merge/release.
- Warning controlado: permitir avance con evidencia explícita y fecha de hard-fail definida.
- Ruido esperado: registrar y no escalar salvo impacto funcional medible en gates.
