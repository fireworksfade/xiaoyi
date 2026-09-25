import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ConversationView } from '@/components/conversation-view';

const baseProps = {
  sidebarCollapsed: false,
  conversation: null,
  selectedId: null,
  messages: [],
  running: false,
  busy: false,
  error: null,
  hasMore: false,
  loadingEarlier: false,
  earlierError: null,
  scrollRef: createRef<HTMLDivElement>(),
  composer: <div>composer</div>,
  onExpandSidebar: vi.fn(),
  onOpenSidebar: vi.fn(),
  onOpenSettings: vi.fn(),
  onOpenRunRecords: vi.fn(),
  onOpenKnowledge: vi.fn(),
  onRetryConversation: vi.fn(),
  onLoadEarlier: vi.fn(),
  onSuggestion: vi.fn(),
};

describe('ConversationView', () => {
  it('shows initial loading and then the empty conversation state', () => {
    const { rerender } = render(<ConversationView {...baseProps} busy />);
    expect(screen.getByText('正在加载对话…')).toBeInTheDocument();

    rerender(<ConversationView {...baseProps} />);
    expect(screen.getByText('今天要处理什么？')).toBeInTheDocument();
    fireEvent.click(screen.getByText('查看设备状态'));
    expect(baseProps.onSuggestion).toHaveBeenCalledWith('查看当前设备运行状态');
  });

  it('shows a recoverable conversation load error', () => {
    const retry = vi.fn();
    render(
      <ConversationView
        {...baseProps}
        selectedId="c1"
        conversation={{
          id: 'c1',
          title: '设备排查',
          created_at: 't',
          updated_at: 't',
        }}
        error="网络中断"
        onRetryConversation={retry}
      />,
    );
    expect(screen.getByText('网络中断')).toBeInTheDocument();
    fireEvent.click(screen.getByText('重新加载'));
    expect(retry).toHaveBeenCalledOnce();
  });
});
