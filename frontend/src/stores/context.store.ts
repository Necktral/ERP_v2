import { defineStore } from 'pinia';
import { clearContext, readContext, writeContext } from 'src/core/storage/context';

export const useContextStore = defineStore('context', {
  state: () => ({
    hydrated: false as boolean,
    activeCompanyId: null as string | null,
    activeBranchId: null as string | null,
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
