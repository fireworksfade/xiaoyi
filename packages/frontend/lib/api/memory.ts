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

export type MemorySourceSummary = {
  id: string;
  source_type: string;
  run_id: string | null;
  conversation_id: string | null;
  diagnosis_id: string | null;
  command_id: string | null;
  mcp_server_id: string | null;
  access_state: string;
  excerpt: Record<string, unknown>;
  content_hash: string;
};

export type MemoryDetail = MemorySummary & {
  content: Record<string, unknown>;
  applicability: Record<string, unknown>;
  review_state: string;
  sources: MemorySourceSummary[];
  active_version?: {
    revision: number;
    title: string;
    summary: string;
    content: Record<string, unknown>;
    applicability: Record<string, unknown>;
  } | null;
};

export type MemoryActivity = {
  candidate_count: number;
  items: {
    id: string;
    kind: string;
    status: string;
    error_code: string | null;
    attempts: number;
    created_at: string;
  }[];
  action_results: {
    run_id: string;
    conversation_id: string;
    device_id: string | null;
    command_id: string | null;
    proposal_id: string | null;
    outcome: string;
    run_status: string | null;
    needs_followup: boolean;
  }[];
};

export function getMemoryActivity() {
  return request<MemoryActivity>('/memories/activity');
}

export function forgetMemorySource(conversationId: string) {
  return request<{ affected_count: number; job_id: string }>(
    '/memories/forget-source',
    {
      method: 'POST',
      body: JSON.stringify({ conversation_id: conversationId }),
    },
    true,
  );
}

export type MemoryUpdate = {
  kind?: MemoryKind;
  title: string;
  summary: string;
  content: Record<string, unknown>;
  applicability: Record<string, unknown>;
  expected_revision: number;
  change_reason?: string;
};

export async function retryMemoryJob(jobId: string) {
  return request<{ queued: boolean }>(
    `/memories/jobs/${encodeURIComponent(jobId)}/retry`,
    { method: 'POST' },
    true,
  );
}

export async function getMemory(memoryId: string) {
  return request<MemoryDetail>(`/memories/${encodeURIComponent(memoryId)}`);
}

/** 编辑生成待确认新版本；expected_revision 不符时后端返回 409 版本冲突。 */
export async function updateMemory(memoryId: string, payload: MemoryUpdate) {
  return request<MemoryDetail>(
    `/memories/${encodeURIComponent(memoryId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
    true,
  );
}

export async function listMemories(
  params: {
    kind?: MemoryKind;
    status?: string;
    q?: string;
    limit?: number;
    cursor?: string;
  } = {},
) {
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

export async function confirmMemory(
  memoryId: string,
  expectedRevision: number,
) {
  return request<MemorySummary>(
    `/memories/${encodeURIComponent(memoryId)}/confirm`,
    {
      method: 'POST',
      body: JSON.stringify({ expected_revision: expectedRevision }),
    },
    true,
  );
}

export async function rejectMemory(memoryId: string, expectedRevision: number) {
  return request<MemorySummary>(
    `/memories/${encodeURIComponent(memoryId)}/reject`,
    {
      method: 'POST',
      body: JSON.stringify({ expected_revision: expectedRevision }),
    },
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
