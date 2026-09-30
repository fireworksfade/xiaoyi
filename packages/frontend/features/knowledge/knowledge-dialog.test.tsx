import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { KnowledgeDialog } from './knowledge-dialog';
import {
  listKnowledgeDocuments,
  uploadKnowledgeDocument,
} from '@/lib/api/index';
import type { KnowledgeDocumentSummary } from '@/lib/api/knowledge';

vi.mock('@/lib/api/index', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api/index')>()),
  ensureDemoSession: vi.fn().mockResolvedValue({}),
  listKnowledgeDocuments: vi.fn(),
  uploadKnowledgeDocument: vi.fn(),
}));

const docs: KnowledgeDocumentSummary[] = [
  {
    source: 'sensor_docs',
    document_id: 'sensor',
    title: '温度传感器手册',
    chunk_count: 10,
    device_type: 'MODEL-X',
  },
  {
    source: 'device_docs',
    document_id: 'device',
    title: '设备接线手册',
    chunk_count: 20,
    device_type: 'MODEL-Y',
  },
  {
    source: 'mqtt_docs',
    document_id: 'mqtt',
    title: 'MQTT 配置指南',
    chunk_count: 30,
    device_type: 'MODEL-X',
    document_type: 'configuration',
    firmware_version: '2.0',
  },
];

describe('KnowledgeDialog organization', () => {
  beforeEach(() => {
    vi.mocked(listKnowledgeDocuments).mockResolvedValue({
      items: docs,
      total: docs.length,
      limit: 200,
      offset: 0,
    });
  });
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('merges hardware sources, hides empty categories and moves chunk counts into details', async () => {
    render(<KnowledgeDialog open onOpenChange={() => {}} />);
    const hardware = await screen.findByRole('button', {
      name: /设备与硬件\s*2\s*篇文档/,
    });
    fireEvent.click(hardware);
    expect(
      within(hardware.closest('section')!).getByText('温度传感器手册'),
    ).toBeVisible();
    expect(
      within(hardware.closest('section')!).getByText('设备接线手册'),
    ).toBeVisible();
    expect(screen.queryByRole('button', { name: /网络与连接/ })).toBeNull();
    expect(hardware).not.toHaveTextContent('分块');
    expect(screen.getByText('sensor · 10 分块')).not.toBeVisible();
    fireEvent.click(
      within(hardware.closest('section')!).getAllByText('文档详情')[0],
    );
    expect(screen.getByText('sensor · 10 分块')).toBeVisible();
    fireEvent.click(hardware);
    expect(screen.queryByText('温度传感器手册')).toBeNull();
    expect(hardware).toHaveAttribute('aria-expanded', 'false');
  });

  it('searches titles, document IDs and device models without filter dropdowns', async () => {
    const user = userEvent.setup();
    render(<KnowledgeDialog open onOpenChange={() => {}} />);
    await screen.findByText('共 3 篇文档');
    await user.click(screen.getByRole('button', { name: /设备与硬件/ }));
    await user.click(screen.getByRole('button', { name: /协议与通信/ }));
    expect(screen.queryByLabelText('适用设备', { exact: true })).toBeNull();
    expect(screen.queryByLabelText('文档类型', { exact: true })).toBeNull();
    expect(screen.queryByLabelText('硬件版本', { exact: true })).toBeNull();
    expect(screen.queryByLabelText('固件版本', { exact: true })).toBeNull();
    fireEvent.change(screen.getByLabelText('搜索知识文档'), {
      target: { value: 'MODEL-X' },
    });
    expect(screen.queryByText('设备接线手册')).toBeNull();
    expect(screen.getByText('温度传感器手册')).toBeVisible();
    fireEvent.change(screen.getByLabelText('搜索知识文档'), {
      target: { value: '配置指南' },
    });
    expect(screen.queryByText('温度传感器手册')).toBeNull();
    expect(screen.getByText('MQTT 配置指南')).toBeVisible();
    fireEvent.change(screen.getByLabelText('搜索知识文档'), {
      target: { value: ' SENSOR ' },
    });
    expect(screen.getByText('温度传感器手册')).toBeVisible();
    expect(screen.queryByText('MQTT 配置指南')).toBeNull();
    expect(screen.getByText('找到 1 篇，共 3 篇文档')).toBeVisible();
    fireEvent.change(screen.getByLabelText('搜索知识文档'), {
      target: { value: 'missing' },
    });
    expect(screen.getByText('没有匹配的文档。')).toBeVisible();
    await user.click(screen.getByRole('button', { name: '清除搜索' }));
    expect(screen.getByText('设备接线手册')).toBeVisible();
  });

  it('loads every page and uploads domain and tags with the retrieval source', async () => {
    vi.mocked(listKnowledgeDocuments)
      .mockResolvedValueOnce({
        items: docs.slice(0, 1),
        total: 3,
        limit: 1,
        offset: 0,
      })
      .mockResolvedValueOnce({
        items: docs.slice(1),
        total: 3,
        limit: 2,
        offset: 1,
      });
    vi.mocked(uploadKnowledgeDocument).mockResolvedValue({
      source: 'device_docs',
      document_id: 'new',
      chunk_count: 1,
      mysql_saved: false,
      vector_indexed: true,
      sync_status: 'complete',
    });
    const user = userEvent.setup();
    render(<KnowledgeDialog open onOpenChange={() => {}} />);
    await screen.findByText('共 3 篇文档');
    expect(listKnowledgeDocuments).toHaveBeenNthCalledWith(2, {
      limit: 200,
      offset: 1,
    });
    await user.click(screen.getByLabelText('技术领域'));
    await user.click(await screen.findByRole('option', { name: '平台与软件' }));
    await user.click(screen.getByLabelText('文档类型（可选）'));
    await user.click(await screen.findByRole('option', { name: '操作指南' }));
    fireEvent.change(screen.getByLabelText('适用设备（可选）'), {
      target: { value: 'MODEL-Z' },
    });
    fireEvent.change(screen.getByLabelText('硬件版本（可选）'), {
      target: { value: 'Rev. C' },
    });
    fireEvent.change(screen.getByLabelText('固件版本（可选）'), {
      target: { value: '3.0' },
    });
    const file = new File(['# OTA guide'], 'ota.md', { type: 'text/markdown' });
    fireEvent.change(screen.getByLabelText('文档文件'), {
      target: { files: [file] },
    });
    fireEvent.submit(
      screen.getByRole('button', { name: '上传文档' }).closest('form')!,
    );
    await screen.findByText('ota.md 已加入知识库，可用于诊断检索。');
    expect(uploadKnowledgeDocument).toHaveBeenCalledWith(
      file,
      expect.objectContaining({
        source: 'device_docs',
        category: 'software',
        documentType: 'manual',
        deviceType: 'MODEL-Z',
        hardwareVersion: 'Rev. C',
        firmwareVersion: '3.0',
      }),
    );
  });
});
