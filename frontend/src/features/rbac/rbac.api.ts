/**
 * Acceso (RBAC) — usuarios del scope, roles y asignaciones por empresa/sucursal.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export interface UserRoleRow {
  assignment_id: number;
  role_id: number;
  role_name: string;
  org_unit_id: number;
  org_unit_name: string;
  org_unit_type: 'COMPANY' | 'BRANCH' | 'HOLDING';
  origin: string;
}

export interface ScopeUserRow {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  roles: UserRoleRow[];
}

export async function listScopeUsers(search = ''): Promise<ScopeUserRow[]> {
  const { data } = await api.get<Paginated<ScopeUserRow>>('/rbac/users/', {
    params: { ...PAGE, ...(search ? { search } : {}) },
  });
  return data.results;
}

export async function assignRole(input: {
  user_id: number;
  role_id: number;
  org_unit_id: number;
}): Promise<void> {
  await api.post('/rbac/assignments/', input);
}

export async function revokeAssignment(assignmentId: number): Promise<void> {
  await api.post(`/rbac/assignments/${assignmentId}/revoke/`, {});
}

export async function getUserEffectivePermissions(userId: number): Promise<string[]> {
  const { data } = await api.get<{ user_id: number; permissions: string[] }>(
    `/rbac/users/${userId}/effective-permissions/`,
  );
  return data.permissions;
}
