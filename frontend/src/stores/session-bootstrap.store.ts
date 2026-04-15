import { defineStore } from 'pinia';
import { api } from 'src/boot/axios';
import { useAclStore, type AclSnapshot } from 'src/stores/acl.store';
import { useAuthStore } from 'src/stores/auth.store';
import { useContextStore } from 'src/stores/context.store';

type ShellMode = 'desktop' | 'mobile';
type DeviceClass = 'desktop' | 'mobile';

type BootstrapSessionResponse = {
  user: {
    id: number;
    username: string;
    must_change_password: boolean;
    is_setup_complete: boolean;
  };
  device: {
    device_class: DeviceClass;
    source_device: string;
  };
  bootstrap_state: {
    is_fresh: boolean;
    setup_required: boolean;
  };
  effective_context: {
    company_id: string | null;
    branch_id: string | null;
    recommended_company_id: string | null;
    recommended_branch_id: string | null;
    requires_context_selection: boolean;
  };
  capabilities: {
    acl_snapshot: AclSnapshot;
  };
  allowed_modules: string[];
  feature_flags: Record<string, boolean>;
  shell_mode: ShellMode;
  trace: {
    request_id: string;
    audit_event_id: string;
    channel: string;
    source_device: string;
  };
};

function detectDeviceClass(): DeviceClass {
  if (typeof window === 'undefined') return 'desktop';

  const byViewport = window.matchMedia?.('(max-width: 1023px)').matches ?? false;
  const ua = navigator.userAgent || '';
  const byUserAgent = /android|iphone|ipad|ipod|mobile/i.test(ua);
  return byViewport || byUserAgent ? 'mobile' : 'desktop';
}

function hasContextInAcl(snapshot: AclSnapshot, companyId: string): boolean {
  return snapshot.companies.some((company) => String(company.company_id) === String(companyId));
}

export const useSessionBootstrapStore = defineStore('sessionBootstrap', {
  state: () => ({
    loaded: false as boolean,
    loading: false as boolean,
    payload: null as BootstrapSessionResponse | null,
  }),

  getters: {
    shellMode: (s): ShellMode => s.payload?.shell_mode ?? 'desktop',
    isMobileShell(): boolean {
      return this.shellMode === 'mobile';
    },
    user: (s) => s.payload?.user ?? null,
    effectiveContext: (s) => s.payload?.effective_context ?? null,
  },

  actions: {
    clear() {
      this.loaded = false;
      this.loading = false;
      this.payload = null;
    },

    async loadSession(options?: { force?: boolean }) {
      if (this.loading) return this.payload;
      if (this.loaded && !options?.force) return this.payload;

      this.loading = true;
      try {
        const deviceClass = detectDeviceClass();
        const sourceDevice = `web-spa-${deviceClass}`;

        const { data } = await api.get<BootstrapSessionResponse>('/auth/bootstrap/session/', {
          headers: {
            'X-Device-Class': deviceClass,
            'X-Source-Device': sourceDevice,
            'X-Channel': 'web',
          },
        });

        this.payload = data;
        this.loaded = true;

        const auth = useAuthStore();
        const acl = useAclStore();
        const ctx = useContextStore();

        auth.applyBootstrapUser(data.user);
        acl.hydrateSnapshot(data.capabilities.acl_snapshot);

        const currentCompanyId = ctx.activeCompanyId;
        if (currentCompanyId && !hasContextInAcl(data.capabilities.acl_snapshot, currentCompanyId)) {
          ctx.clear();
        }

        if (!ctx.activeCompanyId && data.effective_context.recommended_company_id) {
          ctx.setContext(
            data.effective_context.recommended_company_id,
            data.effective_context.recommended_branch_id ?? null,
          );
        }

        return data;
      } finally {
        this.loading = false;
      }
    },
  },
});
