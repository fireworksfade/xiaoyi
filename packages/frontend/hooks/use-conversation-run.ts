'use client';

import { useRef, useState, type Dispatch, type SetStateAction } from 'react';

import type { ChatMessage } from '@/hooks/use-conversation-messages';
import {
  ApiError,
  createConversation,
  ensureDemoSession,
  streamAgentRun,
  stopAgentRun,
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

class RunFailure extends Error {
  constructor(
    message: string,
    readonly code?: string,
  ) {
    super(message);
  }
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
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);
  const messageSeedRef = useRef(0);
  const activeRunIdRef = useRef<string | null>(null);
  const stopRequestedRef = useRef(false);
  const stopRequestStartedRef = useRef(false);

  async function requestStop(runId: string) {
    if (stopRequestStartedRef.current) return;
    stopRequestStartedRef.current = true;
    try {
      await stopAgentRun(runId);
    } catch (error) {
      if (activeRunIdRef.current !== runId) return;
      stopRequestStartedRef.current = false;
      stopRequestedRef.current = false;
      setStopping(false);
      if (!(error instanceof ApiError && error.code === 'RUN_NOT_ACTIVE')) {
        setStopError(
          error instanceof Error ? `停止失败：${error.message}` : '停止失败',
        );
      }
    }
  }

  function stop() {
    if (!running || stopRequestedRef.current) return;
    stopRequestedRef.current = true;
    setStopping(true);
    setStopError(null);
    if (activeRunIdRef.current) void requestStop(activeRunIdRef.current);
  }

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
    setStopError(null);
    activeRunIdRef.current = null;
    stopRequestedRef.current = false;
    stopRequestStartedRef.current = false;
    setStopping(false);
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
      activeRunIdRef.current = runId;
      if (stopRequestedRef.current) void requestStop(runId);

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
          const output =
            event.data.output && typeof event.data.output === 'object'
              ? (event.data.output as Record<string, unknown>)
              : undefined;
          // 超过内联阈值的输出被后端转存为 run_artifact，只留 artifact_id；
          // 未转存时 output 就是完整结果，展开时无需再请求。
          const artifactId =
            typeof output?.artifact_id === 'string' ? output.artifact_id : undefined;
          updateAssistant((message) => ({
            ...message,
            tools: [
              ...(message.tools ?? []).filter((tool) => tool.name !== toolName),
              {
                name: toolName,
                result,
                runId,
                artifactId,
                output: artifactId ? undefined : output,
              },
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
        if (event.type.startsWith('remediation.')) {
          const used = displayValue(
            event.data.used_attempts ?? event.data.used,
            '0',
          );
          const limit = displayValue(event.data.limit, '3');
          const counts = `已执行 ${used}/${limit} 次`;
          const reasons: Record<string, string> = {
            attempt_limit_reached: '修复次数已用尽',
            no_new_evidence: '没有新依据',
            run_finished: '任务已结束，需要发起后续诊断',
            run_deadline: '已达到运行期限',
            tool_budget: '已达到工具调用限制',
            device_recovered: '设备已恢复，自动修复已停止',
          };
          const status =
            event.type === 'remediation.rediagnosis_started'
              ? `正在重新诊断，${counts}`
              : event.type === 'remediation.rediagnosis_completed'
                ? `重新诊断完成，${counts}`
                : event.type === 'remediation.loop_stopped'
                  ? `${reasons[displayValue(event.data.reason)] ?? '自动修复已停止'}，${counts}`
                  : event.type === 'remediation.result_updated' &&
                      event.data.needs_followup
                    ? '修复失败；任务已结束，需要发起后续诊断'
                    : null;
          if (status)
            updateAssistant((message) => ({
              ...message,
              remediationStatus: status,
            }));
        }
        if (event.type === 'run.failed') {
          const error = event.data.error as
            | { code?: string; message?: string }
            | null
            | undefined;
          throw new RunFailure(error?.message ?? '小yi运行失败', error?.code);
        }
      });
    } catch (error) {
      if (error instanceof RunFailure) {
        if (error.code === 'RUN_STOPPED') {
          updateAssistant((current) => ({
            ...current,
            text: current.text ? `${current.text}\n\n已停止生成` : '已停止生成',
            tools: current.tools?.map((tool) =>
              tool.result === '正在运行…'
                ? { ...tool, result: '未完成' }
                : tool,
            ),
          }));
          return true;
        }
        const message = error.message;
        updateAssistant((current) => ({
          ...current,
          text: `小yi运行失败：${message}${error.code ? `（${error.code}）` : ''}`,
          tools: current.tools?.map((tool) =>
            tool.result === '正在运行…' ? { ...tool, result: '未完成' } : tool,
          ),
        }));
      } else {
        const code = error instanceof ApiError ? `（${error.code}）` : '';
        const errorMessage =
          error instanceof Error ? error.message : '未知错误';
        updateAssistant(
          replaceMessageText(`连接后端失败：${errorMessage}${code}`),
        );
      }
    } finally {
      activeRunIdRef.current = null;
      stopRequestedRef.current = false;
      stopRequestStartedRef.current = false;
      setStopping(false);
      setRunning(false);
      try {
        await onFinished(activeConversationId);
      } catch {
        // Optimistic messages stay visible if refreshing the sidebar fails.
      }
    }
    return true;
  }

  return { running, stopping, stopError, submit, stop };
}
