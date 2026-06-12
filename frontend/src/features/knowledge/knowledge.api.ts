/**
 * Conocimiento — búsqueda determinista en la documentación interna (FTS español);
 * síntesis con IA opcional (si el kill switch está encendido).
 */
import { api } from 'src/boot/axios';

export interface KnowledgeResult {
  source_path: string;
  heading: string;
  content: string;
  order: number;
}

export interface KnowledgeResponse {
  query: string;
  results: KnowledgeResult[];
  answer: string | null;
  ai_used: boolean;
}

export async function searchKnowledge(
  q: string,
  opts: { limit?: number; synthesize?: boolean } = {},
): Promise<KnowledgeResponse> {
  const params: Record<string, string | number> = { q, limit: opts.limit ?? 8 };
  if (opts.synthesize) params.synthesize = 1;
  const { data } = await api.get<KnowledgeResponse>('/knowledge/search/', { params });
  return data;
}
