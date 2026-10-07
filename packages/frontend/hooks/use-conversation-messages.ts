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

export type ToolCallInfo = {
  name: string;
  result: string;
  /** 本次运行 ID；输出转存工件时用于拉取完整内容 */
  runId?: string;
  /** 输出超过内联阈值被转存后的 run_artifact ID */
  artifactId?: string;
  /** 未转存时的完整工具输出 */
  output?: unknown;
  status?: 'running' | 'success' | 'error' | 'incomplete';
  callId?: string;
};

export type ChatMessage = {
  id: number | string;
  role: 'user' | 'assistant';
  text: string;
  tools?: ToolCallInfo[];
  citation?: string;
  attachments?: UploadedAttachment[];
  proposals?: RemediationProposal[];
  remediationStatus?: string;
};

export function toChatMessage(message: ConversationMessage): ChatMessage {
  return {
    id: message.id,
    role: message.role,
    text: message.content,
    tools: Array.isArray(message.metadata?.tool_calls)
      ? message.metadata.tool_calls
          .map((value) => toToolCall(value))
          .filter((value): value is ToolCallInfo => value !== null)
      : undefined,
    proposals: Array.isArray(message.metadata?.remediation_proposals)
      ? (message.metadata.remediation_proposals as RemediationProposal[])
      : undefined,
  };
}

export function toToolCall(
  value: unknown,
  runId?: string,
): ToolCallInfo | null {
  if (!value || typeof value !== 'object') return null;
  const event = value as Record<string, unknown>;
  if (typeof event.tool_name !== 'string') return null;
  const output = event.output;
  const record =
    output && typeof output === 'object'
      ? (output as Record<string, unknown>)
      : null;
  const artifactId =
    typeof record?.artifact_id === 'string' ? record.artifact_id : undefined;
  return {
    name: event.tool_name,
    result: typeof event.summary === 'string' ? event.summary : '已完成',
    runId:
      runId ?? (typeof event.run_id === 'string' ? event.run_id : undefined),
    callId: typeof event.call_id === 'string' ? event.call_id : undefined,
    status: event.ok === false || record?.ok === false ? 'error' : 'success',
    artifactId,
    output: artifactId ? undefined : output,
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
