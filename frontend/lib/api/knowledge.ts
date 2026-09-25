import { request } from './client';

export type KnowledgeDocumentSummary = {
  document_id: string;
  source: string;
  title: string;
  device_type?: string | null;
  chunk_count: number;
  content_chars?: number;
  created_at?: string;
};

export type IngestedKnowledgeDocument = {
  source: string;
  document_id: string;
  chunk_count: number;
  mysql_saved: boolean;
  vector_indexed: boolean;
  sync_status: string;
};

export type FaultCaseSummary = {
  fault_id: string;
  device_id: string;
  device_type: string;
  fault_type: string;
  fault_name: string;
  symptoms: string[];
  cause: string;
  solution: string;
  verified_by: string;
  source: string;
  created_at: string;
};

export async function listKnowledgeDocuments() {
  return request<{
    items: KnowledgeDocumentSummary[];
    total: number;
    limit: number;
    offset: number;
  }>('/knowledge-documents');
}

export async function uploadKnowledgeDocument(
  file: File,
  options: {
    source: string;
    documentId?: string;
    title?: string;
    deviceType?: string;
  },
) {
  const form = new FormData();
  form.set('file', file);
  form.set('source', options.source);
  if (options.documentId) form.set('document_id', options.documentId);
  if (options.title) form.set('title', options.title);
  if (options.deviceType) form.set('device_type', options.deviceType);
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
    mysql_saved: boolean;
    vector_deleted: boolean;
    sync_status: string;
    trace_id: string | null;
  }>(
    `/knowledge-documents/${encodeURIComponent(source)}/${encodeURIComponent(documentId)}`,
    { method: 'DELETE' },
    true,
  );
}

export async function listFaultCases(params?: {
  deviceType?: string;
  limit?: number;
  offset?: number;
}) {
  const search = new URLSearchParams();
  if (params?.deviceType) search.set('device_type', params.deviceType);
  if (params?.limit != null) search.set('limit', String(params.limit));
  if (params?.offset != null) search.set('offset', String(params.offset));
  const query = search.toString();
  return request<{
    items: FaultCaseSummary[];
    total: number;
    limit: number;
    offset: number;
  }>(`/fault-cases${query ? `?${query}` : ''}`);
}

export async function deleteFaultCase(faultId: string) {
  return request<{
    fault_id: string;
    deleted: boolean;
    mysql_saved: boolean;
    vector_deleted: boolean;
    sync_status: string;
    trace_id: string | null;
  }>(`/fault-cases/${encodeURIComponent(faultId)}`, { method: 'DELETE' }, true);
}
