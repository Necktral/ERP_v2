import { boot } from 'quasar/wrappers';
import type { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios';
import axios from 'axios';
import { useAuthStore } from 'src/stores/auth.store';
import { useContextStore } from 'src/stores/context.store';

declare module 'axios' {
  export interface AxiosRequestConfig {
    _retry?: boolean;
    _skipAuthRefresh?: boolean;
  }
}

declare module 'vue' {
  interface ComponentCustomProperties {
    $axios: AxiosInstance;
    $api: AxiosInstance;
  }
}

const AUTH_TRANSPORT = 'cookie';
const CSRF_COOKIE_NAME = import.meta.env.VITE_CSRF_COOKIE_NAME || 'nt_csrf';
const RAW_API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api';

function resolveApiBaseUrl(raw: string): string {
  const normalized = (raw || '').trim() || '/api';
  if (AUTH_TRANSPORT !== 'cookie') return normalized;

  // Con auth por cookie, priorizamos same-origin para evitar drift de sesión en móvil.
  if (typeof window === 'undefined') return normalized;
  if (!/^https?:\/\//i.test(normalized)) return normalized;

  try {
    const parsed = new URL(normalized);
    if (parsed.origin !== window.location.origin) {
      console.warn(
        `[auth-cookie] VITE_API_BASE_URL cross-origin (${parsed.origin}) detectado; se fuerza /api para sesión estable.`,
      );
      return '/api';
    }
  } catch {
    return '/api';
  }

  return normalized;
}

const API_BASE_URL = resolveApiBaseUrl(RAW_API_BASE_URL);

function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
  const value = m?.[2];
  return value ? decodeURIComponent(value) : null;
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 25_000,
  withCredentials: AUTH_TRANSPORT === 'cookie',
});

export const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 25_000,
  withCredentials: AUTH_TRANSPORT === 'cookie',
});

// Endpoints exentos de contexto (no requieren X-Company-Id)
const CONTEXT_EXEMPT_PREFIXES = [
  '/auth/login/',
  '/auth/refresh/',
  '/auth/logout/',
  '/auth/me/',
  '/auth/me/acl/',
  '/auth/bootstrap/',
  '/auth/password/',
  '/sync/enroll/',
  '/sync/batch/',
  '/schema/',
];

const AUTH_REFRESH_EXEMPT_PREFIXES = [
  '/auth/login/',
  '/auth/refresh/',
  '/auth/logout/',
  '/auth/bootstrap/',
  '/sync/enroll/',
  '/sync/batch/',
];

function getPath(config: AxiosRequestConfig): string {
  const url = config.url ?? '';
  // Si url es relativa ("/auth/login/"), esto ya sirve.
  // Si fuera absoluta, igual soporta parsing.
  try {
    const full = new URL(url, config.baseURL);
    return full.pathname.replace(/\/api\/?/, '/'); // normaliza si aparece /api/
  } catch {
    return url;
  }
}

function isContextExempt(path: string): boolean {
  return CONTEXT_EXEMPT_PREFIXES.some((p) => path.startsWith(p));
}

function isAuthRefreshExempt(path: string): boolean {
  return AUTH_REFRESH_EXEMPT_PREFIXES.some((p) => path.startsWith(p));
}

export default boot(({ app, router }) => {
  app.config.globalProperties.$axios = axios;
  app.config.globalProperties.$api = api;

  if (
    AUTH_TRANSPORT === 'cookie' &&
    typeof window !== 'undefined' &&
    window.location.protocol !== 'https:' &&
    !['localhost', '127.0.0.1'].includes(window.location.hostname)
  ) {
    console.warn(
      '[auth-cookie] Contexto no HTTPS detectado para sesión autenticada. En LAN/prod se requiere HTTPS para estabilidad y seguridad.',
    );
  }

  api.interceptors.request.use((config) => {
    const auth = useAuthStore();
    const ctx = useContextStore();

    auth.initFromStorage();
    ctx.initFromStorage();

    const path = getPath(config);
    if (isAuthRefreshExempt(path)) {
      config._skipAuthRefresh = true;
    }

    if (AUTH_TRANSPORT === 'cookie') {
      const csrf = readCookie(CSRF_COOKIE_NAME);
      if (csrf) {
        config.headers = config.headers ?? {};
        config.headers['X-CSRF-Token'] = csrf;
      }
    }

    // Identidad del dispositivo enrolado → la bitácora registra desde QUÉ aparato
    // se hizo cada acción (el backend solo lo acepta si el Device está ACTIVO).
    const deviceRaw = localStorage.getItem('nt_device_identity');
    if (deviceRaw) {
      try {
        const deviceId = (JSON.parse(deviceRaw) as { device_id?: string }).device_id;
        if (deviceId) {
          config.headers = config.headers ?? {};
          config.headers['X-Device-Id'] = deviceId;
        }
      } catch {
        /* identidad corrupta: se ignora */
      }
    }

    // Context headers (solo si no es endpoint exento)
    if (!isContextExempt(path)) {
      if (!ctx.activeCompanyId) {
        // Dejar que el router guard fuerce /select-context; aquí devolvemos error claro.
        // También evita llamadas operativas “sin company”.
        const err = new Error('ContextMissing: X-Company-Id is required');
        return Promise.reject(err);
      }

      config.headers = config.headers ?? {};
      config.headers['X-Company-Id'] = ctx.activeCompanyId;
      if (ctx.activeBranchId) config.headers['X-Branch-Id'] = ctx.activeBranchId;
    }

    return config;
  });

  api.interceptors.response.use(
    (resp) => resp,
    async (error: AxiosError) => {
      const auth = useAuthStore();
      const original = error.config as AxiosRequestConfig | undefined;

      // Si no hay config, no hay nada que reintentar
      if (!original) return Promise.reject(error);

      const status = error.response?.status;
      const path = getPath(original);

      // 401: intentar refresh una vez, y reintentar request
      if (status === 401 && isAuthRefreshExempt(path)) {
        return Promise.reject(error);
      }

      if (status === 401 && !original._retry && !original._skipAuthRefresh) {
        original._retry = true;

        try {
          await auth.refresh();

          // Reintentar request (cookies ya viajan automaticamente)
          return api.request(original);
        } catch (e) {
          // Refresh falló → logout duro y llevar a login
          auth.hardClearLocal();
          await router.replace('/login');
          const reason = e instanceof Error ? e : new Error(String(e));
          return Promise.reject(reason);
        }
      }

      // 403: mandamos a /403 (sin romper sesión)
      if (status === 403) {
        await router.replace('/403');
      }

      return Promise.reject(error);
    },
  );
});

export { axios };
