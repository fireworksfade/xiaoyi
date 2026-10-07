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
      {
        title: 'MQTT 连接指南',
        source: 'mqtt_docs',
        id: 'mqtt-001',
        score: 0.8712,
      },
      {
        title: 'WiFi 重连流程',
        source: 'wifi_docs',
        id: 'wifi-002',
        score: 0.6531,
      },
    ],
  },
};

const SQL_OUTPUT = {
  ok: true,
  data: {
    execution_mode: 'query_plan',
    columns: ['device_id', 'avg', 'sample_count'],
    rows: [{ device_id: 'ESP32_05', avg: 25.5, sample_count: 12 }],
    metric_definition: { definition: '按有效温度样本计算', unit: '°C' },
    time_window: {
      kind: 'last_hours',
      start_utc: '2026-10-06T03:00:00Z',
      end_utc: '2026-10-07T03:00:00Z',
    },
    utc_offset_minutes: 480,
    sql: 'SELECT avg(temperature) FROM iot_telemetry',
    parameters: { row_limit: 100 },
    truncated: true,
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
        sources: [
          { source_type: 'mqtt_docs', source_id: 'mqtt-009', score: 0.42 },
        ],
      },
    });
    expect(citations).toEqual([
      { title: 'mqtt-009', source: 'mqtt_docs', score: 0.42 },
    ]);
  });

  it('returns null for non-citation payloads', () => {
    expect(
      extractCitations({ ok: true, data: { device_id: 'ESP32_05' } }),
    ).toBeNull();
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

  it('renders archived SQL rows, units, time scope and truncation', async () => {
    getRunArtifactMock.mockResolvedValue({ content: SQL_OUTPUT });
    render(
      <ToolChip
        tool={tool({
          name: 'query_iot_data',
          artifactId: 'A-SQL',
          runId: 'R-SQL',
        })}
      />,
    );
    await userEvent.setup().click(screen.getByRole('button'));
    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', { name: '平均值（°C）' }),
    ).toBeInTheDocument();
    expect(screen.getByText('25.5')).toBeInTheDocument();
    expect(screen.getByText(/2026-10-06 11:00:00/)).toHaveTextContent(
      'UTC+08:00',
    );
    expect(screen.getByText(/结果已达到返回上限/)).toBeInTheDocument();
    expect(getRunArtifactMock).toHaveBeenCalledWith('R-SQL', 'A-SQL');
  });

  it('shows empty SQL results without inventing a zero measurement', async () => {
    render(
      <ToolChip
        tool={tool({
          output: {
            ...SQL_OUTPUT,
            data: { ...SQL_OUTPUT.data, rows: [], truncated: false },
          },
        })}
      />,
    );
    await userEvent.setup().click(screen.getByRole('button'));
    expect(screen.getByText('该范围内没有匹配数据。')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows a clarification instead of a successful SQL result', async () => {
    render(
      <ToolChip
        tool={tool({
          status: 'error',
          output: {
            ok: false,
            error: {
              code: 'TEXT2SQL_CLARIFICATION_REQUIRED',
              message: '请指定统计时间范围',
            },
          },
        })}
      />,
    );
    await userEvent.setup().click(screen.getByRole('button'));
    expect(screen.getByRole('alert')).toHaveTextContent('需要补充查询条件');
    expect(screen.getByRole('alert')).toHaveTextContent('请指定统计时间范围');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it.each([
    ['dashscope', 'dashscope_remote', false, '向量检索：API · 重排：API'],
    ['qwen3_local', 'qwen3_local', true, '本地 Qwen 0.6B'],
    ['hash', 'weighted', true, 'Hash 兜底'],
  ])(
    'shows the actual retrieval providers: %s',
    async (embedding, provider, fallback, text) => {
      render(
        <ToolChip
          tool={tool({
            output: {
              ...RETRIEVAL_OUTPUT,
              data: {
                ...RETRIEVAL_OUTPUT.data,
                embedding_provider: embedding,
                reranker: { provider, fallback },
              },
            },
          })}
        />,
      );
      await userEvent.setup().click(screen.getByRole('button'));
      expect(screen.getByLabelText('检索服务状态')).toHaveTextContent(text);
      if (fallback)
        expect(screen.getByLabelText('检索服务状态')).toHaveTextContent(
          '已使用兜底',
        );
    },
  );
});
