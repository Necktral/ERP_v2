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
