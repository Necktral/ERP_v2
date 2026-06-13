/**
 * Capa de datos de Recursos Humanos — cliente tipado, fuente única.
 *
 * Mapea los endpoints reales del backend (`/api/hr/*`, `/api/rbac/roles/`,
 * `/api/org/branches/`). Las vistas NO llaman a axios directo: usan estas funciones.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export interface Position {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
}

export interface PermissionRef {
  code: string;
  description: string;
}

export interface Role {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  permissions: PermissionRef[];
}

export interface Branch {
  id: number;
  name: string;
}

export type RoleScope = 'BRANCH' | 'COMPANY';

export interface RoleMap {
  role_id: number;
  scope_mode: RoleScope;
}

export interface AssignmentRow {
  id: number;
  is_active: boolean;
  position_id: number;
  position_name: string;
  branch_id: number | null;
  branch_name: string | null;
  started_at: string | null;
  ended_at?: string | null;
}

export type EmploymentStatus = 'ACTIVO' | 'SUSPENDIDO' | 'BAJA';
export type HrGender = 'M' | 'F' | '';
export type HrSalaryType = 'DAILY' | 'MONTHLY';

export interface EmployeeRow {
  id: number;
  employee_code: string;
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  // Datos de planilla (los copia la nómina al agregar a la planilla)
  cedula: string;
  inss_number: string;
  gender: HrGender;
  salary_type: HrSalaryType;
  daily_rate_nio: string;
  monthly_salary_nio: string;
  has_photo: boolean;
  is_active: boolean;
  employment_status: EmploymentStatus;
  party_id: number | null;
  party_display_name: string | null;
  party_tax_id: string;
  party_national_id: string;
  linked_user_id: number | null;
  linked_username: string | null;
  has_active_assignment: boolean;
  active_assignments: AssignmentRow[];
  roles: EmployeeRoleRow[];
}

export interface EmployeeInput {
  first_name: string;
  last_name?: string;
  employee_code?: string;
  phone?: string;
  email?: string;
  cedula?: string;
  inss_number?: string;
  gender?: HrGender;
  salary_type?: HrSalaryType;
  daily_rate_nio?: string;
  monthly_salary_nio?: string;
  is_active?: boolean;
}

export interface OnboardingSummary {
  positions_count: number;
  positions_with_roles: number;
  employees_count: number;
  employees_active: number;
  employees_suspended: number;
  employees_terminated: number;
  employees_assigned: number;
  employees_provisioned: number;
  next_step: 'POSITIONS' | 'POSITION_ROLES' | 'EMPLOYEES' | 'ASSIGNMENTS' | 'PROVISIONING' | 'DONE';
  complete: boolean;
}

export interface ProvisionResult {
  user_id: number;
  username: string;
  temp_password: string;
}

// --- Onboarding -----------------------------------------------------------
export async function getOnboardingSummary(): Promise<OnboardingSummary> {
  const { data } = await api.get<OnboardingSummary>('/hr/onboarding/summary/');
  return data;
}

// --- Puestos --------------------------------------------------------------
export async function listPositions(): Promise<Position[]> {
  const { data } = await api.get<Paginated<Position>>('/hr/positions/', { params: PAGE });
  return data.results;
}

export async function createPosition(input: { name: string; code?: string }): Promise<number> {
  const { data } = await api.post<{ id: number }>('/hr/positions/', input);
  return data.id;
}

export async function updatePosition(
  id: number,
  patch: Partial<{ name: string; code: string; is_active: boolean }>,
): Promise<void> {
  await api.patch(`/hr/positions/${id}/`, patch);
}

export async function setPositionRoles(id: number, maps: RoleMap[]): Promise<void> {
  await api.put(`/hr/positions/${id}/roles/`, { maps });
}

export interface PositionRoleMapRow {
  role_id: number;
  role_name: string;
  scope_mode: RoleScope;
}

export async function getPositionRoles(id: number): Promise<PositionRoleMapRow[]> {
  const { data } = await api.get<{ results: PositionRoleMapRow[] }>(`/hr/positions/${id}/roles/`);
  return data.results;
}

// --- Roles / Sucursales (selectores) -------------------------------------
export async function listRoles(): Promise<Role[]> {
  const { data } = await api.get<Paginated<Role>>('/rbac/roles/', {
    params: { ...PAGE, include_permissions: 1 },
  });
  return data.results.map((r) => ({ ...r, permissions: r.permissions ?? [] }));
}

export async function listBranches(): Promise<Branch[]> {
  const { data } = await api.get<Paginated<Branch>>('/org/branches/', { params: PAGE });
  return data.results;
}

// --- Trabajadores ---------------------------------------------------------
export async function listEmployees(): Promise<EmployeeRow[]> {
  const { data } = await api.get<Paginated<EmployeeRow>>('/hr/employees/', { params: PAGE });
  return data.results;
}

export async function createEmployee(input: EmployeeInput): Promise<number> {
  const { data } = await api.post<{ id: number }>('/hr/employees/', input);
  return data.id;
}

export async function updateEmployee(id: number, patch: Partial<EmployeeInput>): Promise<void> {
  await api.patch(`/hr/employees/${id}/`, patch);
}

// --- Roles directos del trabajador ---
export interface EmployeeRoleRow {
  role_id: number;
  role_name: string;
}

export async function getEmployeeRoles(employeeId: number): Promise<EmployeeRoleRow[]> {
  const { data } = await api.get<{ results: EmployeeRoleRow[] }>(`/hr/employees/${employeeId}/roles/`);
  return data.results;
}

export async function setEmployeeRoles(employeeId: number, roleIds: number[]): Promise<void> {
  await api.put(`/hr/employees/${employeeId}/roles/`, { role_ids: roleIds });
}

// --- Asignaciones ---------------------------------------------------------
export async function createAssignment(
  employeeId: number,
  input: { position_id: number; branch_id?: number | null },
): Promise<number> {
  const { data } = await api.post<{ id: number }>(`/hr/employees/${employeeId}/assignments/`, input);
  return data.id;
}

export async function endAssignment(employeeId: number, assignmentId: number): Promise<void> {
  await api.post(`/hr/employees/${employeeId}/assignments/${assignmentId}/end/`, {});
}

// --- Acceso (provisión) ---------------------------------------------------
export async function provisionUser(
  employeeId: number,
  input: { username: string; email?: string; temp_password?: string },
): Promise<ProvisionResult> {
  const { data } = await api.post<ProvisionResult>(
    `/hr/employees/${employeeId}/provision-user/`,
    input,
  );
  return data;
}

export async function resetTempPassword(
  employeeId: number,
  input: { temp_password?: string } = {},
): Promise<ProvisionResult> {
  const { data } = await api.post<ProvisionResult>(
    `/hr/employees/${employeeId}/reset-temp-password/`,
    input,
  );
  return data;
}

export async function revokeAccess(
  employeeId: number,
  input: { disable_user?: boolean } = {},
): Promise<void> {
  await api.post(`/hr/employees/${employeeId}/revoke-access/`, input);
}

// --- Catálogos (choices del backend, fuente única) -------------------------
export interface CatalogChoice {
  value: string;
  label: string;
}

export interface HrCatalogs {
  baja_reasons: CatalogChoice[];
  suspension_reasons: CatalogChoice[];
  contract_types: CatalogChoice[];
  salary_periods: CatalogChoice[];
  memo_types: CatalogChoice[];
  employment_statuses: CatalogChoice[];
}

export async function getHrCatalogs(): Promise<HrCatalogs> {
  const { data } = await api.get<HrCatalogs>('/hr/catalogs/');
  return data;
}

// --- Ciclo de vida laboral (suspensión / reintegro / baja / reingreso) -----
export interface LifecycleEvent {
  id: number;
  event_type: 'SUSPENSION' | 'REINTEGRO' | 'BAJA' | 'REINGRESO';
  event_type_label: string;
  reason_code: string;
  reason_detail: string;
  effective_date: string;
  end_date: string | null;
  with_pay: boolean;
  access_suspended: boolean;
  created_at: string;
  created_by: string | null;
}

export async function getLifecycle(employeeId: number): Promise<LifecycleEvent[]> {
  const { data } = await api.get<{ results: LifecycleEvent[] }>(
    `/hr/employees/${employeeId}/lifecycle/`,
  );
  return data.results;
}

export async function suspendEmployee(
  employeeId: number,
  input: {
    reason_code: string;
    reason_detail?: string;
    effective_date: string;
    end_date?: string | null;
    with_pay?: boolean;
    suspend_access?: boolean;
  },
): Promise<void> {
  await api.post(`/hr/employees/${employeeId}/suspend/`, input);
}

export async function reinstateEmployee(
  employeeId: number,
  input: { effective_date: string; reason_detail?: string },
): Promise<void> {
  await api.post(`/hr/employees/${employeeId}/reinstate/`, input);
}

export async function terminateEmployee(
  employeeId: number,
  input: { reason_code: string; reason_detail?: string; effective_date: string },
): Promise<void> {
  await api.post(`/hr/employees/${employeeId}/terminate/`, input);
}

export async function rehireEmployee(
  employeeId: number,
  input: { effective_date: string; reason_detail?: string },
): Promise<void> {
  await api.post(`/hr/employees/${employeeId}/rehire/`, input);
}

// --- Contratos laborales ----------------------------------------------------
export interface ContractRow {
  id: number;
  contract_type: string;
  contract_type_label: string;
  status: 'BORRADOR' | 'EMITIDO' | 'FINALIZADO' | 'ANULADO';
  position_id: number | null;
  position_name: string;
  start_date: string;
  end_date: string | null;
  salary_amount: string | null;
  salary_period: string;
  issued_at: string | null;
  created_at: string;
  body?: string;
}

export async function createContract(
  employeeId: number,
  input: {
    contract_type: string;
    position_id?: number | null;
    start_date: string;
    end_date?: string | null;
    salary_amount?: string | null;
    salary_period?: string;
    work_description?: string;
    season_description?: string;
  },
): Promise<ContractRow> {
  const { data } = await api.post<ContractRow>(`/hr/employees/${employeeId}/contracts/`, input);
  return data;
}

export async function getContract(contractId: number): Promise<ContractRow> {
  const { data } = await api.get<ContractRow>(`/hr/contracts/${contractId}/`);
  return data;
}

export async function updateContract(
  contractId: number,
  patch: Partial<{ body: string; start_date: string; end_date: string | null; salary_amount: string | null; salary_period: string }>,
): Promise<ContractRow> {
  const { data } = await api.patch<ContractRow>(`/hr/contracts/${contractId}/`, patch);
  return data;
}

export async function issueContract(contractId: number): Promise<ContractRow> {
  const { data } = await api.post<ContractRow>(`/hr/contracts/${contractId}/issue/`, {});
  return data;
}

export async function annulContract(contractId: number, reason = ''): Promise<ContractRow> {
  const { data } = await api.post<ContractRow>(`/hr/contracts/${contractId}/annul/`, { reason });
  return data;
}

// --- Memorandos / relaciones laborales --------------------------------------
export interface MemoRow {
  id: number;
  memo_type: string;
  memo_type_label: string;
  status: 'EMITIDO' | 'ANULADO';
  subject: string;
  body: string;
  issued_date: string;
  created_at: string;
  created_by: string | null;
}

export async function createMemo(
  employeeId: number,
  input: { memo_type: string; subject: string; body?: string; issued_date?: string },
): Promise<MemoRow> {
  const { data } = await api.post<MemoRow>(`/hr/employees/${employeeId}/memos/`, input);
  return data;
}

export async function annulMemo(memoId: number, reason = ''): Promise<MemoRow> {
  const { data } = await api.post<MemoRow>(`/hr/memos/${memoId}/annul/`, { reason });
  return data;
}

// --- Perfil (expediente) -----------------------------------------------------
export interface EmployeeProfile {
  id: number;
  employee_code: string;
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  cedula: string;
  inss_number: string;
  gender: HrGender;
  salary_type: HrSalaryType;
  daily_rate_nio: string;
  monthly_salary_nio: string;
  has_photo: boolean;
  is_active: boolean;
  employment_status: EmploymentStatus;
  party_id: number | null;
  party_national_id: string;
  linked_user_id: number | null;
  linked_username: string | null;
  linked_user_active: boolean | null;
  roles: EmployeeRoleRow[];
  assignments: AssignmentRow[];
  contracts: ContractRow[];
  memos: MemoRow[];
  lifecycle_events: LifecycleEvent[];
}

export async function getEmployeeProfile(employeeId: number): Promise<EmployeeProfile> {
  const { data } = await api.get<EmployeeProfile>(`/hr/employees/${employeeId}/profile/`);
  return data;
}

// --- Foto del trabajador ------------------------------------------------------
// La imagen exige los headers de auth/contexto, así que un <img src> directo no
// sirve: se baja como blob por axios y se entrega un object URL, con caché en
// memoria para no repetir la descarga en listas (asistencia, trabajadores).
const photoUrlCache = new Map<number, string | null>();

export async function getEmployeePhotoUrl(employeeId: number): Promise<string | null> {
  if (photoUrlCache.has(employeeId)) return photoUrlCache.get(employeeId) ?? null;
  try {
    const { data } = await api.get<Blob>(`/hr/employees/${employeeId}/photo/`, {
      responseType: 'blob',
    });
    const url = URL.createObjectURL(data);
    photoUrlCache.set(employeeId, url);
    return url;
  } catch {
    photoUrlCache.set(employeeId, null);
    return null;
  }
}

function invalidatePhotoCache(employeeId: number) {
  const prev = photoUrlCache.get(employeeId);
  if (prev) URL.revokeObjectURL(prev);
  photoUrlCache.delete(employeeId);
}

export async function uploadEmployeePhoto(employeeId: number, file: File): Promise<void> {
  const form = new FormData();
  form.append('file', file);
  await api.post(`/hr/employees/${employeeId}/photo/`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  invalidatePhotoCache(employeeId);
}

export async function deleteEmployeePhoto(employeeId: number): Promise<void> {
  await api.delete(`/hr/employees/${employeeId}/photo/`);
  invalidatePhotoCache(employeeId);
}
