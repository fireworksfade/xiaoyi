const API_ROOT =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? '/api/backend/api/v1';

const CSRF_STORAGE_KEY = 'xiaoyi.csrf-token';

type Envelope<T> = {
  data: T;
  request_id: string;
};

type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
  };
};

export type AgentEvent = {
  id: number;
  type: string;
  data: Record<string, unknown>;
};

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ConversationMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type RepairProposal = {
  id: string;
  run_id: string | null;
  version: number;
  target: Record<string, unknown>;
  action: string;
  parameters: Record<string, unknown>;
  reason: string;
  impact: string;
  verification: Record<string, unknown>;
  status: 'pending' | 'approved' | 'rejected' | 'expired' | 'invalidated';
  expires_at: string;
  task_status?: string;
};

export type ModelConfiguration = {
  provider_name: string;
  base_url: string;
  model_name: string;
  api_mode: 'responses' | 'chat_completions';
  api_key_configured: boolean;
  api_key_hint: string | null;
  enabled: boolean;
};

export type MCPServer = {
  id: string;
  server_key: string;
  name: string;
  url: string;
  purpose: 'knowledge' | 'iot' | 'generic';
  enabled: boolean;
  connection_status: string;
  last_error: string | null;
  credential_configured: boolean;
  config_version: number;
  tools_version: number;
  tool_count: number | null;
  last_checked_at: string | null;
};

export type MCPTool = {
  id: string;
  original_name: string;
  model_alias: string;
  description: string;
  enabled: boolean;
  risk_policy: 'read_only' | 'proposal_only' | 'approval_required' | 'disabled';
};

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

function csrfToken() {
  return window.sessionStorage.getItem(CSRF_STORAGE_KEY);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  csrf = false,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  if (csrf) {
    const token = csrfToken();
    if (!token) throw new ApiError('CSRF_TOKEN_MISSING', '登录状态已失效', 401);
    headers.set('X-CSRF-Token', token);
  }

  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });
  const body = (await response.json().catch(() => ({}))) as
    | Envelope<T>
    | ApiErrorBody;

  if (!response.ok) {
    const error = 'error' in body ? body.error : undefined;
    throw new ApiError(
      error?.code ?? `HTTP_${response.status}`,
      error?.message ?? '请求失败',
      response.status,
    );
  }

  return (body as Envelope<T>).data;
}

export async function ensureDemoSession() {
  const token = csrfToken();
  if (token) {
    try {
      await request('/auth/me');
      return;
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
    }
  }

  const data = await request<{ csrf_token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username: 'admin', password: 'admin123' }),
  });
  window.sessionStorage.setItem(CSRF_STORAGE_KEY, data.csrf_token);
}

export async function createConversation(title = '新对话') {
  return request<Conversation>(
    '/conversations',
    { method: 'POST', body: JSON.stringify({ title }) },
    true,
  );
}

export async function listConversations() {
  return request<{
    items: Conversation[];
    page: number;
    page_size: number;
    total: number;
  }>('/conversations?page=1&page_size=100');
}

export async function listConversationMessages(conversationId: string) {
  return request<{ items: ConversationMessage[] }>(
    `/conversations/${conversationId}/messages`,
  );
}

export async function updateConversation(
  conversationId: string,
  title: string,
) {
  return request<Conversation>(
    `/conversations/${conversationId}`,
    { method: 'PATCH', body: JSON.stringify({ title }) },
    true,
  );
}

export async function deleteConversation(conversationId: string) {
  return request<{ deleted: boolean }>(
    `/conversations/${conversationId}`,
    { method: 'DELETE' },
    true,
  );
}

export async function submitAgentMessage(
  conversationId: string,
  content: string,
  options: {
    attachmentIds?: string[];
    toolMode?: 'auto' | 'none' | 'selected';
    mcpServerIds?: string[];
  } = {},
) {
  return request<{ run_id: string }>(
    `/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify({
        content,
        client_message_id: crypto.randomUUID(),
        attachment_ids: options.attachmentIds ?? [],
        tool_mode: options.toolMode ?? 'auto',
        mcp_server_ids: options.mcpServerIds ?? [],
      }),
    },
    true,
  );
}

export type UploadedAttachment = {
  id: string;
  filename: string;
  media_type: string;
  size_bytes: number;
};

export async function uploadAttachment(file: File) {
  const form = new FormData();
  form.set('file', file);
  return request<UploadedAttachment>(
    '/attachments',
    { method: 'POST', body: form },
    true,
  );
}

export async function listAgentToolSources() {
  return request<{
    items: Array<{
      id: string;
      server_key: string;
      name: string;
      tool_count: number;
    }>;
  }>('/agent-tools');
}

export async function streamAgentRun(
  runId: string,
  onEvent: (event: AgentEvent) => void,
) {
  const response = await fetch(`${API_ROOT}/agent-runs/${runId}/events`, {
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
      const payload = JSON.parse(rawData) as {
        id: number;
        data: Record<string, unknown>;
      };
      onEvent({ id: payload.id, type, data: payload.data });
    }

    if (done) break;
  }
}

export async function getRepairProposal(proposalId: string) {
  return request<RepairProposal>(`/repair-proposals/${proposalId}`);
}

export async function decideRepairProposal(
  proposalId: string,
  decision: 'approved' | 'rejected',
  expectedVersion: number,
) {
  return request<RepairProposal>(
    `/repair-proposals/${proposalId}/decision`,
    {
      method: 'POST',
      body: JSON.stringify({ decision, expected_version: expectedVersion }),
    },
    true,
  );
}

export async function getRepairTaskForProposal(proposalId: string) {
  const page = await request<{
    items: Array<{ id: string; proposal_id: string; status: string }>;
  }>('/repair-tasks?page=1&page_size=100');
  const task = page.items.find((item) => item.proposal_id === proposalId);
  if (!task) return null;
  return request<{ id: string; proposal_id: string; status: string }>(
    `/repair-tasks/${task.id}`,
  );
}

export async function getModelConfiguration() {
  return request<ModelConfiguration>('/model-config');
}

export async function saveModelConfiguration(payload: {
  provider_name: string;
  base_url: string;
  model_name: string;
  api_mode: ModelConfiguration['api_mode'];
  api_key?: string;
  clear_api_key?: boolean;
  enabled: boolean;
}) {
  return request<ModelConfiguration>(
    '/model-config',
    { method: 'PUT', body: JSON.stringify(payload) },
    true,
  );
}

export async function testModelConfiguration() {
  return request<{
    connected: boolean;
    model_available: boolean;
    model_name: string;
  }>('/model-config/test', { method: 'POST' }, true);
}

export async function listMCPServers() {
  return request<{ items: MCPServer[]; total: number }>(
    '/mcp-servers?page=1&page_size=100',
  );
}

export async function createMCPServer(payload: {
  server_key: string;
  name: string;
  url: string;
  purpose: MCPServer['purpose'];
  credential?: string;
}) {
  return request<MCPServer>(
    '/mcp-servers',
    { method: 'POST', body: JSON.stringify(payload) },
    true,
  );
}

export async function updateMCPServer(
  serverId: string,
  payload: Partial<
    Pick<MCPServer, 'name' | 'url' | 'purpose' | 'enabled'> & {
      credential: string;
    }
  >,
) {
  return request<MCPServer>(
    `/mcp-servers/${serverId}`,
    { method: 'PATCH', body: JSON.stringify(payload) },
    true,
  );
}

export async function testMCPServer(serverId: string) {
  return request<{ connected: boolean; tool_count: number }>(
    `/mcp-servers/${serverId}/test`,
    { method: 'POST' },
    true,
  );
}

export async function refreshMCPTools(serverId: string) {
  return request<{ items: MCPTool[]; tools_version: number }>(
    `/mcp-servers/${serverId}/refresh-tools`,
    { method: 'POST' },
    true,
  );
}

export async function listMCPTools(serverId: string) {
  return request<{ items: MCPTool[] }>(`/mcp-servers/${serverId}/tools`);
}

export async function updateMCPTool(
  serverId: string,
  toolId: string,
  payload: Pick<MCPTool, 'enabled' | 'risk_policy'>,
) {
  return request<MCPTool>(
    `/mcp-servers/${serverId}/tools/${toolId}`,
    { method: 'PATCH', body: JSON.stringify(payload) },
    true,
  );
}

export async function deleteMCPServer(serverId: string) {
  return request<{ deleted: boolean }>(
    `/mcp-servers/${serverId}`,
    { method: 'DELETE' },
    true,
  );
}
