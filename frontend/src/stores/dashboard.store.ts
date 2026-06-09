import { defineStore } from 'pinia';
import { api } from 'src/boot/axios';

type WorkspaceInfo = {
  workspace_key: string;
  title: string;
  description: string;
  required_permissions: string[];
  datasets: string[];
  compose_allowed: boolean;
};

type WorkspaceListResponse = {
  count: number;
  results: WorkspaceInfo[];
};

type EmbedTokenResponse = {
  workspace_key: string;
  bootstrap_url: string;
  expires_at: string;
  workspace: WorkspaceInfo;
};

interface DashboardState {
  loading: boolean;
  workspaces: WorkspaceInfo[];
  activeWorkspace: string;
  iframeUrl: string;
  embedExpiresAt: string;
  lastError: string;
}

export const useDashboardStore = defineStore('dashboard', {
  state: (): DashboardState => ({
    loading: false,
    workspaces: [],
    activeWorkspace: 'executive',
    iframeUrl: '',
    embedExpiresAt: '',
    lastError: '',
  }),

  getters: {
    hasIframe: (s) => Boolean(s.iframeUrl),
  },

  actions: {
    async loadWorkspaces() {
      const { data } = await api.get<WorkspaceListResponse>('/backend/dashboard/workspaces/');
      this.workspaces = data.results ?? [];
      if (!this.workspaces.find((w) => w.workspace_key === this.activeWorkspace)) {
        this.activeWorkspace = this.workspaces[0]?.workspace_key ?? 'executive';
      }
    },

    async openWorkspace(workspaceKey: string, requireCompose = false) {
      this.loading = true;
      this.lastError = '';
      try {
        const { data } = await api.post<EmbedTokenResponse>('/backend/dashboard/embed-token/', {
          workspace_key: workspaceKey,
          require_compose: requireCompose,
        });
        this.activeWorkspace = data.workspace_key;
        this.iframeUrl = data.bootstrap_url;
        this.embedExpiresAt = data.expires_at;
      } catch (error) {
        this.iframeUrl = '';
        this.embedExpiresAt = '';
        this.lastError = error instanceof Error ? error.message : String(error);
        throw error;
      } finally {
        this.loading = false;
      }
    },
  },
});
