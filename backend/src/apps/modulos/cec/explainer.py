"""Paquete contador del CEC — explicación determinista y SOLO LECTURA de un cierre.

Traduce el resultado técnico de un `CloseRun` (gates, excepciones, score, hashes) a
lenguaje de contador, en español, sin IA: catálogos congelados por gate/código de
excepción/estado + una narrativa armada por plantilla. Reglas duras:
- Solo lectura: jamás escribe en CloseRun/CECException ni publica eventos.
- La verdad es el run: el paquete solo re-expresa lo que ya está en summary_json
  y en las excepciones; no recalcula gates ni inventa cifras.
- Cobertura total: los tests centinela exigen que cada gate y cada código de
  excepción que `services.py` puede emitir tenga explicación de catálogo.
La síntesis LLM opcional (asesora, tras el kill switch) vive en `ai_explainer.py`.
"""
from __future__ import annotations

from typing import Any

from .models import CECException, CloseRun
from .services import OPEN_EXCEPTION_STATUSES, SCORE_WEIGHTS

SCHEMA_VERSION = 1

_SEVERITY_LABELS: dict[str, str] = {
    CECException.Severity.LOW: "Baja",
    CECException.Severity.MEDIUM: "Media",
    CECException.Severity.HIGH: "Alta",
    CECException.Severity.CRITICAL: "Crítica",
}

_STATUS_EXPLANATIONS: dict[str, str] = {
    CloseRun.Status.CREATED: "Creado — el cierre existe pero todavía no se ejecuta.",
    CloseRun.Status.GATHERED: "Recolectado — se reunieron los datos de la ventana; falta validarlos.",
    CloseRun.Status.VALIDATED: "Validado — los controles corrieron; falta empaquetar el resultado.",
    CloseRun.Status.PACKAGED: "Empaquetado — pasó los controles bloqueantes y está listo para entregar.",
    CloseRun.Status.DELIVERED: "Entregado — cualquier corrección posterior requiere reabrirlo por excepción.",
    CloseRun.Status.REOPENED_EXCEPTION: (
        "Reabierto por excepción — hay excepciones bloqueantes; no puede entregarse hasta resolverlas."
    ),
}

# Catálogo por gate (los `name` que emite services.execute_close_run).
_GATE_EXPLANATIONS: dict[str, dict[str, str]] = {
    "billing_doc_integrity": {
        "titulo": "Numeración de facturas",
        "que_verifica": (
            "Que la numeración de los documentos de facturación emitidos en la ventana sea "
            "continua y sin duplicados, por tipo de documento y serie."
        ),
        "si_falla": (
            "Hay huecos o números repetidos en la facturación: puede ser una anulación sin "
            "registrar, un documento perdido o una doble emisión. Revisar la serie señalada "
            "documento por documento antes de entregar el cierre."
        ),
    },
    "cash_session_discipline": {
        "titulo": "Arqueo de cajas",
        "que_verifica": (
            "Que cada sesión de caja cerrada en la ventana cuadre: lo contado debe coincidir "
            "con lo esperado (tolerancia de 0.01)."
        ),
        "si_falla": (
            "Una o más cajas cerraron con diferencia entre lo contado y lo esperado (faltante "
            "o sobrante de efectivo). Revisar el arqueo de la sesión señalada y documentar la causa."
        ),
    },
    "billing_vs_cash_reconciliation": {
        "titulo": "Facturación contra efectivo",
        "que_verifica": (
            "Que el total facturado al contado coincida con el efectivo que entró a cajas en la "
            "misma ventana, descontando ventas con tarjeta, transferencia y crédito."
        ),
        "si_falla": (
            "Lo facturado en efectivo no coincide con lo que entró a cajas. Puede ser una venta "
            "sin facturar, una factura sin cobro registrado o un movimiento de caja mal clasificado. "
            "Conciliar facturas al contado contra movimientos de caja de la ventana."
        ),
    },
    "inventory_negative_stock": {
        "titulo": "Existencias negativas",
        "que_verifica": "Que ningún producto tenga existencia negativa en bodega.",
        "si_falla": (
            "Hay productos con existencia negativa: se registraron salidas por más de lo que había. "
            "Corregir el inventario antes del cierre; una existencia negativa distorsiona el costo "
            "y el resultado."
        ),
    },
    "procurement_doc_integrity": {
        "titulo": "Numeración de compras",
        "que_verifica": (
            "Que la numeración de los documentos de compra contabilizados en la ventana sea "
            "continua y sin duplicados, por tipo y serie."
        ),
        "si_falla": (
            "Hay huecos o números repetidos en los documentos de compra. Revisar la serie señalada "
            "contra los documentos físicos del proveedor."
        ),
    },
    "procurement_stock_cost_integrity": {
        "titulo": "Costo de compras",
        "que_verifica": (
            "Que todo documento de compra que mueve inventario (recepción o factura de proveedor) "
            "tenga un total positivo."
        ),
        "si_falla": (
            "Hay recepciones o facturas de proveedor con total cero o negativo: el inventario "
            "quedaría valorado mal. Corregir el documento señalado antes de cerrar."
        ),
    },
    "procurement_supplier_payment_reconciliation": {
        "titulo": "Cuentas por pagar a proveedores",
        "que_verifica": (
            "Que lo facturado por proveedores menos las notas de crédito coincida con los pagos "
            "a proveedores registrados en la ventana."
        ),
        "si_falla": (
            "Los pagos a proveedores no cuadran contra lo facturado menos notas de crédito. "
            "Puede ser un pago sin registrar, una factura duplicada o una nota de crédito pendiente. "
            "Conciliar el auxiliar de proveedores de la ventana."
        ),
    },
    "fiscal_b_print_failed": {
        "titulo": "Impresión fiscal fallida",
        "que_verifica": (
            "Que ningún documento emitido en modo fiscal B haya quedado con la impresión fiscal fallida."
        ),
        "si_falla": (
            "Hay documentos fiscales que no lograron imprimirse. Reimprimir o anular según el "
            "procedimiento fiscal; un documento emitido sin respaldo impreso es un riesgo ante la DGI."
        ),
    },
    "fiscal_b_contingency_open": {
        "titulo": "Contingencia fiscal abierta",
        "que_verifica": "Que ningún documento fiscal de la ventana siga en modo contingencia.",
        "si_falla": (
            "Hay documentos emitidos en contingencia que no se han regularizado. Completar el "
            "proceso de contingencia antes de entregar el cierre."
        ),
    },
    "fiscal_b_reserved_stale": {
        "titulo": "Números fiscales reservados sin emitir",
        "que_verifica": (
            "Que no queden números fiscales reservados sin emisión definitiva al final de la ventana."
        ),
        "si_falla": (
            "Hay números fiscales reservados que nunca se emitieron: dejan huecos en la numeración "
            "fiscal. Emitir o liberar cada número señalado."
        ),
    },
}

# Catálogo por código de excepción (los `code` que services.py puede registrar).
_EXCEPTION_EXPLANATIONS: dict[str, dict[str, str]] = {
    "DOC_NUMBER_GAP": {
        "titulo": "Hueco o duplicado en numeración de facturas",
        "significado": (
            "En la serie de facturación señalada faltan números o hay números repetidos dentro "
            "de la ventana del cierre."
        ),
        "revisar": (
            "Ubicar físicamente cada número faltante o repetido: anulaciones sin registrar, "
            "documentos perdidos o doble emisión. El detalle adjunto lista los números."
        ),
    },
    "CASH_DIFFERENCE_NONZERO": {
        "titulo": "Caja cerró con diferencia",
        "significado": (
            "La sesión de caja señalada cerró con diferencia entre lo contado y lo esperado "
            "(faltante o sobrante de efectivo). Esta excepción siempre bloquea la entrega."
        ),
        "revisar": (
            "El arqueo de esa sesión: monto esperado, monto contado y diferencia vienen en el "
            "detalle. Documentar la causa y registrar el ajuste que corresponda."
        ),
    },
    "BILLING_CASH_MISMATCH": {
        "titulo": "Facturación al contado no cuadra con caja",
        "significado": (
            "El total facturado en efectivo en la ventana no coincide con el efectivo que entró "
            "a cajas (ya descontadas las ventas con tarjeta, transferencia y crédito)."
        ),
        "revisar": (
            "Conciliar las facturas al contado contra los movimientos de caja de la ventana; el "
            "detalle trae los totales por medio de pago y la diferencia exacta."
        ),
    },
    "NEGATIVE_STOCK": {
        "titulo": "Existencia negativa en bodega",
        "significado": (
            "El producto señalado tiene existencia negativa: salió más de lo que había registrado. "
            "Esta excepción siempre bloquea la entrega porque distorsiona costo y resultado."
        ),
        "revisar": (
            "Los movimientos de inventario del producto y bodega señalados: entradas sin registrar, "
            "salidas duplicadas o conteo físico pendiente."
        ),
    },
    "PROCUREMENT_DOC_NUMBER_GAP": {
        "titulo": "Hueco o duplicado en numeración de compras",
        "significado": (
            "En la serie de documentos de compra señalada faltan números o hay repetidos dentro "
            "de la ventana."
        ),
        "revisar": "Cotejar la serie contra los documentos físicos del proveedor; el detalle lista los números.",
    },
    "PROCUREMENT_STOCK_COST_INTEGRITY": {
        "titulo": "Compra de inventario con costo no positivo",
        "significado": (
            "Un documento de compra que mueve inventario tiene total cero o negativo; valoraría mal "
            "el inventario. Esta excepción siempre bloquea la entrega."
        ),
        "revisar": "El documento de compra señalado: precio, cantidades y captura del total.",
    },
    "PROCUREMENT_SUPPLIER_PAYMENT_MISMATCH": {
        "titulo": "Pagos a proveedores no cuadran",
        "significado": (
            "Lo facturado por proveedores menos notas de crédito no coincide con los pagos "
            "registrados en la ventana."
        ),
        "revisar": (
            "El auxiliar de proveedores: el detalle trae facturado, notas de crédito, pagos y la "
            "diferencia exacta."
        ),
    },
    "FISCAL_B_PRINT_FAILED": {
        "titulo": "Documento fiscal sin imprimir",
        "significado": (
            "Un documento emitido en modo fiscal B quedó con la impresión fiscal fallida. Siempre "
            "bloquea la entrega."
        ),
        "revisar": "Reimprimir o anular según el procedimiento fiscal; el detalle trae serie, número y el error.",
    },
    "FISCAL_B_CONTINGENCY_OPEN": {
        "titulo": "Contingencia fiscal sin regularizar",
        "significado": (
            "Un documento fiscal de la ventana sigue en modo contingencia. Siempre bloquea la entrega."
        ),
        "revisar": "Completar la regularización de la contingencia; el detalle trae la razón y la fecha.",
    },
    "FISCAL_B_RESERVED_STALE": {
        "titulo": "Número fiscal reservado sin emitir",
        "significado": (
            "Un número fiscal quedó reservado sin emisión definitiva al final de la ventana; deja "
            "un hueco en la numeración fiscal."
        ),
        "revisar": "Emitir o liberar el número señalado; el detalle trae los minutos que lleva reservado.",
    },
}


def _verdict(*, run: CloseRun, blocking_open_count: int, open_count: int) -> dict[str, str]:
    if run.status == CloseRun.Status.CREATED:
        return {
            "code": "SIN_EJECUTAR",
            "text": "El cierre todavía no se ejecuta: no hay controles ni excepciones que explicar.",
        }
    if run.status == CloseRun.Status.REOPENED_EXCEPTION or blocking_open_count > 0:
        plural = "excepción bloqueante impide" if blocking_open_count == 1 else "excepciones bloqueantes impiden"
        return {
            "code": "BLOQUEADO",
            "text": (
                f"El cierre está bloqueado: {blocking_open_count} {plural} la entrega. "
                "Resolverlas y volver a ejecutar el cierre."
            ),
        }
    if run.status == CloseRun.Status.DELIVERED:
        return {"code": "ENTREGADO", "text": "El cierre ya fue entregado."}
    if run.status == CloseRun.Status.PACKAGED:
        text = "El cierre pasó los controles bloqueantes y está listo para entregar."
        if open_count:
            text += f" Quedan {open_count} observación(es) abiertas que no bloquean."
        return {"code": "LISTO_PARA_ENTREGA", "text": text}
    return {
        "code": "EN_PROCESO",
        "text": f"El cierre está en proceso ({_STATUS_EXPLANATIONS.get(run.status, run.status)}).",
    }


def _score_rules_text() -> str:
    crit = SCORE_WEIGHTS.get(CECException.Severity.CRITICAL, 0)
    high = SCORE_WEIGHTS.get(CECException.Severity.HIGH, 0)
    med = SCORE_WEIGHTS.get(CECException.Severity.MEDIUM, 0)
    return (
        f"El puntaje arranca en 100 y descuenta {crit} puntos por cada excepción crítica abierta, "
        f"{high} por cada alta y {med} por cada media."
    )


def _explain_gate(gate: dict[str, Any]) -> dict[str, Any]:
    name = str(gate.get("name", ""))
    info = _GATE_EXPLANATIONS.get(name) or {
        "titulo": f"Control {name}",
        "que_verifica": "Control sin explicación de catálogo; revisar con el equipo técnico.",
        "si_falla": "El control falló; revisar el detalle técnico adjunto.",
    }
    metric = dict(gate.get("metric") or {})
    applies = bool(metric.get("enabled", True))
    passed = bool(gate.get("passed"))
    if not applies:
        result_text = "No aplica en esta ventana (sin actividad de este tipo)."
    elif passed:
        result_text = "Pasó."
    else:
        result_text = info["si_falla"]
    return {
        "name": name,
        "passed": passed,
        "applies": applies,
        "title": info["titulo"],
        "checks": info["que_verifica"],
        "result_text": result_text,
        "metric": metric,
    }


def _explain_exception(ex: CECException) -> dict[str, Any]:
    info = _EXCEPTION_EXPLANATIONS.get(ex.code) or {
        "titulo": f"Excepción {ex.code}",
        "significado": (
            f"Excepción registrada por el módulo {ex.source_module}; no tiene explicación de catálogo."
        ),
        "revisar": "El detalle adjunto, junto con el responsable del módulo de origen.",
    }
    return {
        "exception_id": str(ex.exception_id),
        "code": ex.code,
        "severity": ex.severity,
        "severity_label": _SEVERITY_LABELS.get(ex.severity, ex.severity),
        "status": ex.status,
        "is_blocking": bool(ex.is_blocking),
        "title": info["titulo"],
        "meaning": info["significado"],
        "what_to_check": info["revisar"],
        "related_object_type": ex.related_object_type,
        "related_object_id": ex.related_object_id,
        "details": ex.details_json or {},
        "opened_at": ex.opened_at.isoformat() if ex.opened_at else "",
        "resolved_at": ex.resolved_at.isoformat() if ex.resolved_at else "",
        "resolution_note": ex.resolution_note or "",
    }


def _narrative(
    *,
    run: CloseRun,
    gates: list[dict[str, Any]],
    open_exceptions: list[dict[str, Any]],
    blocking_open: list[dict[str, Any]],
    verdict: dict[str, str],
) -> str:
    scope = run.company.name
    if run.branch is not None:
        scope += f" / {run.branch.name}"
    run_label = "diario" if run.run_type == CloseRun.RunType.DAILY else "periódico"

    lines: list[str] = []
    if run.window_start and run.window_end:
        lines.append(
            f"Cierre {run_label} de {scope}, ventana del {run.window_start.isoformat()} "
            f"al {run.window_end.isoformat()}."
        )
    else:
        lines.append(f"Cierre {run_label} de {scope}, aún sin ventana ejecutada.")
    lines.append(f"Estado: {_STATUS_EXPLANATIONS.get(run.status, run.status)}")

    if gates:
        applicable = [g for g in gates if g["applies"]]
        failed = [g for g in applicable if not g["passed"]]
        na_count = len(gates) - len(applicable)
        gates_line = f"Controles: {len(applicable) - len(failed)} de {len(applicable)} pasaron"
        if na_count:
            gates_line += f" ({na_count} no aplican en esta ventana)"
        gates_line += "."
        if failed:
            gates_line += " Fallaron: " + "; ".join(g["title"] for g in failed) + "."
        lines.append(gates_line)
        lines.append(f"Puntaje de consistencia: {run.consistency_score}/100. {_score_rules_text()}")

    if blocking_open:
        lines.append("Bloquean la entrega:")
        for ex in blocking_open:
            lines.append(f"- {ex['title']} ({ex['severity_label']}). Revisar: {ex['what_to_check']}")
    non_blocking = [ex for ex in open_exceptions if not ex["is_blocking"]]
    if non_blocking:
        lines.append("Observaciones abiertas que no bloquean:")
        for ex in non_blocking:
            lines.append(f"- {ex['title']} ({ex['severity_label']}).")

    lines.append(f"Veredicto: {verdict['text']}")
    if run.output_manifest_hash:
        lines.append(
            f"Integridad: huella sha256 {run.output_manifest_hash} — el resumen del cierre no puede "
            "alterarse sin que cambie esta huella."
        )
    return "\n".join(lines)


def build_accountant_package(run: CloseRun) -> dict[str, Any]:
    """Paquete contador determinista del cierre. Solo lee; jamás escribe."""
    summary = run.summary_json or {}
    gates = [_explain_gate(g) for g in summary.get("gates", []) if isinstance(g, dict)]
    exceptions = [
        _explain_exception(ex)
        for ex in run.exceptions.order_by("-is_blocking", "-opened_at", "-id")
    ]
    open_statuses = set(OPEN_EXCEPTION_STATUSES)
    open_exceptions = [ex for ex in exceptions if ex["status"] in open_statuses]
    blocking_open = [ex for ex in open_exceptions if ex["is_blocking"]]
    verdict = _verdict(run=run, blocking_open_count=len(blocking_open), open_count=len(open_exceptions))

    package: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(run.run_id),
        "run_type": run.run_type,
        "status": run.status,
        "status_explained": _STATUS_EXPLANATIONS.get(run.status, run.status),
        "window_start": run.window_start.isoformat() if run.window_start else "",
        "window_end": run.window_end.isoformat() if run.window_end else "",
        "completed_at": run.completed_at.isoformat() if run.completed_at else "",
        "consistency_score": int(run.consistency_score),
        "score_rules": _score_rules_text(),
        "verdict": verdict,
        "gates": gates,
        "gates_failed_count": sum(1 for g in gates if g["applies"] and not g["passed"]),
        "exceptions": exceptions,
        "open_exceptions_count": len(open_exceptions),
        "blocking_open_count": len(blocking_open),
        "output_manifest_hash": run.output_manifest_hash,
    }
    package["narrative"] = _narrative(
        run=run,
        gates=gates,
        open_exceptions=open_exceptions,
        blocking_open=blocking_open,
        verdict=verdict,
    )
    return package
