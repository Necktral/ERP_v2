import http from "k6/http";
import { check, sleep } from "k6";
import { authHeaders, jsonOrNull, login } from "./auth_common.js";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const USERNAME = __ENV.USERNAME || "k6";
const PASSWORD = __ENV.PASSWORD || "";
const LOGIN_CHURN_USERNAME = __ENV.LOGIN_CHURN_USERNAME || USERNAME;
const LOGIN_CHURN_PASSWORD = __ENV.LOGIN_CHURN_PASSWORD || PASSWORD;
const PROFILE = String(__ENV.QA_LOAD_PROFILE || "security").toLowerCase();
const BOOTSTRAP =
  String(__ENV.BOOTSTRAP || "").toLowerCase() === "1" ||
  String(__ENV.BOOTSTRAP || "").toLowerCase() === "true";

const BOOTSTRAP_USERNAME = __ENV.BOOTSTRAP_USERNAME || "root";
const BOOTSTRAP_EMAIL = __ENV.BOOTSTRAP_EMAIL || "root@test.com";
const BOOTSTRAP_PASSWORD = __ENV.BOOTSTRAP_PASSWORD || "";
const AUTH_TTL_MS = Number(__ENV.TOKEN_TTL_MS || 9 * 60 * 1000);

function toBool(raw, fallback = false) {
  if (raw === undefined || raw === null || raw === "") {
    return fallback;
  }
  const normalized = String(raw).trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
}

const LOGIN_CHURN_ENABLED = toBool(
  __ENV.LOGIN_CHURN_ENABLED,
  PROFILE === "performance",
);
// En performance permitimos umbral de login más amplio para señal estable bajo estrés.
const LOGIN_P95_THRESHOLD = PROFILE === "performance" ? "p(95)<900" : "p(95)<600";

const scenarios = {
  // Flujo principal: sesión autenticada + endpoints /me y /me/acl.
  me_acl: {
    executor: "ramping-vus",
    startVUs: 0,
    stages: [
      {
        duration: __ENV.WARMUP || "15s",
        target: Number(__ENV.VUS_WARMUP || 5),
      },
      {
        duration: __ENV.SUSTAIN || "30s",
        target: Number(__ENV.VUS_TARGET || 20),
      },
      { duration: __ENV.COOLDOWN || "10s", target: 0 },
    ],
    exec: "meAclFlow",
  },
};

if (LOGIN_CHURN_ENABLED) {
  // Flujo secundario: churn de login para tensionar auth sin mezclar con la sesión de me_acl.
  scenarios.login_churn = {
    executor: "ramping-arrival-rate",
    timeUnit: "1s",
    startRate: Number(__ENV.LOGIN_RATE_START || 1),
    preAllocatedVUs: Number(__ENV.LOGIN_VUS_PREALLOC || 10),
    maxVUs: Number(__ENV.LOGIN_VUS_MAX || 50),
    stages: [
      {
        duration: __ENV.WARMUP || "15s",
        target: Number(__ENV.LOGIN_RATE_WARMUP || 1),
      },
      {
        duration: __ENV.SUSTAIN || "30s",
        target: Number(__ENV.LOGIN_RATE_TARGET || 2),
      },
      { duration: __ENV.COOLDOWN || "10s", target: 0 },
    ],
    exec: "loginOnly",
  };
}

const thresholds = {
  http_req_failed: ["rate<0.01"],
  "http_req_duration{scenario:me_acl,name:auth_me}": ["p(95)<500"],
  "http_req_duration{scenario:me_acl,name:auth_acl}": ["p(95)<600"],
};

if (LOGIN_CHURN_ENABLED) {
  thresholds["http_req_duration{scenario:login_churn,name:auth_login}"] = [LOGIN_P95_THRESHOLD];
}

export const options = {
  // Importante para cookie transport: preservar jar por VU durante la corrida.
  noCookiesReset: true,
  scenarios,
  thresholds,
};

function ensureBootstrapped() {
  const statusRes = http.get(`${BASE_URL}/auth/bootstrap/status/`, {
    tags: { name: "auth_bootstrap_status" },
  });
  if (!statusRes || statusRes.status !== 200) {
    return null;
  }

  const statusBody = jsonOrNull(statusRes);
  const isFresh = statusBody ? statusBody.is_fresh : false;
  if (!isFresh) {
    return null;
  }

  const initRes = http.post(
    `${BASE_URL}/auth/bootstrap/init/`,
    JSON.stringify({
      username: BOOTSTRAP_USERNAME,
      email: BOOTSTRAP_EMAIL,
      password: BOOTSTRAP_PASSWORD,
    }),
    {
      headers: { "Content-Type": "application/json" },
      tags: { name: "auth_bootstrap_init" },
    },
  );

  check(initRes, {
    "bootstrap init status 201": (r) => r && r.status === 201,
  });

  return { username: BOOTSTRAP_USERNAME, password: BOOTSTRAP_PASSWORD };
}

let cachedAuth = null;
let cachedAtMs = 0;

function getAuthContext() {
  const now = Date.now();
  if (cachedAuth && now - cachedAtMs < AUTH_TTL_MS) {
    return cachedAuth;
  }

  const authCtx = login({
    baseUrl: BASE_URL,
    username: USERNAME,
    password: PASSWORD,
    tags: { profile: PROFILE },
  });
  if (authCtx.ok) {
    cachedAuth = authCtx;
    cachedAtMs = now;
  }
  return authCtx;
}

export function setup() {
  if (!BOOTSTRAP) {
    return null;
  }
  return ensureBootstrapped();
}

export function loginOnly() {
  const authCtx = login({
    baseUrl: BASE_URL,
    username: LOGIN_CHURN_USERNAME,
    password: LOGIN_CHURN_PASSWORD,
    tags: { profile: PROFILE },
  });
  if (!authCtx.ok) {
    sleep(0.1);
  }
}

export function meAclFlow() {
  const authCtx = getAuthContext();
  if (!authCtx || !authCtx.ok) {
    sleep(0.2);
    return;
  }

  const me = http.get(`${BASE_URL}/auth/me/`, {
    headers: authHeaders(authCtx),
    tags: { name: "auth_me", profile: PROFILE },
  });
  check(me, { "me status 200": (r) => r && r.status === 200 });

  const acl = http.get(`${BASE_URL}/auth/me/acl/`, {
    headers: authHeaders(authCtx),
    tags: { name: "auth_acl", profile: PROFILE },
  });
  check(acl, { "acl status 200": (r) => r && r.status === 200 });

  sleep(Number(__ENV.SLEEP || 0.1));
}
