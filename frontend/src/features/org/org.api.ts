/**
 * Organización — empresas, sucursales y módulos por empresa (multi-empresa).
 *
 * Todo opera sobre la EMPRESA ACTIVA del contexto (X-Company-Id), salvo el
 * listado de empresas que devuelve las accesibles para el usuario.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

// --- Empresas -----------------------------------------------------------------
export interface CompanyRow {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  legal_name: string;
  tax_id: string;
}

export async function listCompanies(): Promise<CompanyRow[]> {
  const { data } = await api.get<Paginated<CompanyRow>>('/org/companies/', { params: PAGE });
  return data.results;
}

export async function createCompany(input: {
  name: string;
  code?: string;
  legal_name?: string;
  tax_id?: string;
  address?: string;
  phone?: string;
  email?: string;
}): Promise<number> {
  const { data } = await api.post<{ id: number }>('/org/companies/', input);
  return data.id;
}

// --- Perfil de la empresa activa ------------------------------------------------
export interface CompanyProfile {
  legal_name: string;
  tax_id: string;
  address: string;
  phone: string;
  email: string;
}

export async function getCompanyProfile(): Promise<CompanyProfile> {
  const { data } = await api.get<CompanyProfile>('/org/company/profile/');
  return data;
}

export async function updateCompanyProfile(input: CompanyProfile): Promise<void> {
  await api.put('/org/company/profile/', input);
}

// --- Sucursales -----------------------------------------------------------------
export interface BranchRow {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  address: string;
  phone: string;
  email: string;
}

export async function listBranches(): Promise<BranchRow[]> {
  const { data } = await api.get<Paginated<BranchRow>>('/org/branches/', { params: PAGE });
  return data.results;
}

export async function createBranch(input: {
  name: string;
  code?: string;
  address?: string;
  phone?: string;
  email?: string;
}): Promise<number> {
  const { data } = await api.post<{ id: number }>('/org/branches/', input);
  return data.id;
}

export async function updateBranch(
  branchId: number,
  patch: Partial<{ name: string; code: string; is_active: boolean; address: string; phone: string; email: string }>,
): Promise<void> {
  await api.patch(`/org/branches/${branchId}/`, patch);
}

// --- Módulos por empresa ----------------------------------------------------------
export interface ModuleState {
  code: string;
  label: string;
  category: string;
  core: boolean;
  is_enabled: boolean;
}

export async function listCompanyModules(): Promise<ModuleState[]> {
  const { data } = await api.get<{ results: ModuleState[] }>('/org/modules/');
  return data.results;
}

/** PUT con la lista de cambios; el backend valida dependencias (409 si faltan). */
export async function updateCompanyModules(
  changes: { code: string; is_enabled: boolean }[],
): Promise<ModuleState[]> {
  const { data } = await api.put<{ results: ModuleState[] }>('/org/modules/', { modules: changes });
  return data.results;
}
