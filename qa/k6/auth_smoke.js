import http from "k6/http";
import { check, sleep } from "k6";
import { authHeaders, jsonOrNull, login } from "./auth_common.js";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const USERNAME = __ENV.USERNAME || "admin";
const PASSWORD = __ENV.PASSWORD || "admin";
const BOOTSTRAP =
  String(__ENV.BOOTSTRAP || "").toLowerCase() === "1" ||
  String(__ENV.BOOTSTRAP || "").toLowerCase() === "true";

const BOOTSTRAP_USERNAME = __ENV.BOOTSTRAP_USERNAME || "root";
const BOOTSTRAP_EMAIL = __ENV.BOOTSTRAP_EMAIL || "root@test.com";
const BOOTSTRAP_PASSWORD = __ENV.BOOTSTRAP_PASSWORD || "";
const AUTH_TTL_MS = Number(__ENV.TOKEN_TTL_MS || 9 * 60 * 1000);

let cachedAuth = null;
let cachedAuthAtMs = 0;

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: __ENV.DURATION || "30s",
  // Mantiene cookies entre iteraciones para simular sesión real (cookie auth).
  noCookiesReset: true,
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{name:auth_me}": ["p(95)<500"],
    "http_req_duration{name:auth_acl}": ["p(95)<600"],
  },
};

function ensureBootstrapped() {
  const statusRes = http.get(`${BASE_URL}/auth/bootstrap/status/`);
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
    { headers: { "Content-Type": "application/json" } },
  );

  check(initRes, {
    "bootstrap init status 201": (r) => r && r.status === 201,
  });

  return { username: BOOTSTRAP_USERNAME, password: BOOTSTRAP_PASSWORD };
}

function getAuthContext(username, password) {
  const now = Date.now();
  // Reutiliza contexto auth para no hacer login por iteración y evitar churn artificial.
  if (cachedAuth && now - cachedAuthAtMs < AUTH_TTL_MS) {
    return cachedAuth;
  }

  const authCtx = login({
    baseUrl: BASE_URL,
    username,
    password,
  });
  if (authCtx.ok) {
    cachedAuth = authCtx;
    cachedAuthAtMs = now;
  }
  return authCtx;
}

export function setup() {
  if (!BOOTSTRAP) {
    return null;
  }

  const creds = ensureBootstrapped();
  if (!creds) {
    return null;
  }

  sleep(0.1);
  const authCtx = login({
    baseUrl: BASE_URL,
    username: creds.username,
    password: creds.password,
  });
  if (!authCtx.ok) {
    return creds;
  }

  const orgRes = http.post(
    `${BASE_URL}/auth/bootstrap/org/`,
    JSON.stringify({
      holding_name: __ENV.HOLDING_NAME || "HOLDING",
      company_name: __ENV.COMPANY_NAME || "ACME",
      company_tax_id: __ENV.COMPANY_TAX_ID || "J-123",
      branch_name: __ENV.BRANCH_NAME || "ACME-1",
      branch_address: __ENV.BRANCH_ADDRESS || "Main street",
    }),
    {
      headers: authHeaders(authCtx, {
        "Content-Type": "application/json",
      }),
    },
  );

  check(orgRes, {
    "bootstrap org status 200/400/409": (r) =>
      r && (r.status === 200 || r.status === 400 || r.status === 409),
  });

  return creds;
}

export default function (data) {
  const username = data && data.username ? data.username : USERNAME;
  const password = data && data.password ? data.password : PASSWORD;

  const authCtx = getAuthContext(username, password);
  if (!authCtx || !authCtx.ok) {
    sleep(Number(__ENV.SLEEP || 1));
    return;
  }

  const me = http.get(`${BASE_URL}/auth/me/`, {
    headers: authHeaders(authCtx),
    tags: { name: "auth_me" },
  });
  check(me, { "me status 200": (r) => r && r.status === 200 });

  const acl = http.get(`${BASE_URL}/auth/me/acl/`, {
    headers: authHeaders(authCtx),
    tags: { name: "auth_acl" },
  });
  check(acl, { "acl status 200": (r) => r && r.status === 200 });

  const aclBody = jsonOrNull(acl);
  const recommendedCompanyId = aclBody ? aclBody.recommended_company_id : null;
  if (recommendedCompanyId) {
    const org = http.get(`${BASE_URL}/org/companies/`, {
      headers: authHeaders(authCtx, {
        "X-Company-Id": String(recommendedCompanyId),
      }),
      tags: { name: "org_companies" },
    });
    check(org, {
      "org companies status 200/403": (r) => r && (r.status === 200 || r.status === 403),
    });
  }

  sleep(Number(__ENV.SLEEP || 1));
}
