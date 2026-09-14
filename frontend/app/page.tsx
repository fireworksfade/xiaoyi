'use client';

import { type SyntheticEvent, useEffect, useRef, useState } from 'react';
import {
  ArrowUp,
  BookOpen,
  Bot,
  ChevronDown,
  FileSearch,
  FileText,
  Gauge,
  History,
  Loader2,
  Menu,
  MessageSquare,
  MoreHorizontal,
  Paperclip,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Search,
  Settings,
  Sparkles,
  Trash2,
  Wrench,
  X,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { SettingsSheet } from '@/components/settings-sheet';
import { KnowledgeDialog } from '@/components/knowledge-dialog';
import { RunRecordsSheet } from '@/components/run-records-sheet';
import { MessageList } from '@/components/message-list';
import {
  useConversationMessages,
  type ChatMessage,
} from '@/hooks/use-conversation-messages';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  ApiError,
  createConversation,
  deleteConversation,
  ensureDemoSession,
  listAgentToolSources,
  listConversations,
  type Conversation,
  type RemediationProposal,
  type ToolSource,
  type UploadedAttachment,
  streamAgentRun,
  submitAgentMessage,
  updateConversation,
  uploadAttachment,
} from '@/lib/api';

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

function displayValue(value: unknown, fallback = '') {
  return ['string', 'number', 'boolean'].includes(typeof value)
    ? `${value as string | number | boolean}`
    : fallback;
}

function replaceMessageText(text: string) {
  return (message: ChatMessage): ChatMessage => ({ ...message, text });
}

export default function Home() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [input, setInput] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [conversationQuery, setConversationQuery] = useState('');
  const [conversationListBusy, setConversationListBusy] = useState(true);
  const [conversationBusy, setConversationBusy] = useState(false);
  const [conversationError, setConversationError] = useState<string | null>(
    null,
  );
  const [editingConversation, setEditingConversation] =
    useState<Conversation | null>(null);
  const [deletingConversation, setDeletingConversation] =
    useState<Conversation | null>(null);
  const [conversationTitleDraft, setConversationTitleDraft] = useState('');
  const [conversationActionBusy, setConversationActionBusy] = useState(false);
  const [conversationActionError, setConversationActionError] = useState<
    string | null
  >(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [knowledgeOpen, setKnowledgeOpen] = useState(false);
  const [runRecordsOpen, setRunRecordsOpen] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState<
    string | null
  >(null);
  const [running, setRunning] = useState(false);
  const [attachments, setAttachments] = useState<UploadedAttachment[]>([]);
  const [attachmentBusy, setAttachmentBusy] = useState(false);
  const [composerError, setComposerError] = useState<string | null>(null);
  const [toolSources, setToolSources] = useState<ToolSource[]>([]);
  const [toolSelection, setToolSelection] = useState('auto');
  const [toolMenuOpen, setToolMenuOpen] = useState(false);
  const [backendConversationId, setBackendConversationId] = useState<
    string | null
  >(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const messageSeedRef = useRef(0);
  const conversationLoadRef = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    messages,
    setMessages,
    hasMore,
    loadingEarlier,
    earlierError,
    loadLatest,
    loadEarlier,
    reset: resetMessages,
    skipAutoScrollRef,
  } = useConversationMessages({ scrollRef });

  const selectedConversationItem = conversations.find(
    (conversation) => conversation.id === selectedConversation,
  );
  const normalizedQuery = conversationQuery.trim().toLocaleLowerCase('zh-CN');
  const visibleConversations = normalizedQuery
    ? conversations.filter((conversation) =>
        conversation.title.toLocaleLowerCase('zh-CN').includes(normalizedQuery),
      )
    : conversations;

  async function refreshConversations(preferredId?: string | null) {
    const page = await listConversations();
    setConversations(page.items);
    const nextId = preferredId ?? selectedConversation;
    return (
      page.items.find((conversation) => conversation.id === nextId) ?? null
    );
  }

  async function openConversation(conversation: Conversation) {
    if (running) return;
    const loadId = conversationLoadRef.current + 1;
    conversationLoadRef.current = loadId;
    setSelectedConversation(conversation.id);
    setBackendConversationId(conversation.id);
    setConversationBusy(true);
    setConversationError(null);
    setAttachments([]);
    setComposerError(null);
    setSidebarOpen(false);
    resetMessages();
    try {
      await loadLatest(conversation.id);
      if (conversationLoadRef.current !== loadId) return;
    } catch (error) {
      if (conversationLoadRef.current !== loadId) return;
      setConversationError(
        error instanceof Error ? error.message : '无法读取这段对话',
      );
    } finally {
      if (conversationLoadRef.current === loadId) setConversationBusy(false);
    }
  }

  function beginRename(conversation: Conversation) {
    setEditingConversation(conversation);
    setConversationTitleDraft(conversation.title);
    setConversationActionError(null);
  }

  async function renameConversation(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    const title = conversationTitleDraft.trim();
    if (!editingConversation || !title || conversationActionBusy) return;
    setConversationActionBusy(true);
    setConversationActionError(null);
    try {
      await ensureDemoSession();
      const updated = await updateConversation(editingConversation.id, title);
      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === updated.id ? updated : conversation,
        ),
      );
      setEditingConversation(null);
    } catch (error) {
      setConversationActionError(
        error instanceof Error ? error.message : '无法重命名对话',
      );
    } finally {
      setConversationActionBusy(false);
    }
  }

  async function removeConversation() {
    if (!deletingConversation || conversationActionBusy) return;
    const target = deletingConversation;
    setConversationActionBusy(true);
    setConversationActionError(null);
    try {
      await ensureDemoSession();
      await deleteConversation(target.id);
      const remaining = conversations.filter(
        (conversation) => conversation.id !== target.id,
      );
      setConversations(remaining);
      setDeletingConversation(null);
      if (selectedConversation === target.id) {
        if (remaining[0]) {
          await openConversation(remaining[0]);
        } else {
          startNewChat();
        }
      }
    } catch (error) {
      setConversationActionError(
        error instanceof Error ? error.message : '无法删除对话',
      );
    } finally {
      setConversationActionBusy(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function loadConversationList() {
      setConversationListBusy(true);
      setConversationError(null);
      try {
        await ensureDemoSession();
        const page = await listConversations();
        if (cancelled) return;
        setConversations(page.items);
        const firstConversation = page.items[0];
        if (firstConversation) {
          setSelectedConversation(firstConversation.id);
          setBackendConversationId(firstConversation.id);
          setConversationBusy(true);
          resetMessages();
          await loadLatest(firstConversation.id);
          if (cancelled) return;
          setConversationBusy(false);
        }
      } catch (error) {
        if (!cancelled) {
          setConversationError(
            error instanceof Error ? error.message : '无法读取对话列表',
          );
        }
      } finally {
        if (!cancelled) {
          setConversationListBusy(false);
          setConversationBusy(false);
        }
      }
    }
    void loadConversationList();
    return () => {
      cancelled = true;
      conversationLoadRef.current += 1;
    };
  }, [loadLatest, resetMessages]);

  useEffect(() => {
    if (skipAutoScrollRef.current) {
      skipAutoScrollRef.current = false;
      return;
    }
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages, running, skipAutoScrollRef]);

  async function submitMessage(value = input) {
    const content = value.trim();
    if (!content || running) return;
    messageSeedRef.current += 1;
    const messageSeed = messageSeedRef.current;
    const assistantId = `assistant-${messageSeed}`;
    const submittedAttachments = attachments;
    const selectedServerId = toolSelection.startsWith('server:')
      ? toolSelection.slice('server:'.length)
      : null;
    setMessages((current) => [
      ...current,
      {
        id: `user-${messageSeed}`,
        role: 'user',
        text: content,
        attachments: submittedAttachments,
      },
    ]);
    setInput('');
    setAttachments([]);
    setComposerError(null);
    setRunning(true);
    let activeConversationId = backendConversationId;

    const updateAssistant = (update: (message: ChatMessage) => ChatMessage) => {
      setMessages((current) => {
        const index = current.findIndex(
          (message) => message.id === assistantId,
        );
        if (index === -1) {
          return [
            ...current,
            update({ id: assistantId, role: 'assistant', text: '' }),
          ];
        }
        return current.map((message, messageIndex) =>
          messageIndex === index ? update(message) : message,
        );
      });
    };

    try {
      await ensureDemoSession();
      let conversationId = backendConversationId;
      if (!conversationId) {
        const conversation = await createConversation();
        conversationId = conversation.id;
        activeConversationId = conversation.id;
        setBackendConversationId(conversationId);
        setSelectedConversation(conversationId);
        setConversations((current) => [
          { ...conversation, title: content.slice(0, 40) },
          ...current.filter((item) => item.id !== conversation.id),
        ]);
      }
      const { run_id: runId } = await submitAgentMessage(
        conversationId,
        content,
        {
          attachmentIds: submittedAttachments.map((item) => item.id),
          toolMode:
            toolSelection === 'none'
              ? 'none'
              : selectedServerId
                ? 'selected'
                : 'auto',
          mcpServerIds: selectedServerId ? [selectedServerId] : [],
        },
      );

      await streamAgentRun(runId, (event) => {
        if (event.type === 'answer.delta') {
          const delta = displayValue(event.data.delta);
          updateAssistant((message) => ({
            ...message,
            text: message.text + delta,
          }));
        }
        if (event.type === 'tool.started') {
          const toolName = displayValue(event.data.tool_name, '工具');
          updateAssistant((message) => ({
            ...message,
            tools: [
              ...(message.tools ?? []).filter((tool) => tool.name !== toolName),
              { name: toolName, result: '正在运行…' },
            ],
          }));
        }
        if (event.type === 'tool.finished') {
          const toolName = displayValue(event.data.tool_name, '工具');
          const result = displayValue(event.data.summary, '已完成');
          updateAssistant((message) => ({
            ...message,
            tools: [
              ...(message.tools ?? []).filter((tool) => tool.name !== toolName),
              { name: toolName, result },
            ],
          }));
        }
        if (event.type === 'remediation.proposal_created') {
          // 后端语义事件：载荷为后端定义的稳定结构，不再解析 MCP 信封
          const proposal = event.data.proposal as
            | RemediationProposal
            | undefined;
          if (proposal?.proposal_id) {
            updateAssistant((message) => ({
              ...message,
              proposals: [
                ...(message.proposals ?? []).filter(
                  (item) => item.proposal_id !== proposal.proposal_id,
                ),
                proposal,
              ],
            }));
          }
        }
        if (event.type === 'run.failed') {
          const error = event.data.error as
            | { message?: string }
            | null
            | undefined;
          throw new Error(error?.message ?? '小yi 运行失败');
        }
      });
    } catch (error) {
      const code = error instanceof ApiError ? `（${error.code}）` : '';
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      updateAssistant(
        replaceMessageText(`连接后端失败：${errorMessage}${code}`),
      );
    } finally {
      setRunning(false);
      try {
        await refreshConversations(activeConversationId);
      } catch {
        // The sent messages stay visible even if refreshing the history fails.
      }
    }
  }

  async function handleAttachment(file: File) {
    setAttachmentBusy(true);
    setComposerError(null);
    try {
      await ensureDemoSession();
      const uploaded = await uploadAttachment(file);
      setAttachments((current) => [...current, uploaded].slice(0, 5));
    } catch (error) {
      setComposerError(error instanceof Error ? error.message : '附件上传失败');
    } finally {
      setAttachmentBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function loadToolSources() {
    try {
      await ensureDemoSession();
      const page = await listAgentToolSources();
      setToolSources(page.items);
    } catch (error) {
      setComposerError(
        error instanceof Error ? error.message : '无法读取工具列表',
      );
    }
  }

  const toolSelectionLabel =
    toolSelection === 'none'
      ? '不使用工具'
      : toolSelection.startsWith('server:')
        ? (toolSources.find(
            (source) => source.id === toolSelection.slice('server:'.length),
          )?.name ?? '指定服务')
        : '工具自动选择';

  function startNewChat() {
    if (running) return;
    conversationLoadRef.current += 1;
    resetMessages();
    setBackendConversationId(null);
    setSelectedConversation(null);
    setConversationBusy(false);
    setConversationError(null);
    setAttachments([]);
    setComposerError(null);
    setSidebarOpen(false);
  }

  return (
    <main className="flex h-dvh min-h-[620px] overflow-hidden bg-white text-slate-800">
      {sidebarOpen ? (
        <button
          type="button"
          aria-label="关闭侧边栏"
          className="fixed inset-0 z-30 bg-slate-950/20 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[272px] shrink-0 flex-col border-r border-slate-200 bg-[#f7f7f8] transition-[transform,margin] duration-200 md:static ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} ${sidebarCollapsed ? 'md:-ml-[272px]' : 'md:ml-0'} md:translate-x-0`}
      >
        <div className="flex h-16 items-center gap-2 px-3">
          <Button
            variant="outline"
            className="h-10 flex-1 justify-start border-slate-300 bg-white px-3 text-slate-700 shadow-none hover:bg-slate-50"
            onClick={startNewChat}
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
              setSidebarOpen(false);
              setSidebarCollapsed(true);
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
              value={conversationQuery}
              onChange={(event) => setConversationQuery(event.target.value)}
              className="h-10 w-full rounded-md border-0 bg-slate-200/55 pl-9 pr-9 text-sm outline-none placeholder:text-slate-400 focus:ring-2 focus:ring-slate-300"
              placeholder="搜索对话"
            />
            {conversationQuery ? (
              <button
                type="button"
                aria-label="清除搜索"
                className="absolute right-2 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded text-slate-400 hover:bg-slate-300/60 hover:text-slate-600"
                onClick={() => setConversationQuery('')}
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
          {conversationListBusy ? (
            <div className="flex items-center gap-2 px-2.5 py-3 text-sm text-slate-400">
              <Loader2 className="size-4 animate-spin" />
              正在读取对话…
            </div>
          ) : null}
          {!conversationListBusy && visibleConversations.length === 0 ? (
            <p className="px-2.5 py-3 text-sm leading-6 text-slate-400">
              {conversationError
                ? '暂时无法读取对话'
                : conversationQuery
                  ? '没有匹配的对话'
                  : '还没有对话'}
            </p>
          ) : null}
          {visibleConversations.map((conversation) => (
            <div
              key={conversation.id}
              className={`group mb-0.5 flex w-full items-center rounded-md text-sm ${
                selectedConversation === conversation.id
                  ? 'bg-slate-200/70 text-slate-900'
                  : 'text-slate-600 hover:bg-slate-200/45'
              }`}
            >
              <button
                type="button"
                disabled={running}
                onClick={() => void openConversation(conversation)}
                className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2.5 text-left disabled:cursor-not-allowed disabled:opacity-60"
                aria-current={
                  selectedConversation === conversation.id ? 'page' : undefined
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
                  <DropdownMenuItem onClick={() => beginRename(conversation)}>
                    <Pencil />
                    重命名
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={() => {
                      setConversationActionError(null);
                      setDeletingConversation(conversation);
                    }}
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
            onClick={() => setSettingsOpen(true)}
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

      <section className="relative flex min-w-0 flex-1 flex-col bg-white">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 px-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-2">
            {sidebarCollapsed ? (
              <Button
                variant="ghost"
                size="icon"
                className="hidden text-slate-500 hover:bg-slate-100 md:inline-flex"
                onClick={() => setSidebarCollapsed(false)}
              >
                <PanelLeftOpen />
                <span className="sr-only">展开侧边栏</span>
              </Button>
            ) : null}
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu />
              <span className="sr-only">打开侧边栏</span>
            </Button>
            <button
              type="button"
              onClick={() => setSettingsOpen(true)}
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
              onClick={() => setRunRecordsOpen(true)}
            >
              <History />
              <span className="sr-only">运行记录</span>
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="border-slate-200 text-slate-600 shadow-none"
              onClick={() => setKnowledgeOpen(true)}
            >
              <BookOpen />
              <span className="hidden sm:inline">知识文档</span>
            </Button>
          </div>
        </header>

        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
          {conversationBusy ? (
            <div className="grid min-h-full place-items-center px-5 pb-24 text-sm text-slate-400">
              <span className="flex items-center gap-2">
                <Loader2 className="size-4 animate-spin" />
                正在加载对话…
              </span>
            </div>
          ) : conversationError && selectedConversation ? (
            <div className="mx-auto flex min-h-full max-w-md flex-col items-center justify-center px-5 pb-24 text-center">
              <p className="text-base font-medium text-slate-700">
                这段对话暂时打不开
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                {conversationError}
              </p>
              {selectedConversationItem ? (
                <Button
                  type="button"
                  variant="outline"
                  className="mt-4"
                  onClick={() =>
                    void openConversation(selectedConversationItem)
                  }
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
                    onClick={() => submitMessage(suggestion.prompt)}
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
                      {selectedConversationItem?.title ?? '新对话'}
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
                onLoadEarlier={() => void loadEarlier()}
              />
            </>
          )}
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-white via-white to-transparent px-4 pb-5 pt-12">
          <form
            className="pointer-events-auto mx-auto max-w-3xl"
            onSubmit={(event) => {
              event.preventDefault();
              void submitMessage();
            }}
          >
            <div className="rounded-xl border border-slate-300 bg-white p-2 shadow-[0_8px_30px_rgba(15,23,42,.08)] focus-within:border-slate-400">
              {attachments.length ? (
                <div className="flex flex-wrap gap-2 px-2 pb-2 pt-1">
                  {attachments.map((attachment) => (
                    <span
                      key={attachment.id}
                      className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs text-slate-600"
                    >
                      <FileText className="size-3.5 shrink-0" />
                      <span className="max-w-48 truncate">
                        {attachment.filename}
                      </span>
                      <button
                        type="button"
                        aria-label={`移除 ${attachment.filename}`}
                        className="rounded p-0.5 hover:bg-slate-200"
                        onClick={() =>
                          setAttachments((current) =>
                            current.filter((item) => item.id !== attachment.id),
                          )
                        }
                      >
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                </div>
              ) : null}
              <Textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    void submitMessage();
                  }
                }}
                placeholder="给小yi发送消息"
                className="max-h-36 min-h-12 resize-none border-0 bg-transparent px-2 py-2 text-[15px] shadow-none focus-visible:ring-0"
              />
              <div className="flex items-center justify-between px-1 pb-0.5">
                <div className="flex items-center gap-1">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
                    className="sr-only"
                    onChange={(event) => {
                      const file = event.target.files?.[0];
                      if (file) void handleAttachment(file);
                    }}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    disabled={attachmentBusy || attachments.length >= 5}
                    className="size-8 text-slate-500 hover:bg-slate-100"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {attachmentBusy ? (
                      <Loader2 className="animate-spin" />
                    ) : (
                      <Paperclip />
                    )}
                    <span className="sr-only">添加附件</span>
                  </Button>
                  <DropdownMenu
                    open={toolMenuOpen}
                    onOpenChange={(open) => {
                      setToolMenuOpen(open);
                      if (open) void loadToolSources();
                    }}
                  >
                    <DropdownMenuTrigger
                      render={
                        <button
                          type="button"
                          aria-label="选择本次消息使用的工具"
                          className="flex h-8 max-w-44 items-center gap-1.5 rounded-md px-2 text-xs text-slate-500 hover:bg-slate-100"
                        />
                      }
                    >
                      <Wrench className="size-3.5" />
                      <span className="truncate">{toolSelectionLabel}</span>
                      <ChevronDown className="size-3.5 shrink-0" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align="start"
                      side="top"
                      className="w-64"
                    >
                      <DropdownMenuRadioGroup
                        value={toolSelection}
                        onValueChange={(value) => {
                          setToolSelection(String(value));
                          setToolMenuOpen(false);
                        }}
                      >
                        <DropdownMenuLabel>
                          本次消息使用的工具
                        </DropdownMenuLabel>
                        <DropdownMenuRadioItem value="auto">
                          自动选择全部已授权工具
                        </DropdownMenuRadioItem>
                        <DropdownMenuRadioItem value="none">
                          不使用工具
                        </DropdownMenuRadioItem>
                        {toolSources.length ? <DropdownMenuSeparator /> : null}
                        {toolSources.map((source) => (
                          <DropdownMenuRadioItem
                            key={source.id}
                            value={`server:${source.id}`}
                          >
                            <span className="min-w-0 flex-1 truncate">
                              {source.name}
                            </span>
                            <span className="text-xs text-slate-400">
                              {source.tool_count}
                            </span>
                          </DropdownMenuRadioItem>
                        ))}
                      </DropdownMenuRadioGroup>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                <Button
                  type="submit"
                  size="icon"
                  disabled={!input.trim() || running}
                  className="size-8 rounded-md bg-slate-900 text-white hover:bg-slate-700"
                >
                  <ArrowUp />
                  <span className="sr-only">发送消息</span>
                </Button>
              </div>
            </div>
            {composerError ? (
              <p className="mt-2 text-center text-xs text-red-600">
                {composerError}
              </p>
            ) : null}
            <p className="mt-2 text-center text-[11px] text-slate-400">
              工具输出可能出错；受控操作需要人工审批。
            </p>
          </form>
        </div>
      </section>

      <Dialog
        open={Boolean(editingConversation)}
        onOpenChange={(open) => {
          if (!open && !conversationActionBusy) {
            setEditingConversation(null);
            setConversationActionError(null);
          }
        }}
      >
        <DialogContent>
          <form onSubmit={renameConversation}>
            <DialogHeader>
              <DialogTitle>重命名对话</DialogTitle>
              <DialogDescription>
                使用一个容易辨认的名称，方便之后继续处理。
              </DialogDescription>
            </DialogHeader>
            <Input
              value={conversationTitleDraft}
              maxLength={200}
              className="mt-4"
              aria-label="对话名称"
              onChange={(event) =>
                setConversationTitleDraft(event.target.value)
              }
            />
            {conversationActionError ? (
              <p className="mt-2 text-sm text-red-600">
                {conversationActionError}
              </p>
            ) : null}
            <DialogFooter className="mt-4">
              <Button
                type="button"
                variant="outline"
                disabled={conversationActionBusy}
                onClick={() => setEditingConversation(null)}
              >
                取消
              </Button>
              <Button
                type="submit"
                disabled={
                  !conversationTitleDraft.trim() || conversationActionBusy
                }
              >
                {conversationActionBusy ? (
                  <Loader2 className="animate-spin" />
                ) : null}
                保存
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(deletingConversation)}
        onOpenChange={(open) => {
          if (!open && !conversationActionBusy) {
            setDeletingConversation(null);
            setConversationActionError(null);
          }
        }}
      >
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>删除这段对话？</DialogTitle>
            <DialogDescription>
              “{deletingConversation?.title}”将从对话历史中移除。
            </DialogDescription>
          </DialogHeader>
          {conversationActionError ? (
            <p className="text-sm text-red-600">{conversationActionError}</p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={conversationActionBusy}
              onClick={() => setDeletingConversation(null)}
            >
              取消
            </Button>
            <Button
              type="button"
              disabled={conversationActionBusy}
              className="bg-red-600 text-white hover:bg-red-700"
              onClick={() => void removeConversation()}
            >
              {conversationActionBusy ? (
                <Loader2 className="animate-spin" />
              ) : null}
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <KnowledgeDialog open={knowledgeOpen} onOpenChange={setKnowledgeOpen} />

      <RunRecordsSheet open={runRecordsOpen} onOpenChange={setRunRecordsOpen} />

      <SettingsSheet open={settingsOpen} onOpenChange={setSettingsOpen} />
    </main>
  );
}
