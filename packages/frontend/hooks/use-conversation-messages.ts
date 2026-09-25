'use client';

import {
  type Dispatch,
  type RefObject,
  type SetStateAction,
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';

import {
  type ConversationMessage,
  type RemediationProposal,
  type UploadedAttachment,
  listConversationMessages,
} from '@/lib/api';

export type ChatMessage = {
  id: number | string;
  role: 'user' | 'assistant';
  text: string;
  tools?: { name: string; result: string }[];
  citation?: string;
  attachments?: UploadedAttachment[];
  proposals?: RemediationProposal[];
};

export function toChatMessage(message: ConversationMessage): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    text: message.content,
    proposals: Array.isArray(message.metadata?.remediation_proposals)
      ? (message.metadata.remediation_proposals as RemediationProposal[])
      : undefined,
  };
}

const DEFAULT_PAGE_SIZE = 50;

type UseConversationMessagesOptions = {
  /** 消息滚动容器；用于“加载更早消息”后保持滚动锚点 */
  scrollRef: RefObject<HTMLDivElement | null>;
  pageSize?: number;
};

/**
 * 对话消息列表 + 游标分页（WP-10 §9.2 / §14.4）。
 *
 * - 初次只加载最近一页；顶部“加载更早消息”用 next_cursor 翻页；
 * - prepend 后恢复滚动锚点，避免页面跳动；
 * - 对话切换调用 reset() 取消旧分页状态；
 * - 运行期新消息通过 setMessages 追加，不清空已加载历史。
 */
export function useConversationMessages({
  scrollRef,
  pageSize = DEFAULT_PAGE_SIZE,
}: UseConversationMessagesOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [earlierError, setEarlierError] = useState<string | null>(null);
  const cursorRef = useRef<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const loadIdRef = useRef(0);
  const loadingEarlierRef = useRef(false);
  // prepend 提交前的容器高度；提交后按高度差补偿 scrollTop
  const heightBeforeRef = useRef<number | null>(null);
  // prepend 时跳过页面的“滚到底部”副作用，由本 hook 的锚点恢复接管
  const skipAutoScrollRef = useRef(false);

  const reset = useCallback(() => {
    loadIdRef.current += 1;
    cursorRef.current = null;
    conversationIdRef.current = null;
    loadingEarlierRef.current = false;
    heightBeforeRef.current = null;
    skipAutoScrollRef.current = false;
    setMessages([]);
    setHasMore(false);
    setLoadingEarlier(false);
    setEarlierError(null);
  }, []);

  const loadLatest = useCallback(
    async (conversationId: string) => {
      const loadId = loadIdRef.current + 1;
      loadIdRef.current = loadId;
      conversationIdRef.current = conversationId;
      cursorRef.current = null;
      setHasMore(false);
      setEarlierError(null);
      const page = await listConversationMessages(conversationId, {
        limit: pageSize,
      });
      if (loadIdRef.current !== loadId) return;
      setMessages(page.items.map(toChatMessage));
      cursorRef.current = page.next_cursor;
      setHasMore(page.has_more);
    },
    [pageSize],
  );

  const loadEarlier = useCallback(async () => {
    const conversationId = conversationIdRef.current;
    const cursor = cursorRef.current;
    if (!conversationId || !cursor || loadingEarlierRef.current) return;
    loadingEarlierRef.current = true;
    const loadId = loadIdRef.current;
    setLoadingEarlier(true);
    setEarlierError(null);
    try {
      const page = await listConversationMessages(conversationId, {
        limit: pageSize,
        before: cursor,
      });
      if (loadIdRef.current !== loadId) return;
      if (page.items.length) {
        const container = scrollRef.current;
        heightBeforeRef.current = container?.scrollHeight ?? null;
        skipAutoScrollRef.current = true;
        setMessages((current) => [
          ...page.items.map(toChatMessage),
          ...current,
        ]);
      }
      cursorRef.current = page.next_cursor;
      setHasMore(page.has_more);
    } catch (error) {
      if (loadIdRef.current !== loadId) return;
      setEarlierError(
        error instanceof Error ? error.message : '无法加载更早消息',
      );
    } finally {
      if (loadIdRef.current === loadId) {
        loadingEarlierRef.current = false;
        setLoadingEarlier(false);
      }
    }
  }, [pageSize, scrollRef]);

  // prepend 提交后按高度差补偿 scrollTop，保持视口停留在原消息上
  useLayoutEffect(() => {
    const container = scrollRef.current;
    if (!container || heightBeforeRef.current == null) return;
    const delta = container.scrollHeight - heightBeforeRef.current;
    if (delta > 0) container.scrollTop += delta;
    heightBeforeRef.current = null;
  }, [messages, scrollRef]);

  return {
    messages,
    setMessages: setMessages as Dispatch<SetStateAction<ChatMessage[]>>,
    hasMore,
    loadingEarlier,
    earlierError,
    loadLatest,
    loadEarlier,
    reset,
    skipAutoScrollRef,
  };
}
