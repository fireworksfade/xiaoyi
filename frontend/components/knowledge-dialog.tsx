'use client';

import { type SyntheticEvent, useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Loader2, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
  deleteFaultCase,
  deleteKnowledgeDocument,
  ensureDemoSession,
  listFaultCases,
  listKnowledgeDocuments,
  uploadKnowledgeDocument,
  type FaultCaseSummary,
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

function describeError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    const known: Record<string, string> = {
      KNOWLEDGE_TEXT_TOO_LARGE: '文本超过 20 万字符上限，请拆分后上传',
      KNOWLEDGE_TYPE_NOT_ALLOWED: '仅支持 TXT / Markdown / PDF',
      KNOWLEDGE_INGEST_TOOL_NOT_APPROVED: '摄取工具未在 MCP 服务上启用',
      KNOWLEDGE_TOOL_NOT_ENABLED: '所需工具未在 MCP 服务上启用',
      FAULT_CASE_DELETE_TOOL_NOT_APPROVED: '案例删除工具未在 MCP 服务上启用',
      FAULT_ID_INVALID: '案例编号无效',
      MCP_UNAVAILABLE: '诊断 MCP 服务暂不可用',
    };
    return known[error.code] ?? error.message;
  }
  return error instanceof Error ? error.message : fallback;
}

function formatTime(value: string | undefined) {
  return value ? value.slice(0, 19).replace('T', ' ') : '—';
}

function caseOrigin(item: FaultCaseSummary): { label: string; variant: 'default' | 'secondary' | 'outline' } {
  if (item.source === 'built_in') return { label: '内置案例', variant: 'outline' };
  if (item.verified_by.startsWith('auto-remediation:')) return { label: '自动沉淀', variant: 'secondary' };
  return { label: '人工确认', variant: 'default' };
}

export function KnowledgeDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [tab, setTab] = useState('docs');
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

  // 真实案例库（懒加载：首次切到该标签时拉取）
  const [cases, setCases] = useState<FaultCaseSummary[] | null>(null);
  const [caseTotal, setCaseTotal] = useState(0);
  const [caseLoading, setCaseLoading] = useState(false);
  const [caseBusy, setCaseBusy] = useState(false);
  const [deletingCaseId, setDeletingCaseId] = useState<string | null>(null);
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  const [caseError, setCaseError] = useState<string | null>(null);
  const [caseSuccess, setCaseSuccess] = useState<string | null>(null);

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

  async function refresh() {
    const page = await listKnowledgeDocuments();
    setDocs(page.items);
  }

  async function refreshCases() {
    const page = await listFaultCases({ limit: 200 });
    setCases(page.items);
    setCaseTotal(page.total);
  }

  useEffect(() => {
    if (!props.open) return;
    let cancelled = false;
    async function loadList() {
      setError(null);
      setSuccess(null);
      setCaseError(null);
      setCaseSuccess(null);
      setCases(null);
      setDeletingId(null);
      setDeletingCaseId(null);
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

  useEffect(() => {
    if (!props.open || tab !== 'cases' || cases !== null) return;
    let cancelled = false;
    async function loadCases() {
      setCaseLoading(true);
      setCaseError(null);
      try {
        await ensureDemoSession();
        const page = await listFaultCases({ limit: 200 });
        if (!cancelled) {
          setCases(page.items);
          setCaseTotal(page.total);
        }
      } catch (cause) {
        if (!cancelled) {
          setCaseError(describeError(cause, '案例列表加载失败'));
          setCases([]);
        }
      } finally {
        if (!cancelled) setCaseLoading(false);
      }
    }

    void loadCases();
    return () => {
      cancelled = true;
    };
  }, [props.open, tab, cases]);

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
      await refresh();
    } catch (cause) {
      setError(describeError(cause, '文档删除失败'));
    } finally {
      setBusy(false);
      setDeletingId(null);
    }
  }

  async function removeCase(faultId: string) {
    setCaseBusy(true);
    setCaseError(null);
    setCaseSuccess(null);
    try {
      await ensureDemoSession();
      const result = await deleteFaultCase(faultId);
      setCaseSuccess(
        `${faultId} 已删除（sync_status: ${result.sync_status}），向量与镜像已同步清理`,
      );
      await refreshCases();
    } catch (cause) {
      setCaseError(describeError(cause, '案例删除失败'));
    } finally {
      setCaseBusy(false);
      setDeletingCaseId(null);
    }
  }

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        if (!busy && !caseBusy) props.onOpenChange(open);
      }}
    >
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>知识库</DialogTitle>
          <DialogDescription>
            官方技术文档分块写入数据库并生成语义向量；真实案例库沉淀自人工确认与自动修复闭环，支持删除同步清理向量。
          </DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(value) => setTab(String(value ?? 'docs'))} className="mt-2">
          <TabsList variant="line" className="justify-start border-b border-slate-200">
            <TabsTrigger value="docs">官方技术文档</TabsTrigger>
            <TabsTrigger value="cases">真实案例库</TabsTrigger>
          </TabsList>

          <TabsContent value="docs" className="mt-4">
            <div className="max-h-72 overflow-y-auto rounded-md border border-slate-200">
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
          </TabsContent>

          <TabsContent value="cases" className="mt-4">
            <div className="max-h-96 overflow-y-auto rounded-md border border-slate-200">
              {caseLoading ? (
                <p className="flex items-center gap-2 px-3 py-4 text-sm text-slate-500">
                  <Loader2 className="size-4 animate-spin" />
                  正在读取案例列表…
                </p>
              ) : !cases || cases.length === 0 ? (
                <p className="px-3 py-4 text-sm text-slate-500">
                  案例库还是空的。修复闭环验证成功后会自动沉淀真实案例。
                </p>
              ) : (
                <>
                  <p className="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                    共 {caseTotal} 条已验证案例，按沉淀时间倒序
                  </p>
                  <ul className="divide-y divide-slate-100">
                    {cases.map((item) => {
                      const origin = caseOrigin(item);
                      const expanded = expandedCaseId === item.fault_id;
                      return (
                        <li key={item.fault_id} className="px-3 py-2 text-sm">
                          <div className="flex items-center justify-between gap-3">
                            <button
                              type="button"
                              className="min-w-0 flex-1 text-left"
                              onClick={() => setExpandedCaseId(expanded ? null : item.fault_id)}
                            >
                              <p className="flex items-center gap-2 font-medium text-slate-700">
                                <ChevronRight
                                  className={`size-4 shrink-0 text-slate-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
                                />
                                <span className="truncate">{item.fault_name}</span>
                                <Badge variant={origin.variant} className="shrink-0 text-[10px]">
                                  {origin.label}
                                </Badge>
                              </p>
                              <p className="mt-0.5 pl-6 text-xs text-slate-400">
                                {item.fault_id} · {item.device_id} · {item.fault_type} ·{' '}
                                {formatTime(item.created_at)}
                              </p>
                            </button>
                            {deletingCaseId === item.fault_id ? (
                              <span className="flex shrink-0 items-center gap-1">
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="destructive"
                                  className="h-7 px-2 text-xs"
                                  disabled={caseBusy}
                                  onClick={() => void removeCase(item.fault_id)}
                                >
                                  确认删除
                                </Button>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  className="h-7 px-2 text-xs"
                                  onClick={() => setDeletingCaseId(null)}
                                >
                                  取消
                                </Button>
                              </span>
                            ) : (
                              <Button
                                type="button"
                                size="icon"
                                variant="ghost"
                                className="size-7 shrink-0 text-slate-400 hover:text-red-600"
                                aria-label={`删除案例 ${item.fault_name}`}
                                disabled={caseBusy}
                                onClick={() => setDeletingCaseId(item.fault_id)}
                              >
                                <Trash2 />
                              </Button>
                            )}
                          </div>
                          {expanded ? (
                            <dl className="mt-1 space-y-1 border-t border-slate-100 pt-2 pl-6 text-xs text-slate-600">
                              <div>
                                <dt className="inline text-slate-400">症状：</dt>
                                <dd className="inline">{item.symptoms.join('；') || '—'}</dd>
                              </div>
                              <div>
                                <dt className="inline text-slate-400">根因：</dt>
                                <dd className="inline">{item.cause || '—'}</dd>
                              </div>
                              <div>
                                <dt className="inline text-slate-400">处置：</dt>
                                <dd className="inline">{item.solution || '—'}</dd>
                              </div>
                              <div>
                                <dt className="inline text-slate-400">验证人：</dt>
                                <dd className="inline font-mono">{item.verified_by || '—'}</dd>
                              </div>
                            </dl>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </div>
            {caseError ? <p className="mt-3 text-sm text-red-600">{caseError}</p> : null}
            {caseSuccess ? <p className="mt-3 text-sm text-emerald-700">{caseSuccess}</p> : null}
            <DialogFooter className="mt-5">
              <Button
                type="button"
                variant="outline"
                disabled={caseBusy}
                onClick={() => props.onOpenChange(false)}
              >
                关闭
              </Button>
            </DialogFooter>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
