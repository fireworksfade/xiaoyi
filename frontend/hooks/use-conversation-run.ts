'use client';

import { useRef, useState, type Dispatch, type SetStateAction } from 'react';

import type { ChatMessage } from '@/hooks/use-conversation-messages';
import {
  ApiError,
  createConversation,
  ensureDemoSession,
  streamAgentRun,
  submitAgentMessage,
  type Conversation,
  type RemediationProposal,
  type UploadedAttachment,
} from '@/lib/api';

type UseConversationRunOptions = {
  conversationId: string | null;
  attachments: UploadedAttachment[];
  toolSelection: string;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  clearAttachments: () => void;
  clearComposerError: () => void;
  onConversationCreated: (conversation: Conversation) => void;
  onFinished: (conversationId: string | null) => Promise<void>;
};

function displayValue(value: unknown, fallback = '') {
  return ['string', 'number', 'boolean'].includes(typeof value)
    ? `${value as string | number | boolean}`
    : fallback;
}

function replaceMessageText(text: string) {
  return (message: ChatMessage): ChatMessage => ({ ...message, text });
}

export function useConversationRun({
  conversationId: initialConversationId,
  attachments,
  toolSelection,
  setMessages,
  clearAttachments,
  clearComposerError,
  onConversationCreated,
  onFinished,
}: UseConversationRunOptions) {
  const [running, setRunning] = useState(false);
  const messageSeedRef = useRef(0);

  async function submit(value: string) {
    const content = value.trim();
    if (!content || running) return false;
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
    clearAttachments();
    clearComposerError();
    setRunning(true);
    let activeConversationId = initialConversationId;

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
      let conversationId = initialConversationId;
      if (!conversationId) {
        const conversation = await createConversation();
        conversationId = conversation.id;
        activeConversationId = conversation.id;
        onConversationCreated({ ...conversation, title: content.slice(0, 40) });
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
        await onFinished(activeConversationId);
      } catch {
        // Optimistic messages stay visible if refreshing the sidebar fails.
      }
    }
    return true;
  }

  return { running, submit };
}
