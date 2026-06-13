"""E2E vivo Ola G (verticales): tanques (recepción→despacho→ajuste), costos de flota
(combustible+mantenimiento+gasto→resumen) y presupuesto de finca (líneas→vs-real→SoD).
Corre contra el backend REAL (localhost:8000). Token por env E2E_TOKEN_WIS.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE = "http://localhost:8000/api"
TOKEN = os.environ["E2E_TOKEN_WIS"]

OK = 0
FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    print(f"  {'✓' if cond else '✗'} {name}{(' — ' + extra) if extra else ''}")
    OK, FAIL = (OK + 1, FAIL) if cond else (OK, FAIL + 1)


def req(method, path, body=None):
    r = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )
    r.add_header("Authorization", f"Bearer {TOKEN}")
    r.add_header("Content-Type", "application/json")
    r.add_header("X-Company-Id", "2")
    r.add_header("X-Branch-Id", "3")
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def f(v):
    return float(v)


tag = uuid.uuid4().hex[:5].upper()

print("== Tanques de estación ==")
st, tanks = req("GET", "/fuel/tanks/")
diesel = next((t for t in tanks.get("results", []) if t["product"] == "DIESEL" and t["is_active"]), None)
if diesel is None:
    st, diesel = req("POST", "/fuel/tanks/", {"code": f"TD{tag}", "product": "DIESEL", "capacity_l": "20000"})
    check("tanque diésel creado", st == 201, f"id {diesel.get('id')}")
else:
    check("tanque diésel disponible", True, f"id {diesel['id']}")
tank_id = diesel["id"]

st, t = req("GET", f"/fuel/tanks/{tank_id}/")
nivel0 = f(t["current_volume_l"])
st, _ = req("POST", f"/fuel/tanks/{tank_id}/receive/", {"liters": "500", "supplier_name": "Pipa E2E"})
st, t = req("GET", f"/fuel/tanks/{tank_id}/")
check("recepción sube el nivel +500", abs((f(t["current_volume_l"]) - nivel0) - 500) < 0.01, f"nivel {t['current_volume_l']}")
nivel1 = f(t["current_volume_l"])

# Turno abierto (o abrir uno).
st, shifts = req("GET", "/fuel/shifts/")
shift = next((s for s in shifts.get("results", []) if s.get("status") == "OPEN"), None)
if shift is None:
    st, shift = req("POST", "/fuel/shifts/open/", {})
st, disp = req("POST", "/fuel/dispenses/", {
    "shift_id": shift["id"], "product": "DIESEL",
    "volume": "20", "volume_uom": "LITER",
    "unit_price": "45", "unit_price_uom": "PER_LITER",
})
check("despacho registrado", st == 201, f"id {disp.get('id')}")
st, t = req("GET", f"/fuel/tanks/{tank_id}/")
check("el despacho descuenta 20 L del tanque", abs((nivel1 - f(t["current_volume_l"])) - 20) < 0.01, f"nivel {t['current_volume_l']}")
nivel2 = f(t["current_volume_l"])

st, _ = req("POST", f"/fuel/tanks/{tank_id}/adjust/", {"liters": "-5", "reason": "Merma E2E"})
st, t = req("GET", f"/fuel/tanks/{tank_id}/")
check("ajuste -5 baja el nivel", abs((nivel2 - f(t["current_volume_l"])) - 5) < 0.01, f"nivel {t['current_volume_l']}")

print("== Costos de flota ==")
st, assets = req("GET", "/fleet/assets/")
alist = assets if isinstance(assets, list) else assets.get("results", [])
if alist:
    asset_id = alist[0]["id"]
    check("activo de flota disponible", True, f"id {asset_id}")
else:
    st, a = req("POST", "/fleet/assets/", {"code": f"AV{tag}", "name": "Camión E2E", "asset_type": "VEHICLE"})
    asset_id = a.get("id")
    check("activo de flota creado", st in (200, 201), f"id {asset_id}")

st, s0 = req("GET", f"/fleet/assets/{asset_id}/cost-summary/")
grand0 = f(s0["grand_total"])
req("POST", f"/fleet/assets/{asset_id}/fuel-logs/", {"liters": "40", "unit_cost": "1.5"})  # 60
req("POST", f"/fleet/assets/{asset_id}/maintenance-orders/", {"description": "Frenos E2E", "labor_cost": "200", "parts_cost": "300"})  # 500
req("POST", f"/fleet/assets/{asset_id}/expenses/", {"category": "TIRES", "amount": "800"})  # 800
st, s1 = req("GET", f"/fleet/assets/{asset_id}/cost-summary/")
check("el resumen suma combustible+mantenimiento+gasto (+1360)",
      abs((f(s1["grand_total"]) - grand0) - 1360) < 0.01,
      f"grand {s0['grand_total']} → {s1['grand_total']}")

print("== Presupuesto de finca ==")
season = f"E2E{tag}"
st, plot = req("POST", "/finca/plots/", {"finca_id": 3, "code": f"L{tag}", "area_manzanas": "10"})
check("lote creado en la finca", st == 201, f"id {plot.get('id')}")
plot_id = plot.get("id")
st, labor = req("POST", "/finca/labors/", {"code": f"lab{tag}", "name": "Chapia E2E", "category": "MANTENIMIENTO", "unit": "JORNAL", "default_rate": "150"})
check("labor creada con tarifa", st == 201, f"id {labor.get('id')}")
labor_id = labor.get("id")

st, wo = req("POST", "/finca/work-orders/", {"plot_id": plot_id, "labor_id": labor_id, "season_label": season, "jornales": "10", "status": "DONE"})
wo_id = wo.get("id")
req("POST", f"/finca/work-orders/{wo_id}/insumos/", {"item_name": "Fertilizante", "quantity": "5", "unit_cost": "20"})

st, bud = req("POST", "/finca/budgets/", {"finca_id": 3, "season_label": season, "name": f"Ppto {tag}"})
check("presupuesto creado", st == 201, f"id {bud.get('id')}")
bud_id = bud.get("id")
st, lines = req("PUT", f"/finca/budgets/{bud_id}/lines/", {"lines": [
    {"labor_id": labor_id, "plot_id": plot_id, "planned_jornales": "10", "planned_rate": "150", "planned_insumos_amount": "200"},
]})
check("líneas del presupuesto guardadas", st == 200 and len(lines.get("lines", [])) == 1)

st, vs = req("GET", f"/finca/budgets/{bud_id}/vs-actual/")
row = vs.get("rows", [{}])[0] if vs.get("rows") else {}
check("vs-real: jornales 10×150=1500 + insumos 5×20=100 = 1600",
      row.get("actual_labor") == "1500.00" and row.get("actual_insumos") == "100.00" and row.get("actual_total") == "1600.00",
      f"real {row.get('actual_total')}")
check("vs-real: presupuesto 1700, variación 100",
      row.get("planned_total") == "1700.00" and row.get("variance") == "100.00")

st, self_appr = req("POST", f"/finca/budgets/{bud_id}/approve/", {})
check("auto-aprobación rechazada (SoD)", st == 409 and self_appr.get("code") == "SOD_SELF_APPROVAL")

print(f"\nRESULTADO: {OK} OK, {FAIL} FALLAS")
sys.exit(1 if FAIL else 0)
