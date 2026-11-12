import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { Markdown } from '@/features/conversation/markdown';

afterEach(cleanup);

// 取自“查询节点历史数据”的真实回答片段
const HISTORY_ANSWER = `## 过去24小时各节点平均温度与有效样本数

**统计口径**（来自工具返回的 \`metric_definition\` / \`time_window\`）
- 指标：历史遥测温度（°C）
- 结果完整性：\`truncated=false\`，返回 26 个设备

### 生产节点（ESP32_01～10）

| 设备 | 名称 | 平均温度(°C) | 有效样本数 |
|---|---|---:|---:|
| ESP32_01 | 车间A-环境监测01 | 27.51 | 11,572 |
| ESP32_09 | 锅炉房-烟温监测 | 55.03 | 6 |

### 需要注意的点
- **样本量差异极大**：ESP32_09 仅 6 条。
- OPS_* 与 iot-action-e2e-* 为测试类设备。

需要我单独做故障诊断吗？`;

describe('Markdown', () => {
  it('renders headings, tables, lists and emphasis instead of raw markers', () => {
    const { container } = render(<Markdown text={HISTORY_ANSWER} />);

    expect(
      screen.getByRole('heading', {
        name: '过去24小时各节点平均温度与有效样本数',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: '需要注意的点' }),
    ).toBeInTheDocument();

    const table = screen.getByRole('table');
    const headers = within(table).getAllByRole('columnheader');
    expect(headers.map((cell) => cell.textContent)).toEqual([
      '设备',
      '名称',
      '平均温度(°C)',
      '有效样本数',
    ]);
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(3);
    expect(within(rows[2]).getAllByRole('cell')[3]).toHaveTextContent('6');
    expect(within(rows[2]).getAllByRole('cell')[3]).toHaveStyle({
      textAlign: 'right',
    });

    expect(screen.getByText('样本量差异极大').tagName).toBe('STRONG');
    expect(screen.getByText('metric_definition').tagName).toBe('CODE');
    expect(screen.getAllByRole('list')).toHaveLength(2);

    // 标识符里的星号不能被当成斜体，原样保留
    expect(
      screen.getByText('OPS_* 与 iot-action-e2e-* 为测试类设备。'),
    ).toBeInTheDocument();
    expect(container.querySelector('em')).toBeNull();
    expect(container.textContent).not.toMatch(/\|---|\*\*|^#/m);
  });

  it('nests indented list items and keeps ordered list numbering', () => {
    render(
      <Markdown
        text={
          '2. 对 **ESP32_06** 执行诊断\n   - 先查日志\n   - 再检索文档\n3. 核查 ESP32_09'
        }
      />,
    );
    const [outer, inner] = screen.getAllByRole('list');
    expect(outer.tagName).toBe('OL');
    expect(outer).toHaveAttribute('start', '2');
    expect(within(outer).getAllByRole('listitem')).toHaveLength(4);
    expect(inner.tagName).toBe('UL');
    expect(
      within(inner)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual(['先查日志', '再检索文档']);
  });

  it('never turns untrusted text into HTML or unsafe links', () => {
    const { container } = render(
      <Markdown
        text={
          '日志：<img src=x onerror=alert(1)> [点我](javascript:alert(1)) [文档](https://docs.espressif.com/x)'
        }
      />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror=alert(1)>');
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', 'https://docs.espressif.com/x');
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer');
    expect(container.textContent).toContain('[点我](javascript:alert(1))');
  });

  it('shows unfinished markup from a streaming answer as plain text', () => {
    const { container } = render(
      <Markdown
        text={'**统计口径**：按有效样本\n| 设备 | 均值 |\n```sql\nSELECT 1'}
      />,
    );
    expect(screen.getByText('统计口径').tagName).toBe('STRONG');
    expect(screen.queryByRole('table')).toBeNull();
    expect(container.querySelector('pre')).toHaveTextContent('SELECT 1');
  });

  it('keeps single line breaks inside a paragraph', () => {
    const { container } = render(
      <Markdown text={'**时间范围**：最近 24 小时\n**设备范围**：全部设备'} />,
    );
    expect(container.querySelectorAll('p')).toHaveLength(1);
    expect(container.querySelectorAll('br')).toHaveLength(1);
  });
});
