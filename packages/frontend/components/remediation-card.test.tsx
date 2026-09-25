import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RemediationCard } from '@/components/remediation-card';
import type { RemediationProposal } from '@/lib/api';

function proposal(
  overrides: Partial<RemediationProposal> = {},
): RemediationProposal {
  return {
    proposal_id: 'P-1',
    device_id: 'ESP32_05',
    action: 'restart_device',
    parameters: {},
    reason: '设备无响应',
    impact: '短暂离线',
    status: 'pending',
    version: 1,
    expires_at: '2026-09-14T13:00:00Z',
    task_status: null,
    command_id: null,
    decided_by: null,
    decided_at: null,
    created_at: '2026-09-14T12:00:00Z',
    updated_at: '2026-09-14T12:00:00Z',
    ...overrides,
  };
}

describe('RemediationCard refresh recovery', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('refreshes a historical proposal snapshot and restores the archived result', async () => {
    const completed = proposal({
      status: 'approved',
      version: 2,
      task_status: 'succeeded',
      command_id: 'CMD-1',
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({
          data: {
            proposal: completed,
            command: {
              command_id: 'CMD-1',
              status: 'applied',
              verify_status: 'succeeded',
              ack: {},
              case_status: 'archived',
              case_id: 'CASE-1',
            },
          },
          request_id: 'r',
        }),
      ),
    );

    render(<RemediationCard proposal={proposal()} />);

    await waitFor(() =>
      expect(screen.getByText('设备已恢复，验证通过')).toBeInTheDocument(),
    );
    expect(screen.getByText('CASE-1')).toBeInTheDocument();
    expect(screen.queryByText('批准执行')).not.toBeInTheDocument();
  });
});
