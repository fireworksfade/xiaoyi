import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

const { getRunArtifactMock } = vi.hoisted(() => ({
  getRunArtifactMock: vi.fn(),
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  getRunArtifact: getRunArtifactMock,
}));

import { ToolChip, extractCitations } from '@/features/conversation/tool-chip';
import type { ToolCallInfo } from '@/hooks/use-conversation-messages';

function tool(overrides: Partial<ToolCallInfo> = {}): ToolCallInfo {
  return {
    name: 'search_knowledge',
    result: '已完成',
    ...overrides,
  };
}

const RETRIEVAL_OUTPUT = {
  ok: true,
  data: {
    results: [
      { title: 'MQTT 连接指南', source: 'mqtt_docs', id: 'mqtt-001', score: 0.8712 },
      { title: 'WiFi 重连流程', source: 'wifi_docs', id: 'wifi-002', score: 0.6531 },
    ],
  },
};

describe('extractCitations', () => {
  it('reads search_knowledge data.results', () => {
    const citations = extractCitations(RETRIEVAL_OUTPUT);
    expect(citations).toEqual([
      { title: 'MQTT 连接指南', source: 'mqtt_docs', score: 0.8712 },
      { title: 'WiFi 重连流程', source: 'wifi_docs', score: 0.6531 },
    ]);
  });

  it('reads diagnose_fault data.sources with source_id fallback titles', () => {
    const citations = extractCitations({
      ok: true,
      data: {
        sources: [{ source_type: 'mqtt_docs', source_id: 'mqtt-009', score: 0.42 }],
      },
    });
    expect(citations).toEqual([
      { title: 'mqtt-009', source: 'mqtt_docs', score: 0.42 },
    ]);
  });

  it('returns null for non-citation payloads', () => {
    expect(extractCitations({ ok: true, data: { device_id: 'ESP32_05' } })).toBeNull();
    expect(extractCitations('text')).toBeNull();
  });
});

describe('ToolChip', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    getRunArtifactMock.mockReset();
  });

  it('stays collapsed and inert without output or artifact', async () => {
    const user = userEvent.setup();
    render(<ToolChip tool={tool()} />);
    await user.click(screen.getByRole('button'));
    expect(screen.queryByText('引用来源')).not.toBeInTheDocument();
  });

  it('expands inline output into a citation list', async () => {
    const user = userEvent.setup();
    render(<ToolChip tool={tool({ output: RETRIEVAL_OUTPUT })} />);
    await user.click(screen.getByRole('button'));
    expect(screen.getByText('引用来源')).toBeInTheDocument();
    expect(screen.getByText('MQTT 连接指南')).toBeInTheDocument();
    expect(screen.getByText('0.8712')).toBeInTheDocument();
  });

  it('fetches the artifact once when the output was offloaded', async () => {
    getRunArtifactMock.mockResolvedValue({
      artifact: { id: 'A-1', kind: 'tool_output' },
      content: RETRIEVAL_OUTPUT,
    });
    const user = userEvent.setup();
    render(<ToolChip tool={tool({ runId: 'R-1', artifactId: 'A-1' })} />);
    await user.click(screen.getByRole('button'));
    await waitFor(() =>
      expect(screen.getByText('MQTT 连接指南')).toBeInTheDocument(),
    );
    expect(getRunArtifactMock).toHaveBeenCalledWith('R-1', 'A-1');

    // 折叠再展开不重复请求
    await user.click(screen.getByRole('button'));
    await user.click(screen.getByRole('button'));
    expect(getRunArtifactMock).toHaveBeenCalledTimes(1);
  });

  it('shows a load error and keeps the chip usable', async () => {
    getRunArtifactMock.mockRejectedValue(new Error('网络错误'));
    const user = userEvent.setup();
    render(<ToolChip tool={tool({ runId: 'R-1', artifactId: 'A-1' })} />);
    await user.click(screen.getByRole('button'));
    await waitFor(() =>
      expect(screen.getByText(/网络错误/)).toBeInTheDocument(),
    );
    expect(screen.queryByText('引用来源')).not.toBeInTheDocument();
  });

  it('shows raw JSON for non-citation payloads', async () => {
    const user = userEvent.setup();
    render(
      <ToolChip
        tool={tool({ output: { ok: true, data: { device_id: 'ESP32_05' } } })}
      />,
    );
    await user.click(screen.getByRole('button'));
    expect(await screen.findByText(/ESP32_05/)).toBeInTheDocument();
    expect(screen.queryByText('引用来源')).not.toBeInTheDocument();
  });
});
