import { createRef } from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  useConversationMessages,
  type ChatMessage,
} from '@/hooks/use-conversation-messages';

function messagePage(
  items: unknown[],
  hasMore: boolean,
  cursor: string | null,
) {
  return {
    items,
    next_cursor: cursor,
    has_more: hasMore,
  };
}

function apiMessage(id: string, content: string) {
  return {
    id,
    role: id.startsWith('a') ? 'assistant' : 'user',
    content,
    metadata: {},
    created_at: '2026-09-14T00:00:00Z',
  };
}

/**
 * jsdom 没有布局引擎，scrollHeight 不会随 DOM 提交变化；
 * 用读取序列模拟「捕获时 1000 → prepend 提交后 1600」。
 */
function fakeContainer(heights: number[]) {
  const el = document.createElement('div');
  let index = 0;
  Object.defineProperty(el, 'scrollHeight', {
    get: () => heights[Math.min(index++, heights.length - 1)],
    configurable: true,
  });
  el.scrollTop = 400;
  return el;
}

describe('useConversationMessages', () => {
  beforeEach(() => {
    window.sessionStorage.setItem('xiaoyi.csrf-token', 'test-csrf');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  it('loads only the latest page and exposes cursor state', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) =>
      Response.json(
        {
          data: messagePage(
            [apiMessage('m1', '一'), apiMessage('m2', '二')],
            true,
            'cursor-1',
          ),
          request_id: 't',
        },
        { status: 200 },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);
    const scrollRef = createRef<HTMLDivElement>();
    const { result } = renderHook(() => useConversationMessages({ scrollRef }));

    await act(async () => {
      await result.current.loadLatest('conv-1');
    });

    expect(result.current.messages.map((m) => m.text)).toEqual(['一', '二']);
    expect(result.current.hasMore).toBe(true);
    expect(fetchMock.mock.calls[0][0]).toContain(
      '/conversations/conv-1/messages',
    );
    expect(fetchMock.mock.calls[0][0]).toContain('limit=50');
  });

  it('prepends earlier pages without dropping loaded messages', async () => {
    const pages = [
      messagePage(
        [apiMessage('m3', '三'), apiMessage('a4', '答')],
        true,
        'cursor-1',
      ),
      messagePage(
        [apiMessage('m1', '一'), apiMessage('m2', '二')],
        false,
        null,
      ),
    ];
    let call = 0;
    const urls: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string) => {
        urls.push(input);
        const body = pages[Math.min(call, pages.length - 1)];
        call += 1;
        return Response.json({ data: body, request_id: 't' }, { status: 200 });
      }),
    );
    const scrollRef = createRef<HTMLDivElement>();
    const { result } = renderHook(() =>
      useConversationMessages({ scrollRef, pageSize: 2 }),
    );

    await act(async () => {
      await result.current.loadLatest('conv-1');
    });
    await act(async () => {
      await result.current.loadEarlier();
    });

    expect(urls[1]).toContain('before=cursor-1');
    expect(urls[1]).toContain('limit=2');
    expect(result.current.messages.map((m) => m.text)).toEqual([
      '一',
      '二',
      '三',
      '答',
    ]);
    expect(result.current.hasMore).toBe(false);
  });

  it('keeps the scroll anchor when prepending', async () => {
    const pages = [
      messagePage([apiMessage('m3', '三')], true, 'cursor-1'),
      messagePage(
        [apiMessage('m1', '一'), apiMessage('m2', '二')],
        false,
        null,
      ),
    ];
    let call = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        const body = pages[call];
        call += 1;
        return Response.json({ data: body, request_id: 't' }, { status: 200 });
      }),
    );
    const container = fakeContainer([1000, 1600]);
    const scrollRef = { current: container };
    const { result } = renderHook(() =>
      useConversationMessages({ scrollRef, pageSize: 1 }),
    );

    await act(async () => {
      await result.current.loadLatest('conv-1');
    });
    // 捕获 scrollHeight=1000（scrollTop=400），prepend 提交后高度 1600，应补偿到 1000
    await act(async () => {
      await result.current.loadEarlier();
    });

    expect(container.scrollTop).toBe(1000);
  });

  it('reset cancels stale loads from the previous conversation', async () => {
    let resolveFirst!: (value: Response) => void;
    const firstPromise = new Promise<Response>((resolve) => {
      resolveFirst = resolve;
    });
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: string) => {
        if (_input.includes('conv-1')) return firstPromise;
        return Promise.resolve(
          Response.json(
            {
              data: messagePage([apiMessage('m9', '九')], false, null),
              request_id: 't',
            },
            { status: 200 },
          ),
        );
      }),
    );
    const scrollRef = createRef<HTMLDivElement>();
    const { result } = renderHook(() => useConversationMessages({ scrollRef }));

    let firstLoad: Promise<void>;
    act(() => {
      firstLoad = result.current.loadLatest('conv-1');
    });
    act(() => {
      result.current.reset();
    });
    await act(async () => {
      await result.current.loadLatest('conv-2');
    });
    // 迟到的 conv-1 响应不应覆盖 conv-2 的状态
    resolveFirst(
      Response.json(
        {
          data: messagePage(
            Array.from({ length: 50 }, (_, i) => apiMessage(`m${i}`, `旧${i}`)),
            false,
            null,
          ),
          request_id: 't',
        },
        { status: 200 },
      ),
    );
    await act(async () => {
      await firstLoad;
    });

    expect(result.current.messages.map((m) => m.text)).toEqual(['九']);
    expect(result.current.hasMore).toBe(false);
  });

  it('appending new messages keeps the loaded history', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json(
          {
            data: messagePage([apiMessage('m1', '一')], false, null),
            request_id: 't',
          },
          { status: 200 },
        ),
      ),
    );
    const scrollRef = createRef<HTMLDivElement>();
    const { result } = renderHook(() => useConversationMessages({ scrollRef }));
    await act(async () => {
      await result.current.loadLatest('conv-1');
    });

    const appended: ChatMessage = {
      id: 'user-1',
      role: 'user',
      text: '新消息',
    };
    await act(async () => {
      result.current.setMessages((current) => [...current, appended]);
    });

    expect(result.current.messages.map((m) => m.text)).toEqual([
      '一',
      '新消息',
    ]);
  });

  it('surfaces earlier-page errors without clearing messages', async () => {
    const pages: Array<Record<string, unknown> | Error> = [
      messagePage([apiMessage('m2', '二')], true, 'cursor-1'),
      new Error('网络中断'),
    ];
    let call = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        const page = pages[call];
        call += 1;
        if (page instanceof Error) throw page;
        return Response.json({ data: page, request_id: 't' }, { status: 200 });
      }),
    );
    const scrollRef = createRef<HTMLDivElement>();
    const { result } = renderHook(() =>
      useConversationMessages({ scrollRef, pageSize: 1 }),
    );
    await act(async () => {
      await result.current.loadLatest('conv-1');
    });
    await act(async () => {
      await result.current.loadEarlier();
    });

    expect(result.current.earlierError).toBe('网络中断');
    expect(result.current.messages.map((m) => m.text)).toEqual(['二']);
  });
});
