import { defineStore } from 'pinia';
import { authApi } from 'src/boot/axios';
import { clearTokens, readTokens, writeTokens } from 'src/core/storage/auth';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

type LoginResponse = { access: string; refresh: string };
type RefreshResponse = { access: string; refresh?: string };

export const useAuthStore = defineStore('auth', {
  state: () => ({
    hydrated: false as boolean,
    status: 'anonymous' as 'anonymous' | 'authenticated' | 'refreshing',
    accessToken: null as string | null,
    refreshToken: null as string | null,

    // lock interno para refresh concurrente
    refreshInFlight: null as Promise<void> | null,
  }),

  getters: {
    isAuthenticated: (s) => Boolean(s.accessToken && s.refreshToken),
  },

  actions: {
    initFromStorage() {
      if (this.hydrated) return;
      const t = readTokens();
      this.accessToken = t.access;
      this.refreshToken = t.refresh;
      this.status = this.isAuthenticated ? 'authenticated' : 'anonymous';
      this.hydrated = true;
    },

    async login(username: string, password: string) {
      const { data } = await authApi.post<LoginResponse>('/auth/login/', { username, password });
      this.accessToken = data.access;
      this.refreshToken = data.refresh;
      this.status = 'authenticated';
      writeTokens({ access: data.access, refresh: data.refresh });
    },

    async refresh() {
      const currentRefresh = this.refreshToken;
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

      // limpiar stores primero para cortar UI rápido
      this.hardClearLocal();

      // y luego intentar avisar al backend (si falla, no pasa nada)
      if (refresh && access) {
        try {
          // Usamos authApi pero inyectamos el header manualmente
          // (porque hardClearLocal ya borró el token del store)
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
