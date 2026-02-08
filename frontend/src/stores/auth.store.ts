import { defineStore } from 'pinia';
import { isAxiosError } from 'axios';
import { api, authApi } from 'src/boot/axios';
import { clearTokens, readTokens, writeTokens } from 'src/core/storage/auth';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

type LoginResponse = { access: string; refresh: string };
type RefreshResponse = { access: string; refresh?: string };

const AUTH_TRANSPORT = import.meta.env.VITE_AUTH_TRANSPORT || 'header';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    hydrated: false as boolean,
    status: 'anonymous' as 'anonymous' | 'authenticated' | 'refreshing',
    accessToken: null as string | null,
    refreshToken: null as string | null,
    user: null as null | {
      id: number;
      username: string;
      must_change_password: boolean;
      is_setup_complete: boolean;
    },
    bootstrapState: {
      is_fresh: false,
      setup_required: false,
    },

    bootstrapChecked: false as boolean,

    // lock interno para refresh concurrente
    refreshInFlight: null as Promise<void> | null,
  }),

  getters: {
    isAuthenticated: (s) => (AUTH_TRANSPORT === 'cookie' ? s.status === 'authenticated' : Boolean(s.accessToken && s.refreshToken)),
  },

  actions: {
    initFromStorage() {
      if (this.hydrated) return;
      if (AUTH_TRANSPORT === 'cookie') {
        this.hydrated = true;
        return;
      }
      const t = readTokens();
      this.accessToken = t.access;
      this.refreshToken = t.refresh;
      this.status = this.isAuthenticated ? 'authenticated' : 'anonymous';
      this.hydrated = true;
    },

    async login(username: string, password: string) {
      const { data } = await authApi.post<LoginResponse>('/auth/login/', { username, password });
      if (AUTH_TRANSPORT === 'cookie') {
        this.accessToken = null;
        this.refreshToken = null;
        this.status = 'authenticated';
      } else {
        this.accessToken = data.access;
        this.refreshToken = data.refresh;
        this.status = 'authenticated';
        writeTokens({ access: data.access, refresh: data.refresh });
      }

      // Fetch user details immediately to check flags
      await this.fetchMe();
    },

    async fetchMe() {
      try {
        const { data } = await api.get('/auth/me/');
        this.user = data;
      } catch (e) {
        // Si hay tokens viejos (DB reseteada), /me devuelve 401.
        // En ese caso limpiamos sesión para evitar loops de refresh/401.
        if (isAxiosError(e)) {
          const status = e.response?.status;
          if (status === 401 || status === 403) {
            this.hardClearLocal();
          }
        }
        throw e;
      }
    },

    async checkBootstrap() {
      try {
        if (this.bootstrapChecked) return this.bootstrapState;
        const { data } = await authApi.get('/auth/bootstrap/status/');
        this.bootstrapState = data;
        this.bootstrapChecked = true;

        // Si el sistema está fresh, aseguramos no mantener tokens/contexto previos.
        if (data?.is_fresh) {
          this.hardClearLocal();
        }
        return data;
      } catch {
        // quiet fail
      }
    },

    async refresh() {
      const currentRefresh = this.refreshToken;
      if (AUTH_TRANSPORT === 'cookie') {
        await authApi.post('/auth/refresh/', {});
        this.status = 'authenticated';
        return;
      }
      if (!currentRefresh) throw new Error('No refresh token available');

      // lock: si ya hay refresh en progreso, esperar el mismo
      if (this.refreshInFlight) return this.refreshInFlight;

      this.status = 'refreshing';
      this.refreshInFlight = (async () => {
        try {
          const { data } = await authApi.post<RefreshResponse>('/auth/refresh/', {
            refresh: currentRefresh,
          });

          // backend puede rotar refresh: si viene uno nuevo, lo reemplazamos
          const newAccess = data.access;
          const newRefresh = data.refresh ?? currentRefresh;

          this.accessToken = newAccess;
          this.refreshToken = newRefresh;
          this.status = 'authenticated';
          writeTokens({ access: newAccess, refresh: newRefresh });
        } finally {
          this.refreshInFlight = null;
        }
      })();

      return this.refreshInFlight;
    },

    async logout() {
      const refresh = this.refreshToken;
      const access = this.accessToken;

      // limpiar stores primero para cortar UI rapido
      this.hardClearLocal();

      if (AUTH_TRANSPORT === 'cookie') {
        try {
          await authApi.post('/auth/logout/', {});
        } catch {
          // intencional: no bloqueamos el logout local
        }
        return;
      }

      // y luego intentar avisar al backend (si falla, no pasa nada)
      if (refresh && access) {
        try {
          // Usamos authApi pero inyectamos el header manualmente
          // (porque hardClearLocal ya borro el token del store)
          await authApi.post(
            '/auth/logout/',
            { refresh },
            { headers: { Authorization: `Bearer ${access}` } },
          );
        } catch {
          // intencional: no bloqueamos el logout local
        }
      }
    },

    hardClearLocal() {
      const acl = useAclStore();
      const ctx = useContextStore();

      this.accessToken = null;
      this.refreshToken = null;
      this.status = 'anonymous';
      clearTokens();

      acl.clearAcl();
      ctx.clear();
    },
  },
});
