import { request } from './client';

export type MemoryKind = 'episodic' | 'experience';

export type MemorySummary = {
  id: string;
  kind: MemoryKind;
  status: string;
  title: string;
  current_revision: number;
  active_revision: number | null;
  summary: string;
  source_type: string;
  created_at: string;
  updated_at: string;
  index_status: string;
};

export type ForgetImpact = {
  episodic: number;
  experience: number;
  total: number;
};

export async function listMemories(params: {
  kind?: MemoryKind;
  status?: string;
  q?: string;
  limit?: number;
  cursor?: string;
} = {}) {
  const search = new URLSearchParams();
  if (params.kind) search.set('kind', params.kind);
  if (params.status) search.set('status', params.status);
  if (params.q) search.set('q', params.q);
  if (params.limit != null) search.set('limit', String(params.limit));
  if (params.cursor) search.set('cursor', params.cursor);
  const query = search.toString();
  return request<{ items: MemorySummary[]; next_cursor: string | null }>(
    `/memories${query ? `?${query}` : ''}`,
  );
}

export async function confirmMemory(memoryId: string, expectedRevision: number) {
  return request<MemorySummary>(
    `/memories/${encodeURIComponent(memoryId)}/confirm`,
    { method: 'POST', body: JSON.stringify({ expected_revision: expectedRevision }) },
    true,
  );
}

export async function rejectMemory(memoryId: string, expectedRevision: number) {
  return request<MemorySummary>(
    `/memories/${encodeURIComponent(memoryId)}/reject`,
    { method: 'POST', body: JSON.stringify({ expected_revision: expectedRevision }) },
    true,
  );
}

export async function deleteMemory(memoryId: string) {
  return request<{ deleted: boolean }>(
    `/memories/${encodeURIComponent(memoryId)}`,
    { method: 'DELETE' },
    true,
  );
}

/** 删除聊天勾选“同时清除记忆”前的影响预览（spec §9.3）。 */
export async function getForgetImpact(conversationId: string) {
  return request<ForgetImpact>(
    `/memories/forget-impact?conversation_id=${encodeURIComponent(conversationId)}`,
  );
}
