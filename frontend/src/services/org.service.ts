import { api } from 'src/boot/axios';

export type CompanyProfile = {
  legal_name: string;
  tax_id: string;
  address: string;
  phone: string;
  email: string;
};

export type BranchRow = {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  address: string;
  phone: string;
  email: string;
};

export type CreateBranchPayload = {
  name: string;
  code?: string;
  address?: string;
  phone?: string;
  email?: string;
};

export type PatchBranchPayload = Partial<{
  name: string;
  code: string;
  is_active: boolean;
  address: string;
  phone: string;
  email: string;
}>;

export async function getCompanyProfile() {
  const { data } = await api.get<CompanyProfile>('/org/company/profile/');
  return data;
}

export async function updateCompanyProfile(payload: Partial<CompanyProfile>) {
  const { data } = await api.put<{ ok: true }>('/org/company/profile/', payload);
  return data;
}

export async function listBranches() {
  const { data } = await api.get<{ results: BranchRow[] }>('/org/branches/');
  return data.results;
}

export async function createBranch(payload: CreateBranchPayload) {
  // En tests: devuelve 201 con { id } (branch_id) :contentReference[oaicite:4]{index=4}
  const { data } = await api.post<{ id: number }>('/org/branches/', payload);
  return data.id;
}

export async function patchBranch(branchId: number, payload: PatchBranchPayload) {
  // En tests: devuelve 200 con { ok: true } :contentReference[oaicite:5]{index=5}
  const { data } = await api.patch<{ ok: true }>(`/org/branches/${branchId}/`, payload);
  return data;
}
