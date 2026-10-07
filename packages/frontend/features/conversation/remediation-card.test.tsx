import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { RemediationCard } from '@/features/conversation/remediation-card';
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

  it('refreshes a historical proposal snapshot and shows the verify result', async () => {
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
              delivery_status: 'delivered',
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
    // 案例归档链路已退役：不再展示 case_id，也不再声称自动沉淀
    expect(screen.queryByText(/故障案例/)).not.toBeInTheDocument();
    expect(screen.queryByText('批准执行')).not.toBeInTheDocument();
  });

  it('shows missing verification evidence as inconclusive and stops the spinner', async () => {
    const inconclusive = proposal({ status: 'approved', task_status: 'inconclusive', version: 2 });
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({
      data: { proposal: inconclusive, command: null }, request_id: 'r',
    })));
    const { container } = render(<RemediationCard proposal={inconclusive} />);
    expect(screen.getByText('验证证据不足')).toBeInTheDocument();
    expect(screen.getByText('验证证据不足，请检查设备状态后跟进')).toBeInTheDocument();
    expect(container.querySelector('.animate-spin')).toBeNull();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  });
});
