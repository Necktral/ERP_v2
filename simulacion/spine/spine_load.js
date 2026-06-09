// Carga k6 sobre la columna económica (spine), complementa el load de auth.
// Requiere que el escenario esté sembrado: `python manage.py run_business_simulation`.
// Flujo: login JWT (header) → fija X-Company-Id/X-Branch-Id → golpea endpoints de
// lectura del spine (inventario, facturación, nómina, portfolio) bajo carga, con
// thresholds p95 por endpoint.
import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";

const USERNAME = __ENV.SPINE_USERNAME || "sim_admin_demo";
const PASSWORD = __ENV.SPINE_PASSWORD || "sim-pass-x";
const COMPANY_ID = __ENV.SPINE_COMPANY_ID || "";
const BRANCH_ID = __ENV.SPINE_BRANCH_ID || "";

export const options = {
  scenarios: {
    spine_reads: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: __ENV.WARMUP || "10s", target: Number(__ENV.VUS_WARMUP || 3) },
        { duration: __ENV.SUSTAIN || "30s", target: Number(__ENV.VUS_TARGET || 10) },
        { duration: __ENV.COOLDOWN || "10s", target: 0 },
      ],
      exec: "spineCycle",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.02"],
    "http_req_duration{name:spine_login}": ["p(95)<900"],
    "http_req_duration{name:inv_warehouses}": ["p(95)<700"],
    "http_req_duration{name:inv_items}": ["p(95)<700"],
    "http_req_duration{name:billing_docs}": ["p(95)<800"],
    "http_req_duration{name:nomina_periods}": ["p(95)<800"],
  },
};

function login() {
  const res = http.post(
    `${BASE_URL}/auth/login/`,
    JSON.stringify({ username: USERNAME, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" }, tags: { name: "spine_login" } }
  );
  check(res, { "login 200": (r) => r.status === 200 });
  try {
    return JSON.parse(res.body).access || "";
  } catch (e) {
    return "";
  }
}

function ctxHeaders(token) {
  const h = { Authorization: `Bearer ${token}` };
  if (COMPANY_ID) h["X-Company-Id"] = COMPANY_ID;
  if (BRANCH_ID) h["X-Branch-Id"] = BRANCH_ID;
  return h;
}

export function spineCycle() {
  const token = login();
  if (!token) {
    sleep(1);
    return;
  }
  const h = ctxHeaders(token);

  const endpoints = [
    ["inv_warehouses", `${BASE_URL}/inventory/warehouses/`],
    ["inv_items", `${BASE_URL}/inventory/items/`],
    ["billing_docs", `${BASE_URL}/billing/documents/`],
    ["nomina_periods", `${BASE_URL}/nomina/periods/`],
  ];
  for (const [name, url] of endpoints) {
    const res = http.get(url, { headers: h, tags: { name } });
    check(res, { [`${name} ok`]: (r) => r.status === 200 || r.status === 404 });
  }
  sleep(Number(__ENV.THINK || 1));
}
