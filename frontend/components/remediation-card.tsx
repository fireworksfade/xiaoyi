'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  Loader2,
  ShieldAlert,
  XCircle,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  ApiError,
  decideRemediationProposal,
  getRemediationProposal,
  type RemediationProposal,
} from '@/lib/api';

const TASK_STATUS_LABEL: Record<string, string> = {
  running: '执行中',
  verifying: '恢复验证中',
  succeeded: '已恢复',
  failed: '恢复验证失败',
};

const PROPOSAL_STATUS_LABEL: Record<string, string> = {
  pending: '等待批准',
  approved: '已批准',
  rejected: '已拒绝',
  expired: '已过期',
};

function formatParameters(parameters: Record<string, unknown>) {
  const entries = Object.entries(parameters);
  if (!entries.length) return null;
  return entries.map(([key, value]) => `${key}=${String(value)}`).join('，');
}

export function RemediationCard({
  proposal: initialProposal,
}: {
  proposal: RemediationProposal;
}) {
  const [proposal, setProposal] = useState(initialProposal);
  const [lastInitial, setLastInitial] = useState(initialProposal);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const postVerifyRefreshedRef = useRef(false);

  const refresh = useCallback(async (proposalId: string) => {
    const detail = await getRemediationProposal(proposalId);
    setProposal(detail.proposal);
    setCaseId(detail.command?.case_id ?? null);
    return detail.proposal;
  }, []);

  // 外部提案数据变化（如刷新后的消息元数据）时在渲染期同步，避免级联渲染
  if (initialProposal !== lastInitial) {
    setLastInitial(initialProposal);
    setProposal(initialProposal);
  }

  // 历史消息里的提案是创建时的快照，挂载时拉取一次最新状态
  useEffect(() => {
    const timer = setTimeout(() => {
      refresh(initialProposal.proposal_id).catch(() => {
        // 状态拉取失败时保留快照展示
      });
    }, 0);
    return () => clearTimeout(timer);
  }, [initialProposal.proposal_id, refresh]);

  useEffect(() => {
    const active =
      proposal.status === 'approved' &&
      (proposal.task_status === 'running' || proposal.task_status === 'verifying');
    if (!active) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await refresh(proposal.proposal_id);
        const stillRunning =
          next.task_status === 'running' || next.task_status === 'verifying';
        if (!cancelled && stillRunning) {
          pollRef.current = setTimeout(tick, 3000);
        } else if (!cancelled && !postVerifyRefreshedRef.current) {
          // 任务结束后案例归档最多延迟一个后台周期才回写 case_id，补拉一次
          postVerifyRefreshedRef.current = true;
          pollRef.current = setTimeout(tick, 25000);
        }
      } catch {
        if (!cancelled) pollRef.current = setTimeout(tick, 5000);
      }
    };
    pollRef.current = setTimeout(tick, 3000);
    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [proposal.status, proposal.task_status, proposal.proposal_id, refresh]);

  async function decide(decision: 'approved' | 'rejected') {
    setBusy(true);
    setError(null);
    try {
      const decided = await decideRemediationProposal(proposal.proposal_id, {
        decision,
        expected_version: proposal.version,
      });
      setProposal(decided);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `${err.message ?? '操作失败'}（${err.code}）`
          : '操作失败';
      setError(message);
      // 版本冲突时刷新最新状态，便于用户重试
      if (err instanceof ApiError && err.code === 'VERSION_CONFLICT') {
        try {
          await refresh(proposal.proposal_id);
        } catch {
          // 保留错误提示即可
        }
      }
    } finally {
      setBusy(false);
    }
  }

  const pending = proposal.status === 'pending';
  const parameters = formatParameters(proposal.parameters);
  const statusLabel = pending
    ? PROPOSAL_STATUS_LABEL.pending
    : proposal.task_status
      ? TASK_STATUS_LABEL[proposal.task_status]
      : PROPOSAL_STATUS_LABEL[proposal.status];
  const succeeded = proposal.task_status === 'succeeded';
  const failed = proposal.task_status === 'failed';

  return (
    <div className="mt-3 rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-center gap-2">
        <ShieldAlert
          className={`size-4 ${succeeded ? 'text-emerald-600' : failed ? 'text-red-600' : 'text-amber-500'}`}
        />
        <p className="text-sm font-semibold text-slate-900">修复提案待审批</p>
        <span className="ml-auto inline-flex items-center gap-1 text-xs text-slate-500">
          {proposal.status === 'approved' && !succeeded && !failed ? (
            <Loader2 className="size-3 animate-spin" />
          ) : null}
          {statusLabel}
        </span>
      </div>
      <dl className="mt-3 space-y-1.5 text-xs text-slate-600">
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 text-slate-400">设备</dt>
          <dd className="font-medium text-slate-700">{proposal.device_id}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 text-slate-400">动作</dt>
          <dd className="font-medium text-slate-700">
            {proposal.action}
            {parameters ? (
              <span className="ml-1 font-normal">（{parameters}）</span>
            ) : null}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 text-slate-400">原因</dt>
          <dd className="min-w-0 flex-1">{proposal.reason || '—'}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 text-slate-400">影响</dt>
          <dd className="min-w-0 flex-1">{proposal.impact || '—'}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-16 shrink-0 text-slate-400">编号</dt>
          <dd className="font-mono">{proposal.proposal_id}</dd>
        </div>
      </dl>
      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
      {pending ? (
        <div className="mt-3 flex gap-2">
          <Button size="sm" disabled={busy} onClick={() => decide('approved')}>
            {busy ? <Loader2 className="size-3 animate-spin" /> : null}
            批准执行
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => decide('rejected')}
          >
            拒绝
          </Button>
        </div>
      ) : null}
      {succeeded ? (
        <p className="mt-2 flex items-center gap-1 text-xs text-emerald-600">
          <CheckCircle2 className="size-3.5" /> 设备已恢复，验证通过
        </p>
      ) : null}
      {succeeded && caseId ? (
        <p className="mt-1 text-xs text-slate-500">
          本次修复已自动沉淀为故障案例 <span className="font-mono">{caseId}</span>
        </p>
      ) : null}
      {failed ? (
        <p className="mt-2 flex items-center gap-1 text-xs text-red-600">
          <XCircle className="size-3.5" /> 恢复验证未通过，请人工跟进
        </p>
      ) : null}
      {proposal.status === 'rejected' ? (
        <p className="mt-2 text-xs text-slate-500">提案已拒绝，未执行任何操作</p>
      ) : null}
      {proposal.status === 'expired' ? (
        <p className="mt-2 text-xs text-slate-500">提案已过期，请重新发起</p>
      ) : null}
    </div>
  );
}
