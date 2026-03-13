import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const USERNAME = __ENV.USERNAME || "admin";
const PASSWORD = __ENV.PASSWORD || "admin";
const BOOTSTRAP =
  String(__ENV.BOOTSTRAP || "").toLowerCase() === "1" ||
  String(__ENV.BOOTSTRAP || "").toLowerCase() === "true";

const BOOTSTRAP_USERNAME = __ENV.BOOTSTRAP_USERNAME || "root";
const BOOTSTRAP_EMAIL = __ENV.BOOTSTRAP_EMAIL || "root@test.com";
const BOOTSTRAP_PASSWORD = __ENV.BOOTSTRAP_PASSWORD || "";

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: __ENV.DURATION || "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<800"],
  },
};

function jsonOrNull(res) {
  try {
    return res && res.json ? res.json() : null;
  } catch (_) {
    return null;
  }
}

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

function login(username, password) {
  const res = http.post(
    `${BASE_URL}/auth/login/`,
    JSON.stringify({ username, password }),
    { headers: { "Content-Type": "application/json" } },
  );

  const body = jsonOrNull(res);
  const access = body && body.access ? body.access : null;

  check(res, {
    "login status 200": (r) => r && r.status === 200,
    "login has access": () => !!access,
  });

  if ((!res || res.status !== 200) && __VU === 1 && __ITER === 0) {
    const bodyPreview =
      res && res.body ? String(res.body).slice(0, 500) : "<no-body>";
    // eslint-disable-next-line no-console
    console.error(
      `login failed: status=${res ? res.status : "<no-res>"} body=${bodyPreview}`,
    );
  }

  return access;
}

export function setup() {
  if (!BOOTSTRAP) {
    return null;
  }

  const creds = ensureBootstrapped();
  if (!creds) {
    return null;
  }

  // Si el sistema estaba fresh, cerramos el circuito con bootstrap org.
  sleep(0.1);
  const token = login(creds.username, creds.password);
  if (!token) {
    return creds;
  }

  const withAuth = { headers: { Authorization: `Bearer ${token}` } };
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
      ...withAuth,
      headers: { ...withAuth.headers, "Content-Type": "application/json" },
    },
  );
  // Puede ser 200 (creado) o 400/409 si ya existe; no bloqueamos el smoke por esto.
  check(orgRes, {
    "bootstrap org status 200/400/409": (r) =>
      r && (r.status === 200 || r.status === 400 || r.status === 409),
  });

  return creds;
}

export default function (data) {
  const username = data && data.username ? data.username : USERNAME;
  const password = data && data.password ? data.password : PASSWORD;

  const token = login(username, password);
  if (!token) {
    sleep(0.2);
    return;
  }
  const authHeaders = { Authorization: `Bearer ${token}` };

  const me = http.get(`${BASE_URL}/auth/me/`, { headers: authHeaders });
  check(me, { "me status 200": (r) => r.status === 200 });

  const acl = http.get(`${BASE_URL}/auth/me/acl/`, { headers: authHeaders });
  check(acl, { "acl status 200": (r) => r.status === 200 });

  // Si el ACL trae recomendación de contexto, validamos un endpoint que requiere contexto.
  const aclBody = jsonOrNull(acl);
  const recommendedCompanyId = aclBody ? aclBody.recommended_company_id : null;
  if (recommendedCompanyId) {
    const withCtx = {
      headers: {
        ...authHeaders,
        "X-Company-Id": String(recommendedCompanyId),
      },
    };
    const org = http.get(`${BASE_URL}/org/companies/`, withCtx);
    check(org, {
      "org companies status 200/403": (r) =>
        r.status === 200 || r.status === 403,
    });
  }

  sleep(0.2);
}
