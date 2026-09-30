import type { KnowledgeDocumentSummary } from '@/lib/api/knowledge';

export const CATEGORIES = [
  { value: 'hardware', label: '设备与硬件', source: 'device_docs' },
  { value: 'network', label: '网络与连接', source: 'wifi_docs' },
  { value: 'protocol', label: '协议与通信', source: 'mqtt_docs' },
  { value: 'software', label: '平台与软件', source: 'device_docs' },
] as const;

export const DOCUMENT_TYPES = [
  { value: 'specification', label: '规格书' },
  { value: 'manual', label: '操作指南' },
  { value: 'configuration', label: '配置指南' },
  { value: 'api', label: '接口文档' },
  { value: 'troubleshooting', label: '故障排查' },
  { value: 'release_notes', label: '版本说明' },
] as const;

const LEGACY_CATEGORIES: Record<string, string> = {
  mqtt_docs: 'protocol',
  wifi_docs: 'network',
  sensor_docs: 'hardware',
  device_docs: 'hardware',
};

export function documentCategory(doc: KnowledgeDocumentSummary) {
  return doc.category ?? LEGACY_CATEGORIES[doc.source] ?? 'other';
}

export function documentTypeLabel(value?: string | null) {
  return (
    DOCUMENT_TYPES.find((type) => type.value === value)?.label ??
    value ??
    '未标注'
  );
}
