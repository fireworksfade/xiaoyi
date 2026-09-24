'use client';

import { useEffect, useState } from 'react';
import { Loader2, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import {
  deleteAgentRun,
  getAgentRunWorkflow,
  listAgentRuns,
  type AgentRunSummary,
  type OperationWorkflow,
} from '@/lib/api';
import { formatApiDateTime } from '@/lib/datetime';

const STEP_LABELS: Record<string, string> = {
  diagnose: '诊断',
  select_action: '选择动作',
  approve: '审批',
  remediate: '执行修复',
  verify: '恢复验证',
  archive_case: '案例归档',
};

const WORKFLOW_STATUS_LABELS: Record<string, string> = {
  active: '进行中',
  waiting_approval: '等待审批',
  waiting_verification: '等待恢复验证',
  completed: '已完成',
  failed: '修复失败',
  cancelled: '已取消',
};

const WORKFLOW_OUTCOME_LABELS: Record<string, string> = {
  diagnosed: '诊断完成',
  awaiting_approval: '等待审批',
  remediated_verified: '恢复已验证',
  remediated_verified_archive_pending: '恢复已验证，案例归档中',
  remediation_failed: '修复或验证失败',
  cancelled: '未执行修复',
};

const STEP_STATUS_LABELS: Record<string, string> = {
  pending: '待开始',
  running: '执行中',
  waiting: '等待中',
  completed: '已完成',
  skipped: '已跳过',
  failed: '失败',
};

const STATUS_VARIANTS: Record<
  AgentRunSummary['status'],
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  completed: 'secondary',
  running: 'default',
  queued: 'outline',
  failed: 'destructive',
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
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [workflows, setWorkflows] = useState<
    Record<string, OperationWorkflow | null>
  >({});

  useEffect(() => {
    if (!props.open) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const page = await listAgentRuns({ pageSize: 50 });
        const workflowEntries = await Promise.all(
          page.items.map(
            async (run) => [run.id, await getAgentRunWorkflow(run.id)] as const,
          ),
        );
        if (!cancelled) {
          setRuns(page.items);
          setWorkflows(Object.fromEntries(workflowEntries));
        }
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

  async function removeRun(run: AgentRunSummary) {
    if (!window.confirm('确定删除这条运行记录吗？对话消息不会被删除。')) return;
    setDeletingRunId(run.id);
    setError(null);
    try {
      await deleteAgentRun(run.id);
      setRuns((current) => current.filter((item) => item.id !== run.id));
      setWorkflows((current) => {
        const next = { ...current };
        delete next[run.id];
        return next;
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '运行记录删除失败');
    } finally {
      setDeletingRunId(null);
    }
  }

  return (
    <Sheet open={props.open} onOpenChange={props.onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>运行记录</SheetTitle>
          <SheetDescription>
            最近的 Agent 运行及其状态与错误信息；已完成或失败的记录可删除。
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
              {runs.map((run) => {
                const workflow = workflows[run.id];
                const terminal = [
                  'completed',
                  'failed',
                  'COMPLETED',
                  'FAILED',
                ].includes(run.status);
                return (
                  <li
                    key={run.id}
                    className="rounded-md border border-slate-200 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <Badge
                          variant={
                            run.error?.code === 'RUN_STOPPED'
                              ? 'outline'
                              : (STATUS_VARIANTS[run.status] ?? 'outline')
                          }
                        >
                          {run.error?.code === 'RUN_STOPPED'
                            ? '已停止'
                            : run.status}
                        </Badge>
                        <span className="truncate text-xs text-slate-400">
                          {formatApiDateTime(run.created_at)}
                        </span>
                      </div>
                      {terminal ? (
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          aria-label="删除运行记录"
                          title="删除运行记录"
                          disabled={deletingRunId === run.id}
                          onClick={() => void removeRun(run)}
                        >
                          <Trash2 />
                          删除
                        </Button>
                      ) : null}
                    </div>
                    <p className="mt-1 truncate font-mono text-xs text-slate-500">
                      run {run.id.slice(0, 8)} · 会话{' '}
                      {run.conversation_id.slice(0, 8)}
                    </p>
                    {run.error ? (
                      <p
                        className={`mt-1 text-xs ${run.error.code === 'RUN_STOPPED' ? 'text-slate-500' : 'text-red-600'}`}
                      >
                        {run.error.code}: {run.error.message}
                      </p>
                    ) : null}
                    {workflow ? (
                      <div className="mt-2 border-t border-slate-100 pt-2">
                        <p className="text-xs text-slate-500">
                          {workflow.device_id ?? 'IoT'} ·{' '}
                          {WORKFLOW_STATUS_LABELS[workflow.status] ??
                            workflow.status}
                          {workflow.outcome
                            ? ` · ${WORKFLOW_OUTCOME_LABELS[workflow.outcome] ?? workflow.outcome}`
                            : ''}
                        </p>
                        <ol className="mt-1 grid grid-cols-3 gap-1">
                          {workflow.steps.map((step) => (
                            <li
                              key={step.step_key}
                              className={`rounded px-1.5 py-1 text-[10px] ${
                                step.status === 'failed'
                                  ? 'bg-red-50 text-red-700'
                                  : step.status === 'completed'
                                    ? 'bg-emerald-50 text-emerald-700'
                                    : step.status === 'waiting' ||
                                        step.status === 'running'
                                      ? 'bg-amber-50 text-amber-700'
                                      : 'bg-slate-50 text-slate-400'
                              }`}
                            >
                              {STEP_LABELS[step.step_key] ?? step.step_key}
                              <span className="block">
                                {STEP_STATUS_LABELS[step.status] ?? step.status}
                              </span>
                            </li>
                          ))}
                        </ol>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
