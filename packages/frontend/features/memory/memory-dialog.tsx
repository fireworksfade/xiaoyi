'use client';

import { useEffect, useState } from 'react';
import { Check, Loader2, Trash2, X } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
  listMemories,
  rejectMemory,
  type MemorySummary,
} from '@/lib/api/index';

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

export function MemoryDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [items, setItems] = useState<MemorySummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [kind, setKind] = useState<string>('all');
  const [status, setStatus] = useState<string>('all');
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

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
        const revision = memory.active_revision ?? memory.current_revision;
        if (action === 'confirm') await confirmMemory(memory.id, revision);
        else await rejectMemory(memory.id, revision);
      }
      await refresh();
    } catch (cause) {
      setError(describeError(cause, '操作失败'));
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
                const editable = item.status === 'candidate';
                return (
                  <li key={item.id} className="px-3 py-2 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        onClick={() => setExpandedId(expanded ? null : item.id)}
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
                        {editable ? (
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
                          </>
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
                      </dl>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
      </DialogContent>
    </Dialog>
  );
}
