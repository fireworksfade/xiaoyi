import { request } from './client';

export type KnowledgeDocumentSummary = {
  document_id: string;
  source: string;
  title: string;
  device_type?: string | null;
  category?: string | null;
  document_type?: string | null;
  hardware_version?: string | null;
  firmware_version?: string | null;
  chunk_count: number;
  content_chars?: number;
  created_at?: string;
};

export type IngestedKnowledgeDocument = {
  source: string;
  document_id: string;
  chunk_count: number;
  vector_indexed: boolean;
  sync_status: string;
};

export async function listKnowledgeDocuments(options?: {
  limit: number;
  offset: number;
}) {
  const query = options
    ? `?limit=${options.limit}&offset=${options.offset}`
    : '';
  return request<{
    items: KnowledgeDocumentSummary[];
    total: number;
    limit: number;
    offset: number;
  }>(`/knowledge-documents${query}`);
}

export async function uploadKnowledgeDocument(
  file: File,
  options: {
    source: string;
    documentId?: string;
    title?: string;
    deviceType?: string;
    category?: string;
    documentType?: string;
    hardwareVersion?: string;
    firmwareVersion?: string;
  },
) {
  const form = new FormData();
  form.set('file', file);
  form.set('source', options.source);
  if (options.documentId) form.set('document_id', options.documentId);
  if (options.title) form.set('title', options.title);
  if (options.deviceType) form.set('device_type', options.deviceType);
  if (options.category) form.set('category', options.category);
  if (options.documentType) form.set('document_type', options.documentType);
  if (options.hardwareVersion)
    form.set('hardware_version', options.hardwareVersion);
  if (options.firmwareVersion)
    form.set('firmware_version', options.firmwareVersion);
  return request<IngestedKnowledgeDocument>(
    '/knowledge-documents',
    { method: 'POST', body: form },
    true,
  );
}

export async function deleteKnowledgeDocument(
  source: string,
  documentId: string,
) {
  return request<{
    source: string;
    document_id: string;
    deleted_chunks: number;
    vector_deleted: boolean;
    sync_status: string;
    trace_id: string | null;
  }>(
    `/knowledge-documents/${encodeURIComponent(source)}/${encodeURIComponent(documentId)}`,
    { method: 'DELETE' },
    true,
  );
}
