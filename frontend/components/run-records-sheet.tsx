'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { listAgentRuns, type AgentRunSummary } from '@/lib/api';

const STATUS_VARIANTS: Record<
  AgentRunSummary['status'],
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  COMPLETED: 'secondary',
  RUNNING: 'default',
  QUEUED: 'outline',
  FAILED: 'destructive',
};

export function RunRecordsSheet(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!props.open) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const page = await listAgentRuns({ pageSize: 50 });
        if (!cancelled) setRuns(page.items);
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : '运行记录加载失败');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [props.open]);

  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>运行记录</SheetTitle>
          <SheetDescription>
            最近的 Agent 运行及其状态与错误信息。
          </SheetDescription>
        </SheetHeader>
        <div className="px-4 pb-6">
          {loading ? (
            <p className="flex items-center gap-2 py-6 text-sm text-slate-500">
              <Loader2 className="size-4 animate-spin" />
              正在读取运行记录…
            </p>
          ) : error ? (
            <p className="py-6 text-sm text-red-600">{error}</p>
          ) : runs.length === 0 ? (
            <p className="py-6 text-sm text-slate-500">还没有运行记录。</p>
          ) : (
            <ul className="space-y-2">
              {runs.map((run) => (
                <li
                  key={run.id}
                  className="rounded-md border border-slate-200 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge variant={STATUS_VARIANTS[run.status] ?? 'outline'}>
                      {run.status}
                    </Badge>
                    <span className="text-xs text-slate-400">
                      {new Date(run.created_at).toLocaleString('zh-CN')}
                    </span>
                  </div>
                  <p className="mt-1 truncate font-mono text-xs text-slate-500">
                    run {run.id.slice(0, 8)} · 会话{' '}
                    {run.conversation_id.slice(0, 8)}
                  </p>
                  {run.error ? (
                    <p className="mt-1 text-xs text-red-600">
                      {run.error.code}: {run.error.message}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
