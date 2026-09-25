'use client';

import {
  Loader2,
  MessageSquare,
  MoreHorizontal,
  PanelLeftClose,
  Pencil,
  Plus,
  Search,
  Settings,
  Trash2,
  X,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { Conversation } from '@/lib/api';

type ConversationSidebarProps = {
  open: boolean;
  collapsed: boolean;
  busy: boolean;
  running: boolean;
  error: string | null;
  query: string;
  conversations: Conversation[];
  selectedId: string | null;
  onOpenChange: (open: boolean) => void;
  onCollapsedChange: (collapsed: boolean) => void;
  onQueryChange: (query: string) => void;
  onNewChat: () => void;
  onOpenConversation: (conversation: Conversation) => void;
  onRename: (conversation: Conversation) => void;
  onDelete: (conversation: Conversation) => void;
  onOpenSettings: () => void;
};

export function ConversationSidebar({
  open,
  collapsed,
  busy,
  running,
  error,
  query,
  conversations,
  selectedId,
  onOpenChange,
  onCollapsedChange,
  onQueryChange,
  onNewChat,
  onOpenConversation,
  onRename,
  onDelete,
  onOpenSettings,
}: ConversationSidebarProps) {
  const normalizedQuery = query.trim().toLocaleLowerCase('zh-CN');
  const visibleConversations = normalizedQuery
    ? conversations.filter((conversation) =>
        conversation.title.toLocaleLowerCase('zh-CN').includes(normalizedQuery),
      )
    : conversations;

  return (
    <>
      {open ? (
        <button
          type="button"
          aria-label="关闭侧边栏"
          className="fixed inset-0 z-30 bg-slate-950/20 md:hidden"
          onClick={() => onOpenChange(false)}
        />
      ) : null}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[272px] shrink-0 flex-col border-r border-slate-200 bg-[#f7f7f8] transition-[transform,margin] duration-200 md:static ${open ? 'translate-x-0' : '-translate-x-full'} ${collapsed ? 'md:-ml-[272px]' : 'md:ml-0'} md:translate-x-0`}
      >
        <div className="flex h-16 items-center gap-2 px-3">
          <Button
            variant="outline"
            className="h-10 flex-1 justify-start border-slate-300 bg-white px-3 text-slate-700 shadow-none hover:bg-slate-50"
            onClick={onNewChat}
            disabled={running}
          >
            <Plus className="size-4" />
            新建对话
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="text-slate-500 hover:bg-slate-200/60"
            onClick={() => {
              onOpenChange(false);
              onCollapsedChange(true);
            }}
          >
            <PanelLeftClose />
            <span className="sr-only">收起侧边栏</span>
          </Button>
        </div>

        <div className="px-3 pb-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <input
              aria-label="搜索对话"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              className="h-10 w-full rounded-md border-0 bg-slate-200/55 pl-9 pr-9 text-sm outline-none placeholder:text-slate-400 focus:ring-2 focus:ring-slate-300"
              placeholder="搜索对话"
            />
            {query ? (
              <button
                type="button"
                aria-label="清除搜索"
                className="absolute right-2 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded text-slate-400 hover:bg-slate-300/60 hover:text-slate-600"
                onClick={() => onQueryChange('')}
              >
                <X className="size-3.5" />
              </button>
            ) : null}
          </div>
        </div>

        <nav
          aria-label="对话历史"
          className="min-h-0 flex-1 overflow-y-auto px-2"
        >
          <p className="px-2 pb-2 pt-3 text-sm font-medium text-slate-400">
            最近
          </p>
          {busy ? (
            <div className="flex items-center gap-2 px-2.5 py-3 text-sm text-slate-400">
              <Loader2 className="size-4 animate-spin" />
              正在读取对话…
            </div>
          ) : null}
          {!busy && visibleConversations.length === 0 ? (
            <p className="px-2.5 py-3 text-sm leading-6 text-slate-400">
              {error
                ? '暂时无法读取对话'
                : query
                  ? '没有匹配的对话'
                  : '还没有对话'}
            </p>
          ) : null}
          {visibleConversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`group mb-0.5 flex w-full items-center rounded-md text-sm ${selectedId === conversation.id ? 'bg-slate-200/70 text-slate-900' : 'text-slate-600 hover:bg-slate-200/45'}`}
            >
              <button
                type="button"
                disabled={running}
                onClick={() => onOpenConversation(conversation)}
                className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2.5 text-left disabled:cursor-not-allowed disabled:opacity-60"
                aria-current={
                  selectedId === conversation.id ? 'page' : undefined
                }
              >
                <MessageSquare className="size-4 shrink-0 text-slate-400" />
                <span className="min-w-0 flex-1 truncate">
                  {conversation.title}
                </span>
              </button>
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <button
                      type="button"
                      disabled={running}
                      aria-label={`管理对话：${conversation.title}`}
                      className="mr-1 grid size-8 shrink-0 place-items-center rounded text-slate-400 opacity-0 hover:bg-slate-300/60 hover:text-slate-600 focus-visible:opacity-100 disabled:pointer-events-none group-hover:opacity-100 data-popup-open:opacity-100"
                    />
                  }
                >
                  <MoreHorizontal className="size-4" />
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  side="right"
                  align="start"
                  className="w-36"
                >
                  <DropdownMenuItem onClick={() => onRename(conversation)}>
                    <Pencil />
                    重命名
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={() => onDelete(conversation)}
                  >
                    <Trash2 />
                    删除
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          ))}
        </nav>

        <div className="border-t border-slate-200 p-3">
          <button
            type="button"
            onClick={onOpenSettings}
            className="flex w-full items-center gap-3 rounded-md p-2 text-left hover:bg-slate-200/55"
          >
            <span className="grid size-8 place-items-center rounded-md bg-slate-800 text-sm font-medium text-white">
              管
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-slate-700">
                系统管理员
              </span>
              <span className="block text-xs text-slate-400">admin</span>
            </span>
            <Settings className="size-4 text-slate-400" />
          </button>
        </div>
      </aside>
    </>
  );
}
