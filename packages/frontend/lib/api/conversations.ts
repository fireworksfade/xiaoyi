import { request } from './client';

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

export type MessagePage = {
  items: ConversationMessage[];
  next_cursor: string | null;
  has_more: boolean;
};

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

export async function listConversationMessages(
  conversationId: string,
  options: { limit?: number; before?: string } = {},
) {
  // 游标分页：默认返回最近一页；before 读取更早消息（WP-10 §9.2）
  const params = new URLSearchParams();
  if (options.limit != null) params.set('limit', String(options.limit));
  if (options.before) params.set('before', options.before);
  const query = params.toString();
  return request<MessagePage>(
    `/conversations/${conversationId}/messages${query ? `?${query}` : ''}`,
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

/** 删除未绑定到消息的附件（发送失败后的显式清理；WP-11 §9.3） */
export async function deleteAttachment(attachmentId: string) {
  return request<{ id: string; deleted: boolean }>(
    `/attachments/${encodeURIComponent(attachmentId)}`,
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
