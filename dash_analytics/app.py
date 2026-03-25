from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Any

import requests
from dash import Dash, Input, Output, dcc, html, dash_table
import plotly.graph_objects as go
from flask import Flask, jsonify, redirect, request, session


DASH_BACKEND_BASE_URL = os.getenv("DASH_BACKEND_BASE_URL", "http://backend:8000/api").rstrip("/")
DASH_URL_PREFIX = os.getenv("DASH_URL_PREFIX", "/analytics").rstrip("/")
DASH_REQUEST_TIMEOUT_SEC = float(os.getenv("DASH_REQUEST_TIMEOUT_SEC", "12"))
DASH_SESSION_SECRET = os.getenv("DASH_SESSION_SECRET", "dash-dev-secret-change-me")
DASH_INTERNAL_PORT = int(os.getenv("DASH_INTERNAL_PORT") or os.getenv("DASH_PORT", "8050"))

WORKSPACES = {
    "executive": {
        "label": "Executive",
        "datasets": [
            "accounting.pnl.period",
            "accounting.balance_sheet.as_of",
        ],
    },
    "operations": {
        "label": "Operations",
        "datasets": [
            "fuel.sales.by_pump.daily",
            "fuel.dispense_vs_sale.daily",
            "accounting.operational_reconciliation.period",
        ],
    },
}


def _normalize_num(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(str(value))
    except Exception:
        return 0.0


def _run_dataset(dataset_key: str, filters: dict[str, Any], consumer_ref: str) -> dict[str, Any]:
    token = session.get("reporting_access_token")
    if not token:
        raise RuntimeError("No hay sesión reporting activa.")
    url = f"{DASH_BACKEND_BASE_URL}/reporting/datasets/{dataset_key}/run/"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = requests.post(
        url,
        json={"filters": filters, "consumer_ref": consumer_ref},
        headers=headers,
        timeout=DASH_REQUEST_TIMEOUT_SEC,
    )
    if response.status_code != 200:
        raise RuntimeError(f"{dataset_key} failed ({response.status_code}): {response.text[:300]}")
    return response.json()


def _figure_empty(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        title=title,
        template="plotly_white",
        margin=dict(l=20, r=20, t=60, b=40),
        height=360,
    )
    return fig


def _to_filters(start_date: str | None, end_date: str | None) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if start_date:
        filters["date_from"] = start_date
    if end_date:
        filters["date_to"] = end_date
    return filters


def _build_executive_payload(start_date: str | None, end_date: str | None) -> dict[str, Any]:
    filters = _to_filters(start_date, end_date)
    pnl = _run_dataset("accounting.pnl.period", filters=filters, consumer_ref="dash:executive:pnl")
    bs_filters = dict(filters)
    if end_date:
        bs_filters["as_of"] = end_date
    balance_sheet = _run_dataset(
        "accounting.balance_sheet.as_of",
        filters=bs_filters,
        consumer_ref="dash:executive:balance_sheet",
    )
    return {"pnl": pnl, "balance_sheet": balance_sheet}


def _build_operations_payload(start_date: str | None, end_date: str | None) -> dict[str, Any]:
    filters = _to_filters(start_date, end_date)
    by_pump = _run_dataset("fuel.sales.by_pump.daily", filters=filters, consumer_ref="dash:ops:by_pump")
    by_day = _run_dataset("fuel.dispense_vs_sale.daily", filters=filters, consumer_ref="dash:ops:by_day")
    reconciliation = _run_dataset(
        "accounting.operational_reconciliation.period",
        filters=filters,
        consumer_ref="dash:ops:reconciliation",
    )
    return {"by_pump": by_pump, "by_day": by_day, "reconciliation": reconciliation}


def _figure_executive_main(payload: dict[str, Any]) -> go.Figure:
    rows = payload["pnl"].get("rows") or []
    x = [str(r.get("account_code") or "N/A") for r in rows]
    y = [_normalize_num(r.get("balance")) for r in rows]
    fig = go.Figure(data=[go.Bar(x=x, y=y, marker_color="#1f6feb")])
    fig.update_layout(
        title="PnL por cuenta (click para drill-through)",
        xaxis_title="Cuenta",
        yaxis_title="Balance",
        template="plotly_white",
        margin=dict(l=20, r=20, t=60, b=40),
        height=360,
    )
    return fig


def _figure_executive_secondary(payload: dict[str, Any]) -> go.Figure:
    rows = payload["balance_sheet"].get("rows") or []
    agg: dict[str, float] = {}
    for row in rows:
        section = str(row.get("section") or "OTHER")
        agg[section] = agg.get(section, 0.0) + _normalize_num(row.get("balance"))
    fig = go.Figure(data=[go.Pie(labels=list(agg.keys()), values=list(agg.values()), hole=0.45)])
    fig.update_layout(
        title="Distribución Balance Sheet por sección",
        template="plotly_white",
        margin=dict(l=20, r=20, t=60, b=40),
        height=360,
    )
    return fig


def _figure_operations_main(payload: dict[str, Any]) -> go.Figure:
    rows = payload["by_pump"].get("rows") or []
    x = [str(r.get("pump_code") or "N/A") for r in rows]
    y = [_normalize_num(r.get("amount_total")) for r in rows]
    fig = go.Figure(data=[go.Bar(x=x, y=y, marker_color="#0f766e")])
    fig.update_layout(
        title="Ventas Fuel por surtidor (click para detalle)",
        xaxis_title="Surtidor",
        yaxis_title="Monto",
        template="plotly_white",
        margin=dict(l=20, r=20, t=60, b=40),
        height=360,
    )
    return fig


def _figure_operations_secondary(payload: dict[str, Any]) -> go.Figure:
    rows = payload["by_day"].get("rows") or []
    x = [str(r.get("date") or "") for r in rows]
    sales = [_normalize_num(r.get("amount_sold")) for r in rows]
    liters = [_normalize_num(r.get("liters_dispensed")) for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=sales, mode="lines+markers", name="Monto vendido"))
    fig.add_trace(go.Scatter(x=x, y=liters, mode="lines+markers", name="Litros despachados", yaxis="y2"))
    fig.update_layout(
        title="Dispense vs Sale por día",
        template="plotly_white",
        margin=dict(l=20, r=20, t=60, b=40),
        height=360,
        yaxis=dict(title="Monto"),
        yaxis2=dict(title="Litros", overlaying="y", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def _table_columns(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not rows:
        return []
    return [{"name": str(key), "id": str(key)} for key in rows[0].keys()]


server = Flask(__name__)
server.secret_key = DASH_SESSION_SECRET

app = Dash(
    __name__,
    server=server,
    requests_pathname_prefix=f"{DASH_URL_PREFIX}/",
    suppress_callback_exceptions=True,
)

app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="workspace-store"),
        html.Div(
            [
                html.Div(
                    [
                        html.H3("Necktral Analytics"),
                        html.Div(id="session-caption"),
                    ],
                    style={"display": "flex", "flexDirection": "column", "gap": "4px"},
                ),
                html.Div(
                    [
                        dcc.Dropdown(
                            id="workspace-select",
                            options=[
                                {"label": WORKSPACES["executive"]["label"], "value": "executive"},
                                {"label": WORKSPACES["operations"]["label"], "value": "operations"},
                            ],
                            value="executive",
                            clearable=False,
                            style={"minWidth": "220px"},
                        ),
                        dcc.DatePickerRange(
                            id="date-range",
                            min_date_allowed=date(2020, 1, 1),
                            max_date_allowed=date(2100, 12, 31),
                            display_format="YYYY-MM-DD",
                        ),
                        html.Button("Refresh", id="refresh-btn", n_clicks=0),
                    ],
                    style={"display": "flex", "gap": "10px", "alignItems": "center"},
                ),
            ],
            style={"display": "flex", "justifyContent": "space-between", "padding": "14px 16px"},
        ),
        html.Div(id="status-banner", style={"padding": "0 16px 8px 16px", "color": "#1f2937"}),
        html.Div(
            [
                dcc.Graph(id="main-chart"),
                dcc.Graph(id="secondary-chart"),
            ],
            style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px", "padding": "0 16px"},
        ),
        html.Div(
            [
                html.H4("Dataset"),
                dash_table.DataTable(id="main-table", page_size=10, style_table={"overflowX": "auto"}),
            ],
            style={"padding": "8px 16px"},
        ),
        html.Div(
            [
                html.H4("Drill-through"),
                html.Div(id="drill-caption"),
                dash_table.DataTable(id="drill-table", page_size=10, style_table={"overflowX": "auto"}),
            ],
            style={"padding": "0 16px 20px 16px"},
        ),
    ]
)


@server.get(f"{DASH_URL_PREFIX}/health")
def health():
    return jsonify({"ok": True, "service": "dash_analytics"})


@server.get(f"{DASH_URL_PREFIX}/bootstrap")
def bootstrap():
    token = (request.args.get("token") or "").strip()
    if not token:
        return ("Missing token", 400)
    redeem_url = f"{DASH_BACKEND_BASE_URL}/backend/dashboard/embed-token/redeem/"
    try:
        response = requests.post(
            redeem_url,
            json={"token": token},
            timeout=DASH_REQUEST_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        return (f"Redeem request failed: {exc}", 502)
    if response.status_code != 200:
        return (f"Redeem failed ({response.status_code}): {response.text}", response.status_code)

    payload = response.json()
    session["reporting_access_token"] = payload.get("reporting_access_token")
    session["reporting_expires_at"] = payload.get("expires_at")
    workspace = payload.get("workspace") or {}
    workspace_key = str(workspace.get("workspace_key") or "executive")
    session["workspace_key"] = workspace_key
    return redirect(f"{DASH_URL_PREFIX}/?workspace={workspace_key}")


@server.get(f"{DASH_URL_PREFIX}/logout")
def logout():
    session.clear()
    return redirect(f"{DASH_URL_PREFIX}/")


@app.callback(
    Output("workspace-select", "value"),
    Output("date-range", "start_date"),
    Output("date-range", "end_date"),
    Input("url", "search"),
)
def init_state(search: str | None):
    qs = str(search or "")
    workspace = session.get("workspace_key") or "executive"
    if "workspace=operations" in qs:
        workspace = "operations"
    today = date.today().isoformat()
    return workspace, today, today


@app.callback(
    Output("session-caption", "children"),
    Output("status-banner", "children"),
    Output("workspace-store", "data"),
    Output("main-chart", "figure"),
    Output("secondary-chart", "figure"),
    Output("main-table", "columns"),
    Output("main-table", "data"),
    Input("refresh-btn", "n_clicks"),
    Input("workspace-select", "value"),
    Input("date-range", "start_date"),
    Input("date-range", "end_date"),
)
def load_workspace(_: int, workspace: str, start_date: str | None, end_date: str | None):
    caption = f"Workspace: {workspace} · Token exp: {session.get('reporting_expires_at') or 'N/A'}"
    if not session.get("reporting_access_token"):
        return (
            caption,
            "No hay sesión activa. Solicita un embed token desde Quasar.",
            {},
            _figure_empty("Sin sesión"),
            _figure_empty("Sin sesión"),
            [],
            [],
        )

    try:
        if workspace == "operations":
            payload = _build_operations_payload(start_date=start_date, end_date=end_date)
            main_fig = _figure_operations_main(payload)
            secondary_fig = _figure_operations_secondary(payload)
            table_rows = list(payload["by_pump"].get("rows") or [])
            status_text = (
                f"Runs: by_pump={payload['by_pump'].get('run_id')} "
                f"by_day={payload['by_day'].get('run_id')} "
                f"reconciliation={payload['reconciliation'].get('run_id')}"
            )
        else:
            payload = _build_executive_payload(start_date=start_date, end_date=end_date)
            main_fig = _figure_executive_main(payload)
            secondary_fig = _figure_executive_secondary(payload)
            table_rows = list(payload["pnl"].get("rows") or [])
            status_text = (
                f"Runs: pnl={payload['pnl'].get('run_id')} "
                f"balance_sheet={payload['balance_sheet'].get('run_id')}"
            )
    except Exception as exc:
        return (
            caption,
            f"Error ejecutando datasets: {exc}",
            {},
            _figure_empty("Error"),
            _figure_empty("Error"),
            [],
            [],
        )

    return (
        caption,
        status_text,
        {"workspace": workspace, "payload": payload, "start_date": start_date, "end_date": end_date},
        main_fig,
        secondary_fig,
        _table_columns(table_rows),
        table_rows,
    )


@app.callback(
    Output("drill-caption", "children"),
    Output("drill-table", "columns"),
    Output("drill-table", "data"),
    Input("main-chart", "clickData"),
    Input("workspace-store", "data"),
)
def run_drill(click_data: dict[str, Any] | None, store: dict[str, Any] | None):
    if not store:
        return "Selecciona un workspace y ejecuta refresh.", [], []
    if not click_data:
        return "Haz click en un punto del gráfico principal para ver detalle.", [], []

    workspace = str(store.get("workspace") or "")
    payload = store.get("payload") or {}
    start_date = store.get("start_date")
    end_date = store.get("end_date")

    if workspace == "operations":
        point = ((click_data or {}).get("points") or [{}])[0]
        pump_code = str(point.get("x") or "").strip()
        rows = [row for row in list((payload.get("by_pump") or {}).get("rows") or []) if str(row.get("pump_code")) == pump_code]
        return f"Detalle por surtidor: {pump_code or 'N/A'}", _table_columns(rows), rows

    point = ((click_data or {}).get("points") or [{}])[0]
    account_code = str(point.get("x") or "").strip()
    if not account_code:
        return "No se pudo inferir account_code para drill-through.", [], []

    filters = _to_filters(start_date=start_date, end_date=end_date)
    filters["account_code"] = account_code
    try:
        gl = _run_dataset(
            "accounting.general_ledger.transaction",
            filters=filters,
            consumer_ref="dash:executive:drill_gl",
        )
    except Exception as exc:
        return f"Drill-through falló: {exc}", [], []

    rows = list(gl.get("rows") or [])
    caption = f"Drill-through GL ({account_code}) · run_id={gl.get('run_id')}"
    return caption, _table_columns(rows), rows


if __name__ == "__main__":
    server.run(host="0.0.0.0", port=DASH_INTERNAL_PORT)
