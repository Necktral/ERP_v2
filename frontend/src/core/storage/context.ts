import { STORAGE_KEYS } from './keys';

export type StoredContext = {
  companyId: string | null;
  branchId: string | null;
};

export function readContext(): StoredContext {
  return {
    companyId: localStorage.getItem(STORAGE_KEYS.CTX_COMPANY_ID),
    branchId: localStorage.getItem(STORAGE_KEYS.CTX_BRANCH_ID),
  };
}

export function writeContext(ctx: { companyId: string; branchId?: string | null }) {
  localStorage.setItem(STORAGE_KEYS.CTX_COMPANY_ID, ctx.companyId);
  if (ctx.branchId) localStorage.setItem(STORAGE_KEYS.CTX_BRANCH_ID, ctx.branchId);
  else localStorage.removeItem(STORAGE_KEYS.CTX_BRANCH_ID);
}

export function clearContext() {
  localStorage.removeItem(STORAGE_KEYS.CTX_COMPANY_ID);
  localStorage.removeItem(STORAGE_KEYS.CTX_BRANCH_ID);
}
