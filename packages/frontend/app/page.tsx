'use client';

import { type SyntheticEvent, useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConversationSidebar } from '@/features/conversation/conversation-sidebar';
import { ConversationView } from '@/features/conversation/conversation-view';
import { MessageComposer } from '@/features/conversation/message-composer';
import { SettingsSheet } from '@/features/settings/settings-sheet';
import { KnowledgeDialog } from '@/features/knowledge/knowledge-dialog';
import { RunRecordsSheet } from '@/components/run-records-sheet';
import { useConversationMessages } from '@/hooks/use-conversation-messages';
import { useAttachmentDraft } from '@/hooks/use-attachment-draft';
import { useConversationList } from '@/hooks/use-conversation-list';
import { useConversationRun } from '@/hooks/use-conversation-run';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  deleteConversation,
  ensureDemoSession,
  listAgentToolSources,
  type Conversation,
  type ToolSource,
  updateConversation,
} from '@/lib/api';

export default function Home() {
  const [input, setInput] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [conversationQuery, setConversationQuery] = useState('');
  const [conversationBusy, setConversationBusy] = useState(false);
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
  const [toolSources, setToolSources] = useState<ToolSource[]>([]);
  const [toolSelection, setToolSelection] = useState('auto');
  const [toolMenuOpen, setToolMenuOpen] = useState(false);
  const [backendConversationId, setBackendConversationId] = useState<
    string | null
  >(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const conversationLoadRef = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    conversations,
    setConversations,
    busy: conversationListBusy,
    setBusy: setConversationListBusy,
    error: conversationError,
    setError: setConversationError,
    load: loadConversationList,
    refresh: refreshConversationList,
  } = useConversationList();
  const {
    attachments,
    setAttachments,
    busy: attachmentBusy,
    error: composerError,
    setError: setComposerError,
    upload: uploadDraftAttachment,
    remove: removeDraftAttachment,
  } = useAttachmentDraft(fileInputRef);
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
  const {
    running,
    stopping,
    stopError,
    stop: stopConversationRun,
    submit: submitConversationRun,
  } = useConversationRun({
    conversationId: backendConversationId,
    attachments,
    toolSelection,
    setMessages,
    clearAttachments: () => setAttachments([]),
    clearComposerError: () => setComposerError(null),
    onConversationCreated: (conversation) => {
      setBackendConversationId(conversation.id);
      setSelectedConversation(conversation.id);
      setConversations((current) => [
        conversation,
        ...current.filter((item) => item.id !== conversation.id),
      ]);
    },
    onFinished: async (conversationId) => {
      await refreshConversations(conversationId);
    },
  });

  const selectedConversationItem = conversations.find(
    (conversation) => conversation.id === selectedConversation,
  );
  async function refreshConversations(preferredId?: string | null) {
    return refreshConversationList(preferredId ?? selectedConversation);
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
    async function initializeConversations() {
      setConversationListBusy(true);
      setConversationError(null);
      try {
        await ensureDemoSession();
        const items = await loadConversationList();
        if (cancelled) return;
        const firstConversation = items[0];
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
    void initializeConversations();
    return () => {
      cancelled = true;
      conversationLoadRef.current += 1;
    };
  }, [
    loadConversationList,
    loadLatest,
    resetMessages,
    setConversationError,
    setConversationListBusy,
  ]);

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
    setInput('');
    await submitConversationRun(content);
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
      <ConversationSidebar
        open={sidebarOpen}
        collapsed={sidebarCollapsed}
        busy={conversationListBusy}
        running={running}
        error={conversationError}
        query={conversationQuery}
        conversations={conversations}
        selectedId={selectedConversation}
        onOpenChange={setSidebarOpen}
        onCollapsedChange={setSidebarCollapsed}
        onQueryChange={setConversationQuery}
        onNewChat={startNewChat}
        onOpenConversation={(conversation) =>
          void openConversation(conversation)
        }
        onRename={beginRename}
        onDelete={(conversation) => {
          setConversationActionError(null);
          setDeletingConversation(conversation);
        }}
        onOpenSettings={() => setSettingsOpen(true)}
      />

      <ConversationView
        sidebarCollapsed={sidebarCollapsed}
        conversation={selectedConversationItem ?? null}
        selectedId={selectedConversation}
        messages={messages}
        running={running}
        busy={conversationBusy}
        error={conversationError}
        hasMore={hasMore}
        loadingEarlier={loadingEarlier}
        earlierError={earlierError}
        scrollRef={scrollRef}
        onExpandSidebar={() => setSidebarCollapsed(false)}
        onOpenSidebar={() => setSidebarOpen(true)}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenRunRecords={() => setRunRecordsOpen(true)}
        onOpenKnowledge={() => setKnowledgeOpen(true)}
        onRetryConversation={() => {
          if (selectedConversationItem)
            void openConversation(selectedConversationItem);
        }}
        onLoadEarlier={() => void loadEarlier()}
        onSuggestion={(prompt) => void submitMessage(prompt)}
        composer={
          <MessageComposer
            input={input}
            running={running}
            stopping={stopping}
            attachments={attachments}
            attachmentBusy={attachmentBusy}
            error={stopError ?? composerError}
            fileInputRef={fileInputRef}
            toolSources={toolSources}
            toolSelection={toolSelection}
            toolMenuOpen={toolMenuOpen}
            onInputChange={setInput}
            onSubmit={() => void submitMessage()}
            onStop={stopConversationRun}
            onFile={(file) => void uploadDraftAttachment(file)}
            onRemoveAttachment={removeDraftAttachment}
            onToolMenuOpenChange={(open) => {
              setToolMenuOpen(open);
              if (open) void loadToolSources();
            }}
            onToolSelectionChange={(value) => {
              setToolSelection(value);
              setToolMenuOpen(false);
            }}
          />
        }
      />

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
