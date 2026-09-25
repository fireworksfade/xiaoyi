'use client';

import type { ReactNode, RefObject } from 'react';
import {
  BookOpen,
  Bot,
  ChevronDown,
  FileSearch,
  Gauge,
  History,
  Loader2,
  Menu,
  PanelLeftOpen,
  Sparkles,
  Wrench,
} from 'lucide-react';

import { MessageList } from '@/components/message-list';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { ChatMessage } from '@/hooks/use-conversation-messages';
import type { Conversation } from '@/lib/api';

const suggestions = [
  {
    icon: FileSearch,
    label: '整理一份文档',
    prompt: '帮我整理工作区里的规格文档',
  },
  {
    icon: Wrench,
    label: '调用工具排查问题',
    prompt: '检查当前可用工具并排查异常',
  },
  { icon: Gauge, label: '查看设备状态', prompt: '查看当前设备运行状态' },
];

type ConversationViewProps = {
  sidebarCollapsed: boolean;
  conversation: Conversation | null;
  selectedId: string | null;
  messages: ChatMessage[];
  running: boolean;
  busy: boolean;
  error: string | null;
  hasMore: boolean;
  loadingEarlier: boolean;
  earlierError: string | null;
  scrollRef: RefObject<HTMLDivElement | null>;
  composer: ReactNode;
  onExpandSidebar: () => void;
  onOpenSidebar: () => void;
  onOpenSettings: () => void;
  onOpenRunRecords: () => void;
  onOpenKnowledge: () => void;
  onRetryConversation: () => void;
  onLoadEarlier: () => void;
  onSuggestion: (prompt: string) => void;
};

export function ConversationView({
  sidebarCollapsed,
  conversation,
  selectedId,
  messages,
  running,
  busy,
  error,
  hasMore,
  loadingEarlier,
  earlierError,
  scrollRef,
  composer,
  onExpandSidebar,
  onOpenSidebar,
  onOpenSettings,
  onOpenRunRecords,
  onOpenKnowledge,
  onRetryConversation,
  onLoadEarlier,
  onSuggestion,
}: ConversationViewProps) {
  return (
    <section className="relative flex min-w-0 flex-1 flex-col bg-white">
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 px-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-2">
          {sidebarCollapsed ? (
            <Button
              variant="ghost"
              size="icon"
              className="hidden text-slate-500 hover:bg-slate-100 md:inline-flex"
              onClick={onExpandSidebar}
            >
              <PanelLeftOpen />
              <span className="sr-only">展开侧边栏</span>
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={onOpenSidebar}
          >
            <Menu />
            <span className="sr-only">打开侧边栏</span>
          </Button>
          <button
            type="button"
            onClick={onOpenSettings}
            className="flex min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-slate-50"
          >
            <span className="truncate font-medium text-slate-900">小yi</span>
            <ChevronDown className="size-4 shrink-0 text-slate-400" />
          </button>
          <Badge
            variant="outline"
            className="hidden rounded-md border-slate-200 bg-slate-50 font-normal text-slate-500 sm:inline-flex"
          >
            工具已连接
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="text-slate-500 hover:bg-slate-100"
            onClick={onOpenRunRecords}
          >
            <History />
            <span className="sr-only">运行记录</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="border-slate-200 text-slate-600 shadow-none"
            onClick={onOpenKnowledge}
          >
            <BookOpen />
            <span className="hidden sm:inline">知识文档</span>
          </Button>
        </div>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {busy ? (
          <div className="grid min-h-full place-items-center px-5 pb-24 text-sm text-slate-400">
            <span className="flex items-center gap-2">
              <Loader2 className="size-4 animate-spin" />
              正在加载对话…
            </span>
          </div>
        ) : error && selectedId ? (
          <div className="mx-auto flex min-h-full max-w-md flex-col items-center justify-center px-5 pb-24 text-center">
            <p className="text-base font-medium text-slate-700">
              这段对话暂时打不开
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500">{error}</p>
            {conversation ? (
              <Button
                type="button"
                variant="outline"
                className="mt-4"
                onClick={onRetryConversation}
              >
                重新加载
              </Button>
            ) : null}
          </div>
        ) : messages.length === 0 ? (
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col items-center justify-center px-5 pb-24 text-center">
            <span className="mb-5 grid size-11 place-items-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700">
              <Sparkles className="size-5" />
            </span>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
              今天要处理什么？
            </h1>
            <p className="mt-2 max-w-lg text-sm leading-6 text-slate-500">
              可以读取资料、调用已授权工具、分析运行数据，或继续一个需要审批的任务。
            </p>
            <div className="mt-7 grid w-full gap-2 sm:grid-cols-3">
              {suggestions.map((suggestion) => (
                <button
                  key={suggestion.label}
                  type="button"
                  onClick={() => onSuggestion(suggestion.prompt)}
                  className="rounded-lg border border-slate-200 p-4 text-left hover:border-slate-300 hover:bg-slate-50"
                >
                  <suggestion.icon className="mb-3 size-5 text-slate-500" />
                  <span className="text-sm font-medium text-slate-700">
                    {suggestion.label}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className="mx-auto w-full max-w-3xl px-5 pt-8 sm:px-8">
              <div className="flex items-center gap-3 border-b border-slate-100 pb-5">
                <span className="grid size-9 place-items-center rounded-lg bg-slate-900 text-white">
                  <Bot className="size-[18px]" />
                </span>
                <div>
                  <h1 className="text-base font-semibold text-slate-900">
                    {conversation?.title ?? '新对话'}
                  </h1>
                  <p className="text-xs text-slate-400">
                    小yi · {messages.length} 条消息
                  </p>
                </div>
              </div>
            </div>
            <MessageList
              messages={messages}
              running={running}
              hasMore={hasMore}
              loadingEarlier={loadingEarlier}
              earlierError={earlierError}
              onLoadEarlier={onLoadEarlier}
            />
          </>
        )}
      </div>
      {composer}
    </section>
  );
}
