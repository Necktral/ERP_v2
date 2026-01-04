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

    setContext(companyId: string, branchId?: string | null) {
      this.activeCompanyId = companyId;
      this.activeBranchId = branchId ?? null;
      writeContext({ companyId, branchId: branchId ?? null });
    },

    clear() {
      this.activeCompanyId = null;
      this.activeBranchId = null;
      clearContext();
    },
  },
});
