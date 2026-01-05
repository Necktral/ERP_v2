import { api } from 'src/boot/axios';

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
};

export type PositionRoleMapItem = {
  role_id: number;
  scope_mode: 'BRANCH' | 'COMPANY';
};

export async function listPositions() {
  const { data } = await api.get<PositionRow[]>('/hr/positions/');
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

export async function listEmployees() {
  const { data } = await api.get<EmployeeRow[]>('/hr/employees/');
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
