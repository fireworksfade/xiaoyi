'use client';

import { useEffect, useState } from 'react';
import { Check, Loader2, Pencil, Trash2, X } from 'lucide-react';

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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  ApiError,
  confirmMemory,
  deleteMemory,
  ensureDemoSession,
  getMemory,
  getMemoryActivity,
  forgetMemorySource,
  listMemories,
  rejectMemory,
  updateMemory,
  retryMemoryJob,
  type MemorySummary,
  type MemoryDetail,
  type MemoryActivity,
} from '@/lib/api/index';
import { MemoryContent } from './memory-content';

const STATUS_LABELS: Record<string, string> = {
  candidate: '待确认',
  active: '已启用',
  suspended: '已暂停',
  archived: '已归档',
  rejected: '已拒绝',
};

const KIND_LABELS: Record<string, string> = {
  episodic: '情景',
  experience: '经验',
};

function describeError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    const known: Record<string, string> = {
      MEMORY_VERSION_CONFLICT: '内容已更新，请刷新后重试',
      MEMORY_NOT_FOUND: '记忆不存在或已被删除',
    };
    return known[error.code] ?? error.message;
  }
  return error instanceof Error ? error.message : fallback;
}

type EditDraft = {
  memoryId: string;
  kind: 'episodic' | 'experience';
  title: string;
  summary: string;
  contentText: string;
  applicabilityText: string;
  expectedRevision: number;
  wasActive: boolean;
};

export function MemoryDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onFollowup?: (prompt: string) => void;
}) {
  const [items, setItems] = useState<MemorySummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [kind, setKind] = useState<string>('all');
  const [status, setStatus] = useState<string>('all');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<EditDraft | null>(null);
  const [details, setDetails] = useState<Record<string, MemoryDetail>>({});
  const [activity, setActivity] = useState<MemoryActivity | null>(null);

  useEffect(() => {
    if (!props.open) return;
    let cancelled = false;
    const load = async () => {
      try {
        await ensureDemoSession();
        const result = await getMemoryActivity();
        if (!cancelled) setActivity(result);
      } catch {
        /* List and review remain available during an activity outage. */
      }
    };
    void load();
    const timer = setInterval(() => void load(), 10000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [props.open]);

  async function expand(memory: MemorySummary) {
    setExpandedId(memory.id);
    try {
      const detail = await getMemory(memory.id);
      setDetails((previous) => ({ ...previous, [memory.id]: detail }));
    } catch (cause) {
      setError(describeError(cause, '记忆详情加载失败'));
    }
  }

  async function forgetSource(conversationId: string) {
    setError(null);
    try {
      const result = await forgetMemorySource(conversationId);
      setNotice(`已清除来源，${result.affected_count} 条相关记忆已停止使用。`);
      setDetails({});
      await refresh();
    } catch (cause) {
      setError(describeError(cause, '清除来源失败'));
    }
  }

  async function refresh() {
    await ensureDemoSession();
    const page = await listMemories({
      kind: kind === 'all' ? undefined : (kind as 'episodic' | 'experience'),
      status: status === 'all' ? undefined : status,
      limit: 100,
    });
    setItems(page.items);
    setError(null);
  }

  useEffect(() => {
    if (!props.open) return;
    let cancelled = false;
    async function loadList() {
      setDetails({});
      setExpandedId(null);
      setDraft(null);
      setNotice(null);
      setLoading(true);
      try {
        await ensureDemoSession();
        const page = await listMemories({
          kind:
            kind === 'all' ? undefined : (kind as 'episodic' | 'experience'),
          status: status === 'all' ? undefined : status,
          limit: 100,
        });
        if (!cancelled) {
          setItems(page.items);
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) setError(describeError(cause, '记忆列表加载失败'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadList();
    return () => {
      cancelled = true;
    };
  }, [props.open, kind, status]);

  async function act(
    memory: MemorySummary,
    action: 'confirm' | 'reject' | 'delete',
  ) {
    setBusyId(memory.id);
    setError(null);
    try {
      await ensureDemoSession();
      if (action === 'delete') {
        await deleteMemory(memory.id);
      } else {
        const detail = details[memory.id];
        if (action === 'confirm' && (!detail || expandedId !== memory.id)) {
          await expand(memory);
          setNotice('请查看具体内容及版本差异，再确认启用。');
          return;
        }
        const revision = detail?.current_revision ?? memory.current_revision;
        if (action === 'confirm') await confirmMemory(memory.id, revision);
        else await rejectMemory(memory.id, revision);
      }
      setDetails((previous) => {
        const next = { ...previous };
        delete next[memory.id];
        return next;
      });
      await refresh();
    } catch (cause) {
      setError(describeError(cause, '操作失败'));
    } finally {
      setBusyId(null);
    }
  }

  async function startEdit(memory: MemorySummary) {
    setBusyId(memory.id);
    setError(null);
    setNotice(null);
    try {
      await ensureDemoSession();
      const detail = await getMemory(memory.id);
      setDetails((previous) => ({ ...previous, [memory.id]: detail }));
      setDraft({
        memoryId: memory.id,
        kind: memory.kind,
        title: detail.title,
        summary: detail.summary,
        contentText: JSON.stringify(detail.content ?? {}, null, 2),
        applicabilityText: JSON.stringify(detail.applicability ?? {}, null, 2),
        expectedRevision: detail.current_revision,
        wasActive: detail.status === 'active',
      });
      setExpandedId(memory.id);
    } catch (cause) {
      setError(describeError(cause, '记忆详情加载失败'));
    } finally {
      setBusyId(null);
    }
  }

  async function saveEdit() {
    if (!draft) return;
    let content: Record<string, unknown>;
    let applicability: Record<string, unknown>;
    try {
      content = JSON.parse(draft.contentText) as Record<string, unknown>;
      applicability = JSON.parse(draft.applicabilityText) as Record<
        string,
        unknown
      >;
    } catch {
      setError('内容必须是合法 JSON');
      return;
    }
    setBusyId(draft.memoryId);
    setError(null);
    try {
      await ensureDemoSession();
      const updated = await updateMemory(draft.memoryId, {
        kind: draft.kind,
        title: draft.title,
        summary: draft.summary,
        content,
        applicability,
        expected_revision: draft.expectedRevision,
      });
      setDetails((previous) => ({ ...previous, [draft.memoryId]: updated }));
      // 编辑已启用记忆：新版本待确认，旧版本继续参与召回（spec §6.3/§10.3）。
      setNotice(
        draft.wasActive
          ? '已生成待确认新版本；旧版本仍在正常召回中使用。'
          : '已保存为新版本，待确认后生效。',
      );
      setDraft(null);
      await refresh();
    } catch (cause) {
      setError(describeError(cause, '保存失败'));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>记忆</DialogTitle>
          <DialogDescription>
            情景记录一次具体经历；经验是可复用的认识与步骤。经验确认后才会用于后续召回，
            历史记忆仅供参考，不覆盖当前指令与实时证据。
          </DialogDescription>
        </DialogHeader>
        {activity ? (
          <section
            aria-label="记忆活动"
            className="mt-3 space-y-2 rounded-md bg-slate-50 p-3 text-xs"
          >
            <p>待审核经验：{activity.candidate_count}</p>
            {activity.items
              .filter((job) => job.status === 'failed')
              .map((job) => (
                <p key={job.id} className="text-amber-700">
                  记忆处理失败：{job.error_code ?? '需检查后台处理状态'}
                  。设备修复结果单独保留。
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void (async () => {
                        try {
                          await retryMemoryJob(job.id);
                          setActivity(await getMemoryActivity());
                        } catch (cause) {
                          setError(describeError(cause, '重试记忆处理失败'));
                        }
                      })()
                    }
                  >
                    重试记忆处理
                  </Button>
                </p>
              ))}
            {activity.action_results
              .filter((result) => result.needs_followup)
              .map((result) => (
                <p
                  key={`${result.run_id}-${result.command_id ?? result.proposal_id}`}
                >
                  {result.device_id ?? '设备'}{' '}
                  的修复失败；任务已结束，需要发起后续诊断。
                  {props.onFollowup ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        props.onOpenChange(false);
                        props.onFollowup?.(
                          `请对 ${result.device_id ?? '该设备'} 发起后续诊断，核实命令 ${result.command_id ?? result.proposal_id ?? ''} 失败后的实时状态与日志，再决定下一步。`,
                        );
                      }}
                    >
                      发起后续诊断
                    </Button>
                  ) : null}
                </p>
              ))}
          </section>
        ) : null}

        <div className="mt-2 flex gap-2">
          <Select
            value={kind}
            onValueChange={(value) => setKind(String(value ?? 'all'))}
          >
            <SelectTrigger className="w-32" aria-label="记忆类型">
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="start">
              <SelectItem value="all">全部类型</SelectItem>
              <SelectItem value="episodic">情景</SelectItem>
              <SelectItem value="experience">经验</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={status}
            onValueChange={(value) => setStatus(String(value ?? 'all'))}
          >
            <SelectTrigger className="w-32" aria-label="记忆状态">
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="start">
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="candidate">待确认</SelectItem>
              <SelectItem value="active">已启用</SelectItem>
              <SelectItem value="suspended">已暂停</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="mt-3 max-h-96 overflow-y-auto rounded-md border border-slate-200">
          {loading ? (
            <p className="flex items-center gap-2 px-3 py-4 text-sm text-slate-500">
              <Loader2 className="size-4 animate-spin" />
              正在读取记忆…
            </p>
          ) : items.length === 0 ? (
            <p className="px-3 py-4 text-sm text-slate-500">
              还没有记忆。有效诊断与修复经历会由后台自动记录。
            </p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {items.map((item) => {
                const expanded = expandedId === item.id;
                const detail = details[item.id] ?? (item as MemoryDetail);
                const editable =
                  item.status === 'candidate' ||
                  item.status === 'active' ||
                  item.status === 'suspended';
                const hasPendingRevision =
                  item.status === 'active' &&
                  item.current_revision > (item.active_revision ?? 0);
                const editing = draft?.memoryId === item.id;
                return (
                  <li key={item.id} className="px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        onClick={() =>
                          expanded ? setExpandedId(null) : void expand(item)
                        }
                      >
                        <p className="flex items-center gap-2 font-medium text-slate-700">
                          <span className="truncate">{item.title}</span>
                          <Badge
                            variant="outline"
                            className="shrink-0 text-[10px]"
                          >
                            {KIND_LABELS[item.kind] ?? item.kind}
                          </Badge>
                          <Badge
                            variant={
                              item.status === 'candidate'
                                ? 'secondary'
                                : 'default'
                            }
                            className="shrink-0 text-[10px]"
                          >
                            {STATUS_LABELS[item.status] ?? item.status}
                          </Badge>
                        </p>
                        <p className="mt-0.5 truncate text-xs text-slate-400">
                          {item.summary}
                        </p>
                      </button>
                      <span className="flex shrink-0 items-center gap-1">
                        {(item.status === 'candidate' ||
                          hasPendingRevision ||
                          item.status === 'suspended') &&
                        detail.review_state !== 'rejected' ? (
                          <>
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              className="size-7 text-emerald-600"
                              aria-label={`确认 ${item.title}`}
                              disabled={busyId === item.id}
                              onClick={() => void act(item, 'confirm')}
                            >
                              <Check />
                            </Button>
                            {item.active_revision !== item.current_revision ? (
                              <Button
                                type="button"
                                size="icon"
                                variant="ghost"
                                className="size-7 text-slate-400 hover:text-red-600"
                                aria-label={`拒绝 ${item.title}`}
                                disabled={busyId === item.id}
                                onClick={() => void act(item, 'reject')}
                              >
                                <X />
                              </Button>
                            ) : null}
                          </>
                        ) : null}
                        {editable ? (
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            className="size-7 text-slate-400 hover:text-slate-700"
                            aria-label={`编辑 ${item.title}`}
                            disabled={busyId === item.id}
                            onClick={() => void startEdit(item)}
                          >
                            <Pencil />
                          </Button>
                        ) : null}
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          className="size-7 text-slate-400 hover:text-red-600"
                          aria-label={`删除 ${item.title}`}
                          disabled={busyId === item.id}
                          onClick={() => void act(item, 'delete')}
                        >
                          <Trash2 />
                        </Button>
                      </span>
                    </div>
                    {editing && draft ? (
                      <form
                        className="mt-2 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3"
                        onSubmit={(event) => {
                          event.preventDefault();
                          void saveEdit();
                        }}
                      >
                        <Input
                          aria-label="标题"
                          value={draft.title}
                          maxLength={160}
                          onChange={(event) =>
                            setDraft({ ...draft, title: event.target.value })
                          }
                        />
                        <Input
                          aria-label="摘要"
                          value={draft.summary}
                          maxLength={1200}
                          onChange={(event) =>
                            setDraft({ ...draft, summary: event.target.value })
                          }
                        />
                        <textarea
                          aria-label="内容 JSON"
                          className="w-full rounded-md border border-slate-300 bg-white p-2 font-mono text-xs"
                          rows={8}
                          value={draft.contentText}
                          onChange={(event) =>
                            setDraft({
                              ...draft,
                              contentText: event.target.value,
                            })
                          }
                        />
                        <textarea
                          aria-label="适用条件 JSON"
                          className="w-full rounded-md border border-slate-300 bg-white p-2 font-mono text-xs"
                          rows={3}
                          value={draft.applicabilityText}
                          onChange={(event) =>
                            setDraft({
                              ...draft,
                              applicabilityText: event.target.value,
                            })
                          }
                        />
                        <div className="flex items-center gap-2">
                          <Button
                            type="submit"
                            size="sm"
                            disabled={busyId === item.id}
                          >
                            保存新版本
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={() => setDraft(null)}
                          >
                            取消
                          </Button>
                          <span className="text-xs text-slate-400">
                            保存会生成待确认新版本（版本{' '}
                            {draft.expectedRevision} →{' '}
                            {draft.expectedRevision + 1}）。
                          </span>
                        </div>
                      </form>
                    ) : null}
                    {expanded ? (
                      <dl className="mt-1 space-y-1 border-t border-slate-100 pt-2 pl-6 text-xs text-slate-600">
                        <div>
                          <dt className="inline text-slate-400">摘要：</dt>
                          <dd className="inline">{item.summary}</dd>
                        </div>
                        <div>
                          <dt className="inline text-slate-400">索引状态：</dt>
                          <dd className="inline">{item.index_status}</dd>
                        </div>
                        {hasPendingRevision ? (
                          <div className="text-amber-600">
                            有新版本待确认；旧版本（v{item.active_revision}
                            ）仍在正常召回中使用。
                          </div>
                        ) : null}
                        <div>
                          当前审核版本：v{detail.current_revision}；
                          {item.status === 'active'
                            ? `正在使用 v${item.active_revision}`
                            : '当前停止召回'}
                        </div>
                        <MemoryContent
                          content={detail.content ?? {}}
                          applicability={detail.applicability ?? {}}
                        />
                        {detail.active_version ? (
                          <div className="rounded border border-amber-200 p-2">
                            <p className="font-medium">
                              旧版 v{detail.active_version.revision} 与当前 v
                              {detail.current_revision} 对照
                            </p>
                            <p>旧摘要：{detail.active_version.summary}</p>
                            <p>新摘要：{detail.summary}</p>
                            <p className="mt-2 font-medium">旧版内容与条件</p>
                            <MemoryContent
                              content={detail.active_version.content}
                              applicability={
                                detail.active_version.applicability
                              }
                            />
                          </div>
                        ) : null}
                        <div>
                          <dt className="font-medium">来源依据</dt>
                          <dd>
                            {detail.sources?.length
                              ? detail.sources.map((source) => (
                                  <div
                                    key={source.id}
                                    className="mt-1 rounded border p-2"
                                  >
                                    <p>
                                      {source.command_id ??
                                        source.diagnosis_id ??
                                        source.id}
                                    </p>
                                    <p>
                                      {source.access_state === 'available'
                                        ? '来源可用'
                                        : '来源正文已不可用'}
                                    </p>
                                    <p className="break-all">
                                      内容校验：{source.content_hash}
                                    </p>
                                    <pre className="whitespace-pre-wrap">
                                      {JSON.stringify(source.excerpt, null, 2)}
                                    </pre>
                                    {source.access_state ===
                                      'conversation_deleted' &&
                                    source.conversation_id ? (
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() =>
                                          void forgetSource(
                                            source.conversation_id!,
                                          )
                                        }
                                      >
                                        清除已删除聊天的记忆
                                      </Button>
                                    ) : null}
                                  </div>
                                ))
                              : '用户提供或来源已撤回'}
                          </dd>
                        </div>
                      </dl>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        {notice ? (
          <p className="mt-3 text-sm text-emerald-700">{notice}</p>
        ) : null}
        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
      </DialogContent>
    </Dialog>
  );
}
