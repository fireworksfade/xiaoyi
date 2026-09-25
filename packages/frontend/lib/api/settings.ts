import { request } from './client';

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
