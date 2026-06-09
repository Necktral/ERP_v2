import { defineStore } from 'pinia';
import { clearContext, readContext, writeContext } from 'src/core/storage/context';

interface ContextState {
  hydrated: boolean;
  activeCompanyId: string | null;
  activeBranchId: string | null;
}

export const useContextStore = defineStore('context', {
  state: (): ContextState => ({
    hydrated: false,
    activeCompanyId: null,
    activeBranchId: null,
  }),

  getters: {
    hasCompanyContext: (s) => Boolean(s.activeCompanyId),
  },

  actions: {
    initFromStorage() {
      if (this.hydrated) return;
      const ctx = readContext();
      this.activeCompanyId = ctx.companyId;
      this.activeBranchId = ctx.branchId;
      this.hydrated = true;
    },

    setContext(companyId: string | number, branchId?: string | number | null) {
      const normalizedCompanyId = String(companyId);
      const normalizedBranchId = branchId != null ? String(branchId) : null;

      this.activeCompanyId = normalizedCompanyId;
      this.activeBranchId = normalizedBranchId;
      writeContext({ companyId: normalizedCompanyId, branchId: normalizedBranchId });
    },

    clear() {
      this.activeCompanyId = null;
      this.activeBranchId = null;
      clearContext();
    },
  },
});
