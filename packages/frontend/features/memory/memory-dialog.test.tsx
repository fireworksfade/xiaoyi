import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MemoryDialog } from '@/features/memory/memory-dialog';
import type { MemoryDetail, MemorySummary } from '@/lib/api';

function listResponse(): MemorySummary {
  return {
    id: 'm-1',
    kind: 'experience',
    status: 'active',
    title: 'MQTT 超时先查心跳',
    current_revision: 1,
    active_revision: 1,
    summary: 'keep alive 超时优先检查客户端心跳配置。',
    source_type: 'task',
    created_at: '2026-09-28T10:00:00Z',
    updated_at: '2026-09-28T10:00:00Z',
    index_status: 'indexed',
  };
}

function detailResponse(): MemoryDetail {
  return {
    ...listResponse(),
    content: {
      claims: [
        {
          text: '心跳间隔大于 Broker 超时会引发 keep alive timeout',
          epistemic_status: 'hypothesis',
          evidence_refs: ['ep-1'],
        },
      ],
      procedure: [{ text: '检查 keep alive 配置后重连' }],
      limitations: [],
    },
    applicability: { mcp_server_id: 'srv-1' },
    review_state: 'confirmed',
    sources: [],
  };
}

function envelope(data: unknown, status = 200) {
  return new Response(
    JSON.stringify(status >= 400 ? data : { data, request_id: 'r-1' }),
    {
      status,
      headers: { 'Content-Type': 'application/json' },
    },
  );
}

type FetchCall = { url: string; method: string; body: unknown };

describe('MemoryDialog editing', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('edits an active experience and keeps the old revision in recall', async () => {
    const calls: FetchCall[] = [];
    let currentRevision = 1;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        const method = init?.method ?? 'GET';
        const body =
          typeof init?.body === 'string' ? JSON.parse(init.body) : null;
        calls.push({ url, method, body });
        if (url.endsWith('/auth/me')) {
          return envelope({ id: 'u-1', username: 'admin' });
        }
        if (url.endsWith('/auth/login')) {
          return envelope({ csrf_token: 'csrf-1', username: 'admin' });
        }
        if (url.endsWith('/memories/activity'))
          return envelope({
            candidate_count: 0,
            items: [],
            action_results: [],
          });
        if (url.includes('/memories/m-1') && method === 'GET') {
          return envelope(detailResponse());
        }
        if (url.includes('/memories/m-1') && method === 'PATCH') {
          if (body.expected_revision !== currentRevision) {
            return envelope(
              {
                error: { code: 'MEMORY_VERSION_CONFLICT', message: 'conflict' },
              },
              409,
            );
          }
          currentRevision = body.expected_revision + 1;
          return envelope({
            ...detailResponse(),
            current_revision: currentRevision,
            active_revision: 1,
          });
        }
        if (url.includes('/memories') && method === 'GET') {
          return envelope({
            items: [{ ...listResponse(), current_revision: currentRevision }],
            next_cursor: null,
          });
        }
        return envelope({}, 404);
      }),
    );

    render(<MemoryDialog open onOpenChange={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText('MQTT 超时先查心跳')).toBeTruthy(),
    );

    fireEvent.click(screen.getByLabelText('编辑 MQTT 超时先查心跳'));
    const summaryInput = await screen.findByLabelText('摘要');
    fireEvent.change(summaryInput, {
      target: { value: '修订后的经验摘要。' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));

    await waitFor(() =>
      expect(
        screen.getByText('已生成待确认新版本；旧版本仍在正常召回中使用。'),
      ).toBeTruthy(),
    );
    const patch = calls.find((call) => call.method === 'PATCH');
    expect(patch?.body).toMatchObject({
      title: 'MQTT 超时先查心跳',
      summary: '修订后的经验摘要。',
      expected_revision: 1,
    });
  });

  it('surfaces a version conflict from the backend', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        const method = init?.method ?? 'GET';
        if (url.endsWith('/auth/me')) {
          return envelope({ id: 'u-1', username: 'admin' });
        }
        if (url.endsWith('/auth/login')) {
          return envelope({ csrf_token: 'csrf-1', username: 'admin' });
        }
        if (url.endsWith('/memories/activity'))
          return envelope({
            candidate_count: 0,
            items: [],
            action_results: [],
          });
        if (url.includes('/memories/m-1') && method === 'GET') {
          return envelope(detailResponse());
        }
        if (url.includes('/memories/m-1') && method === 'PATCH') {
          return envelope(
            { error: { code: 'MEMORY_VERSION_CONFLICT', message: 'conflict' } },
            409,
          );
        }
        if (url.includes('/memories') && method === 'GET') {
          return envelope({ items: [listResponse()], next_cursor: null });
        }
        return envelope({}, 404);
      }),
    );

    render(<MemoryDialog open onOpenChange={() => {}} />);
    await waitFor(() =>
      expect(screen.getByText('MQTT 超时先查心跳')).toBeTruthy(),
    );
    fireEvent.click(screen.getByLabelText('编辑 MQTT 超时先查心跳'));
    await screen.findByLabelText('摘要');
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));
    await waitFor(() =>
      expect(screen.getByText('内容已更新，请刷新后重试')).toBeTruthy(),
    );
  });

  it.each(['active', 'suspended'])(
    'reviews and confirms current revision of an %s experience',
    async (status) => {
      const confirmed: unknown[] = [];
      const item = {
        ...detailResponse(),
        status,
        current_revision: 2,
        active_version: {
          revision: 1,
          title: '旧版',
          summary: '旧摘要',
          content: { procedure: ['旧步骤'] },
          applicability: {},
        },
      };
      vi.stubGlobal(
        'fetch',
        vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
          const url =
            typeof input === 'string'
              ? input
              : input instanceof URL
                ? input.href
                : input.url;
          if (url.endsWith('/auth/me')) return envelope({ id: 'u-1' });
          if (url.endsWith('/auth/login'))
            return envelope({ csrf_token: 'csrf-1' });
          if (url.endsWith('/activity'))
            return envelope({
              candidate_count: 1,
              items: [],
              action_results: [],
            });
          if (url.endsWith('/confirm')) {
            confirmed.push(
              typeof init?.body === 'string' ? JSON.parse(init.body) : null,
            );
            return envelope({ ...item, active_revision: 2 });
          }
          if (url.endsWith('/m-1')) return envelope(item);
          return envelope({ items: [item], next_cursor: null });
        }),
      );
      render(<MemoryDialog open onOpenChange={() => {}} />);
      const button = await screen.findByRole('button', {
        name: '确认 MQTT 超时先查心跳',
      });
      fireEvent.click(button); // First click opens the precise version for review.
      await screen.findByText('检查 keep alive 配置后重连');
      expect(confirmed).toEqual([]);
      expect(screen.getByText('旧步骤')).toBeTruthy();
      fireEvent.click(button);
      await waitFor(() =>
        expect(confirmed).toEqual([{ expected_revision: 2 }]),
      );
    },
  );

  it('shows structured candidate evidence and late failure activity', async () => {
    const followup = vi.fn();
    const item = {
      ...detailResponse(),
      status: 'candidate',
      active_revision: null,
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        if (url.endsWith('/auth/me')) return envelope({ id: 'u-1' });
        if (url.endsWith('/activity'))
          return envelope({
            candidate_count: 1,
            items: [],
            action_results: [
              {
                run_id: 'r1',
                command_id: 'c1',
                device_id: 'ESP32',
                needs_followup: true,
              },
            ],
          });
        if (url.endsWith('/m-1')) return envelope(item);
        return envelope({ items: [item], next_cursor: null });
      }),
    );
    render(<MemoryDialog open onOpenChange={() => {}} onFollowup={followup} />);
    fireEvent.click(await screen.findByText('MQTT 超时先查心跳'));
    await screen.findByText('检查 keep alive 配置后重连');
    expect(screen.getByText(/ESP32 的修复失败；任务已结束/)).toBeTruthy();
    expect(screen.getByText('适用条件')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '发起后续诊断' }));
    expect(followup).toHaveBeenCalledWith(expect.stringContaining('ESP32'));
  });
});
