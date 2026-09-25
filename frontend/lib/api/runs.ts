import { request, API_BASE_URL, ApiError } from './client';

export type AgentEvent = {
  id: number;
  type: string;
  data: Record<string, unknown>;
};

export type AgentRunSummary = {
  id: string;
  conversation_id: string;
  status:
    | 'queued'
    | 'running'
    | 'completed'
    | 'failed'
    | 'QUEUED'
    | 'RUNNING'
    | 'COMPLETED'
    | 'FAILED';
  final_message_id: string | null;
  error: { code: string; message: string; retryable: boolean } | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowStep = {
  step_key:
    | 'diagnose'
    | 'select_action'
    | 'approve'
    | 'remediate'
    | 'verify'
    | 'archive_case';
  sequence: number;
  status:
    | 'pending'
    | 'running'
    | 'waiting'
    | 'completed'
    | 'skipped'
    | 'failed';
  evidence: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
};

export type OperationWorkflow = {
  id: string;
  agent_run_id: string;
  goal: 'diagnosis' | 'remediation';
  status:
    | 'active'
    | 'waiting_approval'
    | 'waiting_verification'
    | 'completed'
    | 'failed'
    | 'cancelled';
  outcome: string | null;
  current_step: WorkflowStep['step_key'];
  device_id: string | null;
  diagnosis_id: string | null;
  proposal_id: string | null;
  command_id: string | null;
  case_id: string | null;
  steps: WorkflowStep[];
};

export type ToolSource = {
  id: string;
  server_key: string;
  name: string;
  tool_count: number;
};

export async function listAgentToolSources() {
  return request<{ items: ToolSource[] }>('/agent-tools');
}

export async function getAgentRunWorkflow(runId: string) {
  return request<OperationWorkflow | null>(
    `/agent-runs/${encodeURIComponent(runId)}/workflow`,
  );
}

export async function listAgentRuns(
  options: { page?: number; pageSize?: number } = {},
) {
  const params = new URLSearchParams({
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 20),
  });
  return request<{
    items: AgentRunSummary[];
    page: number;
    page_size: number;
    total: number;
  }>(`/agent-runs?${params.toString()}`);
}

export async function deleteAgentRun(runId: string) {
  return request<{ deleted: boolean; run_id: string }>(
    `/agent-runs/${encodeURIComponent(runId)}`,
    { method: 'DELETE' },
    true,
  );
}

export async function stopAgentRun(runId: string) {
  return request<{ run_id: string; stopped: boolean }>(
    `/agent-runs/${encodeURIComponent(runId)}/stop`,
    { method: 'POST' },
    true,
  );
}

export async function streamAgentRun(
  runId: string,
  onEvent: (event: AgentEvent) => void,
) {
  const response = await fetch(`${API_BASE_URL}/agent-runs/${runId}/events`, {
    credentials: 'include',
    headers: { Accept: 'text/event-stream' },
  });
  if (!response.ok || !response.body) {
    throw new ApiError(
      'EVENT_STREAM_FAILED',
      '无法连接运行事件流',
      response.status,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n');
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';

    for (const block of blocks) {
      if (!block || block.startsWith(':')) continue;
      let type = 'message';
      let rawData = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) type = line.slice(6).trim();
        if (line.startsWith('data:')) rawData += line.slice(5).trim();
      }
      if (!rawData) continue;
      let payload: { id: number; data: Record<string, unknown> };
      try {
        payload = JSON.parse(rawData) as {
          id: number;
          data: Record<string, unknown>;
        };
      } catch {
        // 无效事件跳过，不中断整条事件流；运行状态由轮询兜底恢复。
        continue;
      }
      onEvent({ id: payload.id, type, data: payload.data });
    }

    if (done) break;
  }
}
