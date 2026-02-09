export type EmployeeActiveAssignmentSummary = {
  id: number;
  position_id: number;
  position_name: string;
  branch_id: number | null;
  branch_name: string | null;
  started_at: string | null;
};

export type EmployeeAssignmentRow = {
  id: number;
  is_active: boolean;
  position_id: number;
  position_name: string;
  branch_id: number | null;
  branch_name: string | null;
  started_at: string | null;
  ended_at: string | null;
};
import { api } from 'src/boot/axios';

type PaginatedResponse<T> = {
  count: number;
  limit: number;
  offset: number;
  results: T[];
};

type ListParams = {
  limit?: number;
  offset?: number;
};

function buildListQuery(params?: ListParams): string {
  if (!params) return '';
  const qs = new URLSearchParams();
  if (typeof params.limit === 'number') qs.set('limit', String(params.limit));
  if (typeof params.offset === 'number') qs.set('offset', String(params.offset));
  const out = qs.toString();
  return out ? `?${out}` : '';
}

export type PositionRow = {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
};

export type EmployeeRow = {
  id: number;
  employee_code: string;
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  is_active: boolean;
  linked_user_id: number | null;
  linked_username?: string | null;
  has_active_assignment?: boolean;
  active_assignments?: EmployeeActiveAssignmentSummary[];
};
export async function listEmployeeAssignments(employeeId: number, params?: ListParams) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<EmployeeAssignmentRow>>(
    `/hr/employees/${employeeId}/assignments/${qs}`,
  );
  return data;
}

export type PositionRoleMapItem = {
  role_id: number;
  scope_mode: 'BRANCH' | 'COMPANY';
};

export async function listPositions(params?: ListParams) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<PositionRow>>(`/hr/positions/${qs}`);
  return data;
}

export async function createPosition(payload: { name: string; code?: string }) {
  const { data } = await api.post<{ id: number }>('/hr/positions/', payload);
  return data.id;
}

export async function patchPosition(
  positionId: number,
  payload: Partial<Pick<PositionRow, 'name' | 'code' | 'is_active'>>,
) {
  const { data } = await api.patch<{ ok: true }>(`/hr/positions/${positionId}/`, payload);
  return data.ok;
}

export async function setPositionRoleMaps(positionId: number, maps: PositionRoleMapItem[]) {
  const { data } = await api.put<{ ok: true }>(`/hr/positions/${positionId}/roles/`, { maps });
  return data.ok;
}

export async function listEmployees(params?: ListParams) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<EmployeeRow>>(`/hr/employees/${qs}`);
  return data;
}

export async function createEmployee(payload: {
  employee_code?: string;
  first_name: string;
  last_name?: string;
  phone?: string;
  email?: string;
  linked_user_id?: number;
}) {
  const { data } = await api.post<{ id: number }>('/hr/employees/', payload);
  return data.id;
}

export async function patchEmployee(
  employeeId: number,
  payload: Partial<EmployeeRow> & { linked_user_id?: number | null },
) {
  const { data } = await api.patch<{ ok: true }>(`/hr/employees/${employeeId}/`, payload);
  return data.ok;
}

export async function createAssignment(
  employeeId: number,
  payload: { position_id: number; branch_id?: number | null },
) {
  const { data } = await api.post<{ id: number }>(
    `/hr/employees/${employeeId}/assignments/`,
    payload,
  );
  return data.id;
}

export async function endAssignment(employeeId: number, assignmentId: number) {
  const { data } = await api.post<{ ok: true }>(
    `/hr/employees/${employeeId}/assignments/${assignmentId}/end/`,
    {},
  );
  return data.ok;
}

export async function provisionEmployeeUser(
  employeeId: number,
  payload: { username: string; email?: string; temp_password?: string },
) {
  const { data } = await api.post<{
    user_id: number;
    username: string;
    temp_password: string;
  }>(`/hr/employees/${employeeId}/provision-user/`, payload);
  return data;
}

export async function resetEmployeeTempPassword(
  employeeId: number,
  payload: { temp_password?: string } = {},
) {
  const { data } = await api.post<{
    user_id: number;
    username: string;
    temp_password: string;
  }>(`/hr/employees/${employeeId}/reset-temp-password/`, payload);
  return data;
}

export type RevokeEmployeeAccessResponse = {
  ok: true;
  employee_id: number;
  linked_user_id: number;
  role_assignments_deactivated: number;
  memberships_deactivated: number;
  user_disabled: boolean;
};

export async function revokeEmployeeAccess(
  employeeId: number,
  payload: { disable_user?: boolean } = {},
) {
  const { data } = await api.post<RevokeEmployeeAccessResponse>(
    `/hr/employees/${employeeId}/revoke-access/`,
    payload,
  );
  return data;
}
