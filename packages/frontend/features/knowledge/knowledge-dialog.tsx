'use client';

import { type SyntheticEvent, useEffect, useMemo, useState } from 'react';
import { ChevronDown, Loader2, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
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
} from '@/lib/api/index';

import {
  CATEGORIES,
  DOCUMENT_TYPES,
  documentCategory,
  documentTypeLabel,
} from './taxonomy';

type UploadForm = {
  category: string;
  documentId: string;
  title: string;
  deviceType: string;
  documentType: string;
  hardwareVersion: string;
  firmwareVersion: string;
};

function TagSelect(props: {
  id: string;
  label: string;
  value: string;
  options: ReadonlyArray<{ value: string; label: string }>;
  onChange: (value: string) => void;
  disabled?: boolean;
}) {
  return (
    <div>
      <label htmlFor={props.id} className="text-sm font-medium text-slate-700">
        {props.label}
      </label>
      <Select
        value={props.value}
        onValueChange={(value) => props.onChange(String(value ?? ''))}
        disabled={props.disabled}
      >
        <SelectTrigger id={props.id} className="mt-1.5 w-full">
          <SelectValue>
            {
              props.options.find((option) => option.value === props.value)
                ?.label
            }
          </SelectValue>
        </SelectTrigger>
        <SelectContent align="start">
          {props.options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

async function loadDocuments() {
  const items: KnowledgeDocumentSummary[] = [];
  let page;
  do {
    page = await listKnowledgeDocuments({ limit: 200, offset: items.length });
    items.push(...page.items);
  } while (page.items.length > 0 && items.length < page.total);
  return items;
}

function describeError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    const known: Record<string, string> = {
      KNOWLEDGE_TEXT_TOO_LARGE: '文本超过 20 万字符上限，请拆分后上传',
      KNOWLEDGE_TYPE_NOT_ALLOWED: '仅支持 TXT / Markdown / PDF',
      KNOWLEDGE_INGEST_TOOL_NOT_APPROVED: '摄取工具未在 MCP 服务上启用',
      KNOWLEDGE_TOOL_NOT_ENABLED: '所需工具未在 MCP 服务上启用',
      MCP_UNAVAILABLE: '诊断 MCP 服务暂不可用',
    };
    return known[error.code] ?? error.message;
  }
  return error instanceof Error ? error.message : fallback;
}

export function KnowledgeDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [docs, setDocs] = useState<KnowledgeDocumentSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    new Set([...CATEGORIES.map((category) => category.value), 'other']),
  );
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [search, setSearch] = useState('');
  const [form, setForm] = useState<UploadForm>({
    category: 'hardware',
    documentId: '',
    title: '',
    deviceType: '',
    documentType: 'unspecified',
    hardwareVersion: '',
    firmwareVersion: '',
  });

  const filteredDocs = useMemo(
    () =>
      docs.filter((doc) => {
        const haystack = [doc.title, doc.document_id, doc.device_type]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        return haystack.includes(search.trim().toLowerCase());
      }),
    [docs, search],
  );

  const groups = useMemo(() => {
    const known = CATEGORIES.map((category) => ({
      ...category,
      items: filteredDocs.filter(
        (doc) => documentCategory(doc) === category.value,
      ),
    }));
    const other = filteredDocs.filter(
      (doc) =>
        !CATEGORIES.some(
          (category) => category.value === documentCategory(doc),
        ),
    );
    return [
      ...known,
      { value: 'other', label: '其他资料', source: '', items: other },
    ].filter((group) => group.items.length > 0);
  }, [filteredDocs]);

  function toggleGroup(source: string) {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (next.has(source)) next.delete(source);
      else next.add(source);
      return next;
    });
  }

  async function refresh() {
    setDocs(await loadDocuments());
  }

  useEffect(() => {
    if (!props.open) return;
    let cancelled = false;
    async function loadList() {
      setError(null);
      setSuccess(null);
      setDeletingId(null);
      setLoading(true);
      try {
        await ensureDemoSession();
        const items = await loadDocuments();
        if (!cancelled) setDocs(items);
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
        source: CATEGORIES.find((category) => category.value === form.category)!
          .source,
        category: form.category,
        documentId: form.documentId.trim() || undefined,
        title: form.title.trim() || undefined,
        deviceType: form.deviceType.trim() || undefined,
        documentType:
          form.documentType === 'unspecified' ? undefined : form.documentType,
        hardwareVersion: form.hardwareVersion.trim() || undefined,
        firmwareVersion: form.firmwareVersion.trim() || undefined,
      });
      setSuccess(
        `${form.title.trim() || file.name} 已加入知识库${result.vector_indexed ? '，可用于诊断检索。' : '，检索索引正在同步。'}`,
      );
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
      await deleteKnowledgeDocument(source, documentId);
      setSuccess('文档已从知识库删除。');
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
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>知识库</DialogTitle>
          <DialogDescription>
            技术资料按领域整理，可搜索标题、文档 ID 或设备型号，供诊断检索引用。
            实际任务中的案例与经验在「记忆」中管理。
          </DialogDescription>
        </DialogHeader>

        <div className="mt-4">
          <Input
            aria-label="搜索知识文档"
            placeholder="搜索标题、文档 ID 或设备型号"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <div className="my-3 flex items-center justify-between text-xs text-slate-500">
            <span>
              {filteredDocs.length === docs.length
                ? `共 ${docs.length} 篇文档`
                : `找到 ${filteredDocs.length} 篇，共 ${docs.length} 篇文档`}
            </span>
            {search ? (
              <Button variant="ghost" size="sm" onClick={() => setSearch('')}>
                清除搜索
              </Button>
            ) : null}
          </div>
          <div className="max-h-72 overflow-y-auto rounded-md border border-slate-200">
            {loading ? (
              <p className="flex items-center gap-2 px-3 py-4 text-sm text-slate-500">
                <Loader2 className="size-4 animate-spin" />
                正在读取文档列表…
              </p>
            ) : filteredDocs.length === 0 ? (
              <p className="px-3 py-4 text-sm text-slate-500">
                {docs.length
                  ? '没有匹配的文档。'
                  : '还没有知识文档，上传一份资料开始整理。'}
              </p>
            ) : (
              groups.map((group) => {
                const collapsed = collapsedGroups.has(group.value);
                return (
                  <section key={group.value}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2 text-left text-sm font-medium text-slate-700"
                      onClick={() => toggleGroup(group.value)}
                      aria-expanded={!collapsed}
                    >
                      <span className="flex items-center gap-2">
                        <ChevronDown
                          className={`size-4 text-slate-400 transition-transform ${collapsed ? '-rotate-90' : ''}`}
                        />
                        {group.label}
                      </span>
                      <span className="text-xs font-normal text-slate-400">
                        {group.items.length} 篇文档
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
                                <p className="truncate font-medium text-slate-700">
                                  {doc.title}
                                </p>
                                <div className="mt-1 flex flex-wrap gap-1">
                                  {doc.device_type ? (
                                    <Badge variant="secondary">
                                      {doc.device_type}
                                    </Badge>
                                  ) : null}
                                  {doc.document_type ? (
                                    <Badge variant="outline">
                                      {documentTypeLabel(doc.document_type)}
                                    </Badge>
                                  ) : null}
                                  {doc.hardware_version ? (
                                    <Badge variant="outline">
                                      硬件 {doc.hardware_version}
                                    </Badge>
                                  ) : null}
                                  {doc.firmware_version ? (
                                    <Badge variant="outline">
                                      固件 {doc.firmware_version}
                                    </Badge>
                                  ) : null}
                                </div>
                                <details className="mt-1 text-xs text-slate-400">
                                  <summary className="cursor-pointer">
                                    文档详情
                                  </summary>
                                  <p className="mt-1 break-all">
                                    {doc.document_id} · {doc.chunk_count} 分块
                                    {typeof doc.content_chars === 'number'
                                      ? ` · ${doc.content_chars} 字`
                                      : ''}
                                  </p>
                                </details>
                              </div>
                              {deletingId === key ? (
                                <span className="flex shrink-0 items-center gap-1">
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="destructive"
                                    className="h-7 px-2 text-xs"
                                    disabled={busy}
                                    onClick={() =>
                                      void remove(doc.source, doc.document_id)
                                    }
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

          <form onSubmit={submit} className="mt-5">
            <p className="mb-3 text-sm font-medium text-slate-700">添加文档</p>
            <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label
                  htmlFor="knowledge-file"
                  className="text-sm font-medium text-slate-700"
                >
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
              <TagSelect
                id="knowledge-category"
                label="技术领域"
                value={form.category}
                options={CATEGORIES}
                disabled={busy}
                onChange={(category) =>
                  setForm((current) => ({ ...current, category }))
                }
              />
              <TagSelect
                id="knowledge-document-type"
                label="文档类型（可选）"
                value={form.documentType}
                options={[
                  { value: 'unspecified', label: '未标注' },
                  ...DOCUMENT_TYPES,
                ]}
                disabled={busy}
                onChange={(documentType) =>
                  setForm((current) => ({ ...current, documentType }))
                }
              />
              <div>
                <label
                  htmlFor="knowledge-device-type"
                  className="text-sm font-medium text-slate-700"
                >
                  适用设备（可选）
                </label>
                <Input
                  id="knowledge-device-type"
                  className="mt-1.5"
                  placeholder="例如 ESP32、某设备型号；留空表示通用资料"
                  maxLength={120}
                  value={form.deviceType}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      deviceType: event.target.value,
                    }))
                  }
                />
              </div>
              <div>
                <label
                  htmlFor="knowledge-hardware-version"
                  className="text-sm font-medium text-slate-700"
                >
                  硬件版本（可选）
                </label>
                <Input
                  id="knowledge-hardware-version"
                  className="mt-1.5"
                  placeholder="例如 Rev. B"
                  maxLength={120}
                  value={form.hardwareVersion}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      hardwareVersion: event.target.value,
                    }))
                  }
                />
              </div>
              <div>
                <label
                  htmlFor="knowledge-firmware-version"
                  className="text-sm font-medium text-slate-700"
                >
                  固件版本（可选）
                </label>
                <Input
                  id="knowledge-firmware-version"
                  className="mt-1.5"
                  placeholder="例如 1.2.0"
                  maxLength={120}
                  value={form.firmwareVersion}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      firmwareVersion: event.target.value,
                    }))
                  }
                />
              </div>
              <div>
                <label
                  htmlFor="knowledge-document-id"
                  className="text-sm font-medium text-slate-700"
                >
                  文档 ID（可选）
                </label>
                <Input
                  id="knowledge-document-id"
                  className="mt-1.5"
                  placeholder="默认由文件名生成"
                  value={form.documentId}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      documentId: event.target.value,
                    }))
                  }
                />
              </div>
              <div>
                <label
                  htmlFor="knowledge-title"
                  className="text-sm font-medium text-slate-700"
                >
                  标题（可选）
                </label>
                <Input
                  id="knowledge-title"
                  className="mt-1.5"
                  placeholder="默认使用文件名"
                  value={form.title}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      title: event.target.value,
                    }))
                  }
                />
              </div>
            </fieldset>
            {error ? (
              <p className="mt-3 text-sm text-red-600">{error}</p>
            ) : null}
            {success ? (
              <p className="mt-3 text-sm text-emerald-700">{success}</p>
            ) : null}
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
                上传文档
              </Button>
            </DialogFooter>
          </form>
        </div>
      </DialogContent>
    </Dialog>
  );
}
