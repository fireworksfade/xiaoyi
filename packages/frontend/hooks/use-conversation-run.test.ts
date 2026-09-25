import { useState } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useConversationRun } from '@/hooks/use-conversation-run';
import type { ChatMessage } from '@/hooks/use-conversation-messages';

function sse(body: string) {
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function setupHook(onFinished = vi.fn(async () => {})) {
  return renderHook(() => {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const run = useConversationRun({
      conversationId: 'c1',
      attachments: [],
      toolSelection: 'auto',
      setMessages,
      clearAttachments: vi.fn(),
      clearComposerError: vi.fn(),
      onConversationCreated: vi.fn(),
      onFinished,
    });
    return { messages, ...run };
  });
}

describe('useConversationRun', () => {
  beforeEach(() => window.sessionStorage.setItem('xiaoyi.csrf-token', 'csrf'));
  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  it('streams answer and tool state into the optimistic conversation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string) => {
        if (input.endsWith('/auth/me')) {
          return Response.json({ data: { id: 'u1' }, request_id: 'r' });
        }
        if (input.includes('/messages')) {
          return Response.json({ data: { run_id: 'run-1' }, request_id: 'r' });
        }
        return sse(
          'event: tool.started\ndata: {"id":1,"data":{"tool_name":"inspect"}}\n\n' +
            'event: answer.delta\ndata: {"id":2,"data":{"delta":"完成"}}\n\n' +
            'event: tool.finished\ndata: {"id":3,"data":{"tool_name":"inspect","summary":"正常"}}\n\n',
        );
      }),
    );
    const finished = vi.fn(async () => {});
    const { result } = setupHook(finished);

    await act(async () => {
      await result.current.submit('检查设备');
    });

    expect(result.current.messages.map((message) => message.text)).toEqual([
      '检查设备',
      '完成',
    ]);
    expect(result.current.messages[1].tools).toEqual([
      { name: 'inspect', result: '正常' },
    ]);
    expect(result.current.running).toBe(false);
    expect(finished).toHaveBeenCalledWith('c1');
  });

  it.each(['MCP_CAPABILITY_AMBIGUOUS', 'MCP_CAPABILITY_UNAVAILABLE'])(
    'shows capability routing error %s without losing the user message',
    async (code) => {
      vi.stubGlobal(
        'fetch',
        vi.fn(async (input: string) => {
          if (input.endsWith('/auth/me')) {
            return Response.json({ data: { id: 'u1' }, request_id: 'r' });
          }
          return Response.json(
            { error: { code, message: '工具服务不可用' }, request_id: 'r' },
            { status: 409 },
          );
        }),
      );
      const { result } = setupHook();

      await act(async () => {
        await result.current.submit('排查问题');
      });

      expect(result.current.messages[0].text).toBe('排查问题');
      expect(result.current.messages[1].text).toContain(code);
      expect(result.current.messages[1].text).toContain('工具服务不可用');
    },
  );

  it('restores an interrupted run as a retryable failure message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string) => {
        if (input.endsWith('/auth/me')) {
          return Response.json({ data: { id: 'u1' }, request_id: 'r' });
        }
        if (input.includes('/messages')) {
          return Response.json({ data: { run_id: 'run-2' }, request_id: 'r' });
        }
        return sse(
          'event: tool.started\ndata: {"id":3,"data":{"tool_name":"get_action_result"}}\n\n' +
            'event: run.failed\ndata: {"id":4,"data":{"error":{"code":"RUN_INTERRUPTED","message":"运行因服务重启中断","retryable":true}}}\n\n',
        );
      }),
    );
    const { result } = setupHook();
    await act(async () => {
      await result.current.submit('继续诊断');
    });
    expect(result.current.messages.at(-1)?.text).toContain(
      '运行因服务重启中断',
    );
    expect(result.current.messages.at(-1)?.text).not.toContain('连接后端失败');
    expect(result.current.messages.at(-1)?.tools).toEqual([
      { name: 'get_action_result', result: '未完成' },
    ]);
  });

  it('shows a workflow evidence failure as a run failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string) => {
        if (input.endsWith('/auth/me')) {
          return Response.json({ data: { id: 'u1' }, request_id: 'r' });
        }
        if (input.includes('/messages')) {
          return Response.json({ data: { run_id: 'run-3' }, request_id: 'r' });
        }
        return sse(
          'event: run.failed\ndata: {"id":4,"data":{"error":{"code":"REQUIRED_EVIDENCE_MISSING","message":"小yi运行失败"}}}\n\n',
        );
      }),
    );
    const { result } = setupHook();
    await act(async () => {
      await result.current.submit('检查命令');
    });
    expect(result.current.messages.at(-1)?.text).toContain(
      '缺少当前工作流所需的诊断证据',
    );
    expect(result.current.messages.at(-1)?.text).toContain(
      'REQUIRED_EVIDENCE_MISSING',
    );
  });

  it('stops the active run and keeps text already streamed', async () => {
    const encoder = new TextEncoder();
    let streamController!: ReadableStreamDefaultController<Uint8Array>;
    const stopRequests: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string) => {
        if (input.endsWith('/auth/me')) {
          return Response.json({ data: { id: 'u1' }, request_id: 'r' });
        }
        if (input.includes('/messages')) {
          return Response.json({
            data: { run_id: 'run-stop' },
            request_id: 'r',
          });
        }
        if (input.endsWith('/stop')) {
          stopRequests.push(input);
          streamController.enqueue(
            encoder.encode(
              'event: run.failed\ndata: {"id":2,"data":{"error":{"code":"RUN_STOPPED","message":"用户已停止运行"}}}\n\n',
            ),
          );
          streamController.close();
          return Response.json({
            data: { run_id: 'run-stop', stopped: true },
            request_id: 'r',
          });
        }
        return new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              streamController = controller;
              controller.enqueue(
                encoder.encode(
                  'event: answer.delta\ndata: {"id":1,"data":{"delta":"已完成一半"}}\n\n',
                ),
              );
            },
          }),
          { headers: { 'Content-Type': 'text/event-stream' } },
        );
      }),
    );
    const { result } = setupHook();
    let submitted!: Promise<boolean>;
    act(() => {
      submitted = result.current.submit('诊断设备');
    });
    await waitFor(() =>
      expect(result.current.messages.at(-1)?.text).toBe('已完成一半'),
    );
    act(() => result.current.stop());
    await act(async () => {
      await submitted;
    });
    expect(stopRequests).toHaveLength(1);
    expect(result.current.messages.at(-1)?.text).toBe(
      '已完成一半\n\n已停止生成',
    );
    expect(result.current.running).toBe(false);
  });
});
