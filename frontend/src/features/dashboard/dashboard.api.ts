/**
 * Analítica / Dashboard — workspaces de tableros y tokens de embed temporales.
 */
import { api } from 'src/boot/axios';

export interface WorkspaceRow {
  key: string;
  label: string;
  [k: string]: unknown;
}

export async function listWorkspaces(): Promise<WorkspaceRow[]> {
  const { data } = await api.get<{ results: WorkspaceRow[] }>('/backend/dashboard/workspaces/');
  return data.results;
}

export async function createEmbedToken(workspaceKey: string): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>('/backend/dashboard/embed-token/', {
    workspace_key: workspaceKey,
  });
  return data;
}
