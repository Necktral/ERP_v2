import http from "k6/http";
import { check } from "k6";

export function jsonOrNull(res) {
  try {
    return res && res.json ? res.json() : null;
  } catch (_) {
    return null;
  }
}

function _cookieName() {
  return __ENV.AUTH_COOKIE_ACCESS_NAME || "nt_access";
}

function _hasCookieInResponse(res, cookieName) {
  if (!res || !res.cookies) {
    return false;
  }
  const bucket = res.cookies[cookieName];
  return Array.isArray(bucket) && bucket.length > 0;
}

function _hasCookieInJar(baseUrl, cookieName) {
  try {
    const jar = http.cookieJar();
    const cookies = jar.cookiesForURL(baseUrl) || {};
    return Boolean(cookies[cookieName]);
  } catch (_) {
    return false;
  }
}

function _toBool(raw, fallback = false) {
  if (raw === undefined || raw === null || raw === "") {
    return fallback;
  }
  const normalized = String(raw).trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes";
}

export function parseDurationToMs(rawValue) {
  if (rawValue === undefined || rawValue === null) {
    return null;
  }
  const raw = String(rawValue).trim();
  if (!raw || raw === "0s") {
    return 0;
  }
  const match = raw.match(/^([0-9]+(?:\.[0-9]+)?)(ms|s|m|us|µs)$/i);
  if (!match) {
    return null;
  }
  const value = Number(match[1]);
  const unit = match[2].toLowerCase();
  if (unit === "m") return value * 60 * 1000;
  if (unit === "s") return value * 1000;
  if (unit === "ms") return value;
  if (unit === "us" || unit === "µs") return value / 1000;
  return null;
}

export function authMode() {
  // Forzado opcional para debugging; en CI normal queda en auto-detect.
  const forceHeader = _toBool(__ENV.K6_FORCE_HEADER_AUTH, false);
  const forceCookie = _toBool(__ENV.K6_FORCE_COOKIE_AUTH, false);
  if (forceHeader) return "header";
  if (forceCookie) return "cookie";
  return "auto";
}

export function login({ baseUrl, username, password, tags = {} }) {
  // Contrato dual:
  // - header mode: body con access token
  // - cookie mode: cookie de sesión (nt_access por defecto)
  const res = http.post(
    `${baseUrl}/auth/login/`,
    JSON.stringify({ username, password }),
    {
      headers: { "Content-Type": "application/json" },
      tags: { name: "auth_login", ...tags },
    },
  );

  const body = jsonOrNull(res);
  const accessToken = body && body.access ? body.access : null;
  const cookieName = _cookieName();
  const hasSessionCookie =
    _hasCookieInResponse(res, cookieName) || _hasCookieInJar(baseUrl, cookieName);

  const mode = authMode();
  let transport = "unknown";
  if (mode === "header") {
    transport = "header";
  } else if (mode === "cookie") {
    transport = "cookie";
  } else if (accessToken) {
    transport = "header";
  } else if (hasSessionCookie) {
    transport = "cookie";
  }

  const checks = {
    "login status 200": (r) => r && r.status === 200,
  };
  // Check condicional por transporte para evitar falsos negativos cuando AUTH_TOKEN_TRANSPORT=cookie.
  if (transport === "cookie") {
    checks["login has session cookie"] = () => hasSessionCookie;
  } else {
    checks["login has access"] = () => !!accessToken;
  }
  check(res, checks);

  return {
    ok: res && res.status === 200 && (transport === "cookie" ? hasSessionCookie : !!accessToken),
    transport,
    accessToken,
    hasSessionCookie,
    statusCode: res ? res.status : null,
    response: res,
  };
}

export function authHeaders(authCtx, extra = {}) {
  const headers = { ...extra };
  if (authCtx && authCtx.transport === "header" && authCtx.accessToken) {
    headers.Authorization = `Bearer ${authCtx.accessToken}`;
  }
  return headers;
}
