import { request } from './client';

export type RemediationProposal = {
  proposal_id: string;
  device_id: string;
  action: string;
  parameters: Record<string, unknown>;
  reason: string;
  impact: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  version: number;
  expires_at: string;
  task_status: 'running' | 'verifying' | 'succeeded' | 'failed' | null;
  command_id: string | null;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RemediationProposalDetail = {
  proposal: RemediationProposal;
  command: {
    command_id: string;
    status: 'pending' | 'acked' | 'applied' | 'failed' | 'timeout';
    verify_status: 'succeeded' | 'failed' | null;
    ack: Record<string, unknown> | null;
    case_status: 'pending' | 'archived' | 'skipped' | null;
    case_id: string | null;
  } | null;
  delivered?: boolean;
};

export async function getRemediationProposal(proposalId: string) {
  return request<RemediationProposalDetail>(
    `/remediation-proposals/${encodeURIComponent(proposalId)}`,
  );
}

export async function decideRemediationProposal(
  proposalId: string,
  payload: { decision: 'approved' | 'rejected'; expected_version: number },
) {
  return request<
    RemediationProposal & { command?: unknown; delivered?: boolean }
  >(
    `/remediation-proposals/${encodeURIComponent(proposalId)}/decision`,
    { method: 'POST', body: JSON.stringify(payload) },
    true,
  );
}
