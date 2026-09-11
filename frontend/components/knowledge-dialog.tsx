'use client';

import { type SyntheticEvent, useEffect, useMemo, useState } from 'react';
import { ChevronDown, Loader2, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  ApiError,
  deleteKnowledgeDocument,
  ensureDemoSession,
  listKnowledgeDocuments,
  uploadKnowledgeDocument,
  type KnowledgeDocumentSummary,
} from '@/lib/api';

const SOURCE_LABELS: Record<string, string> = {
  mqtt_docs: 'MQTT 文档',
  wifi_docs: 'WiFi 文档',
  sensor_docs: '传感器文档',
  device_docs: '设备文档',
};

const SOURCE_ORDER = ['mqtt_docs', 'wifi_docs', 'sensor_docs', 'device_docs'];

type UploadForm = {
  source: string;
  documentId: string;
  title: string;
  deviceType: string;
};

export function KnowledgeDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [docs, setDocs] = useState<KnowledgeDocumentSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState<UploadForm>({
    source: 'mqtt_docs',
    documentId: '',
    title: '',
    deviceType: 'ESP32',
  });

  const groups = useMemo(() => {
    const known = SOURCE_ORDER.map((source) => ({
      source,
      items: docs.filter((doc) => doc.source === source),
    })).filter((group) => group.items.length > 0);
    const extras = docs
      .filter((doc) => !SOURCE_ORDER.includes(doc.source))
      .reduce<Array<{ source: string; items: KnowledgeDocumentSummary[] }>>((acc, doc) => {
        const existing = acc.find((group) => group.source === doc.source);
        if (existing) existing.items.push(doc);
        else acc.push({ source: doc.source, items: [doc] });
        return acc;
      }, []);
    return [...known, ...extras];
  }, [docs]);

  function toggleGroup(source: string) {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  }

  function describeError(error: unknown, fallback: string) {
    if (error instanceof ApiError) {
      const known: Record<string, string> = {
        KNOWLEDGE_TEXT_TOO_LARGE: '文本超过 20 万字符上限，请拆分后上传',
        KNOWLEDGE_TYPE_NOT_ALLOWED: '仅支持 TXT / Markdown / PDF',
        KNOWLEDGE_INGEST_TOOL_NOT_APPROVED: '摄取工具未在 MCP 服务上启用',
        MCP_UNAVAILABLE: '诊断 MCP 服务暂不可用',
      };
      return known[error.code] ?? error.message;
    }
    return error instanceof Error ? error.message : fallback;
  }

  async function refresh() {
    const page = await listKnowledgeDocuments();
    setDocs(page.items);
  }

  useEffect(() => {
    if (!props.open) return;
    let cancelled = false;
    async function loadList() {
      setError(null);
      setSuccess(null);
      setLoading(true);
      try {
        await ensureDemoSession();
        const page = await listKnowledgeDocuments();
        if (!cancelled) setDocs(page.items);
      } catch (cause) {
        if (!cancelled) setError(describeError(cause, '文档列表加载失败'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadList();
    return () => {
      cancelled = true;
    };
  }, [props.open]);

  async function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError('请选择要上传的 TXT / Markdown / PDF 文件');
      return;
    }
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await ensureDemoSession();
      const result = await uploadKnowledgeDocument(file, {
        source: form.source,
        documentId: form.documentId.trim() || undefined,
        title: form.title.trim() || undefined,
        deviceType: form.deviceType.trim() || undefined,
      });
      const parts = [
        `${result.document_id} 已入库，共 ${result.chunk_count} 个分块`,
        result.vector_indexed ? '向量索引完成' : '向量索引待同步',
        result.mysql_saved ? 'MySQL 已写入' : 'MySQL 待同步',
      ];
      setSuccess(`${parts.join('，')}（sync_status: ${result.sync_status}）`);
      setFile(null);
      await refresh();
    } catch (cause) {
      setError(describeError(cause, '文档摄取失败'));
    } finally {
      setBusy(false);
    }
  }

  async function remove(source: string, documentId: string) {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await ensureDemoSession();
      const result = await deleteKnowledgeDocument(source, documentId);
      setSuccess(
        `${documentId} 已删除（${result.deleted_chunks} 个分块，sync_status: ${result.sync_status}）`,
      );
      setDeletingId(null);
      await refresh();
    } catch (cause) {
      setError(describeError(cause, '文档删除失败'));
    } finally {
      setBusy(false);
      setDeletingId(null);
    }
  }

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        if (!busy) props.onOpenChange(open);
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>知识文档库</DialogTitle>
          <DialogDescription>
            上传 TXT / Markdown / PDF 资料到诊断知识库，文档会分块写入数据库并生成语义向量。
          </DialogDescription>
        </DialogHeader>

        <div className="mt-4 max-h-72 overflow-y-auto rounded-md border border-slate-200">
          {loading ? (
            <p className="flex items-center gap-2 px-3 py-4 text-sm text-slate-500">
              <Loader2 className="size-4 animate-spin" />
              正在读取文档列表…
            </p>
          ) : docs.length === 0 ? (
            <p className="px-3 py-4 text-sm text-slate-500">还没有已摄取的知识文档。</p>
          ) : (
            groups.map((group) => {
              const collapsed = collapsedGroups.has(group.source);
              const chunkTotal = group.items.reduce((sum, item) => sum + item.chunk_count, 0);
              return (
                <section key={group.source}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2 text-left text-sm font-medium text-slate-700"
                    onClick={() => toggleGroup(group.source)}
                  >
                    <span className="flex items-center gap-2">
                      <ChevronDown
                        className={`size-4 text-slate-400 transition-transform ${collapsed ? '' : 'rotate-180'}`}
                      />
                      {SOURCE_LABELS[group.source] ?? group.source}
                    </span>
                    <span className="text-xs font-normal text-slate-400">
                      {group.items.length} 篇 · {chunkTotal} 分块
                    </span>
                  </button>
                  {collapsed ? null : (
                    <ul className="divide-y divide-slate-100">
                      {group.items.map((doc) => {
                        const key = `${doc.source}:${doc.document_id}`;
                        return (
                          <li
                            key={key}
                            className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                          >
                            <div className="min-w-0">
                              <p className="truncate font-medium text-slate-700">{doc.title}</p>
                              <p className="text-xs text-slate-400">
                                {doc.document_id} · {doc.chunk_count} 分块
                                {typeof doc.content_chars === 'number'
                                  ? ` · ${doc.content_chars} 字`
                                  : ''}
                              </p>
                            </div>
                            {deletingId === key ? (
                              <span className="flex shrink-0 items-center gap-1">
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="destructive"
                                  className="h-7 px-2 text-xs"
                                  disabled={busy}
                                  onClick={() => void remove(doc.source, doc.document_id)}
                                >
                                  确认删除
                                </Button>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  className="h-7 px-2 text-xs"
                                  onClick={() => setDeletingId(null)}
                                >
                                  取消
                                </Button>
                              </span>
                            ) : (
                              <span className="flex shrink-0 items-center gap-2">
                                <Button
                                  type="button"
                                  size="icon"
                                  variant="ghost"
                                  className="size-7 text-slate-400 hover:text-red-600"
                                  aria-label={`删除 ${doc.title}`}
                                  disabled={busy}
                                  onClick={() => setDeletingId(key)}
                                >
                                  <Trash2 />
                                </Button>
                              </span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </section>
              );
            })
          )}
        </div>

        <form onSubmit={submit} className="mt-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label htmlFor="knowledge-file" className="text-sm font-medium text-slate-700">
                文档文件
              </label>
              <Input
                id="knowledge-file"
                type="file"
                required
                accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
                className="mt-1.5"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                key={file ? file.name : 'empty'}
              />
            </div>
            <div>
              <label htmlFor="knowledge-source" className="text-sm font-medium text-slate-700">
                资料来源
              </label>
              <Select
                value={form.source}
                onValueChange={(value) =>
                  setForm((current) => ({ ...current, source: String(value ?? 'mqtt_docs') }))
                }
              >
                <SelectTrigger id="knowledge-source" className="mt-1.5 w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent align="start">
                  <SelectItem value="mqtt_docs">MQTT 文档</SelectItem>
                  <SelectItem value="wifi_docs">WiFi 文档</SelectItem>
                  <SelectItem value="sensor_docs">传感器文档</SelectItem>
                  <SelectItem value="device_docs">设备文档</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label htmlFor="knowledge-device-type" className="text-sm font-medium text-slate-700">
                设备类型
              </label>
              <Input
                id="knowledge-device-type"
                className="mt-1.5"
                value={form.deviceType}
                onChange={(event) =>
                  setForm((current) => ({ ...current, deviceType: event.target.value }))
                }
              />
            </div>
            <div>
              <label htmlFor="knowledge-document-id" className="text-sm font-medium text-slate-700">
                文档 ID（可选）
              </label>
              <Input
                id="knowledge-document-id"
                className="mt-1.5"
                placeholder="默认由文件名生成"
                value={form.documentId}
                onChange={(event) =>
                  setForm((current) => ({ ...current, documentId: event.target.value }))
                }
              />
            </div>
            <div>
              <label htmlFor="knowledge-title" className="text-sm font-medium text-slate-700">
                标题（可选）
              </label>
              <Input
                id="knowledge-title"
                className="mt-1.5"
                placeholder="默认使用文件名"
                value={form.title}
                onChange={(event) =>
                  setForm((current) => ({ ...current, title: event.target.value }))
                }
              />
            </div>
          </div>
          {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
          {success ? <p className="mt-3 text-sm text-emerald-700">{success}</p> : null}
          <DialogFooter className="mt-5">
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => props.onOpenChange(false)}
            >
              关闭
            </Button>
            <Button type="submit" disabled={busy || !file}>
              {busy ? <Loader2 className="animate-spin" /> : null}
              上传并摄取
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
