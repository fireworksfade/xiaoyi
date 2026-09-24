import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  deleteAgentRun,
  deleteConversation,
  listConversationMessages,
  streamAgentRun,
  stopAgentRun,
} from '@/lib/api';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('api client', () => {
  beforeEach(() => {
    window.sessionStorage.setItem('xiaoyi.csrf-token', 'test-csrf');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  it('unwraps the success envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({
          data: {
            items: [
              { id: 'c1', title: '新对话', created_at: 't', updated_at: 't' },
            ],
          },
          request_id: 'req-1',
        }),
      ),
    );
    const data = await listConversationMessages('c1');
    expect(data.items).toHaveLength(1);
  });

  it('throws ApiError with the server error code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          {
            error: { code: 'CONVERSATION_NOT_FOUND', message: '会话不存在' },
            request_id: 'r',
          },
          404,
        ),
      ),
    );
    await expect(listConversationMessages('missing')).rejects.toMatchObject({
      code: 'CONVERSATION_NOT_FOUND',
      status: 404,
    });
  });

  it('falls back to HTTP_<status> for non-JSON error responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () => new Response('<html>bad gateway</html>', { status: 502 }),
      ),
    );
    await expect(listConversationMessages('c1')).rejects.toMatchObject({
      code: 'HTTP_502',
      status: 502,
    });
  });

  it('requires a CSRF token for mutating requests', async () => {
    window.sessionStorage.removeItem('xiaoyi.csrf-token');
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    await expect(deleteConversation('c1')).rejects.toMatchObject({
      code: 'CSRF_TOKEN_MISSING',
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('deletes an agent run with the CSRF-protected endpoint', async () => {
    const fetchSpy = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.toString()
              : input.url;
        expect(url).toContain('/agent-runs/run-1');
        expect(init?.method).toBe('DELETE');
        expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe(
          'test-csrf',
        );
        return jsonResponse({ data: { deleted: true, run_id: 'run-1' } });
      },
    );
    vi.stubGlobal('fetch', fetchSpy);

    await expect(deleteAgentRun('run-1')).resolves.toEqual({
      deleted: true,
      run_id: 'run-1',
    });
  });

  it('stops an agent run with the CSRF-protected endpoint', async () => {
    const fetchSpy = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        expect(url).toContain('/agent-runs/run-1/stop');
        expect(init?.method).toBe('POST');
        expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe(
          'test-csrf',
        );
        return jsonResponse({ data: { run_id: 'run-1', stopped: true } });
      },
    );
    vi.stubGlobal('fetch', fetchSpy);
    await expect(stopAgentRun('run-1')).resolves.toEqual({
      run_id: 'run-1',
      stopped: true,
    });
  });
});

function sseResponse(chunks: string[]) {
  const encoder = new TextEncoder();
  let index = 0;
  return new Response(
    new ReadableStream({
      pull(controller) {
        if (index < chunks.length) {
          controller.enqueue(encoder.encode(chunks[index]));
          index += 1;
        } else {
          controller.close();
        }
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  );
}

describe('SSE parser', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('parses events across chunk boundaries and skips comments', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse([
          'id: 1\nevent: run.started\ndata: {"id":1,"data":{}}\n\n: keep-alive\n\n',
          'id: 2\nevent: answer.delta\ndata: {"id":2,"data":{"text":"你"}}\n\ndata: {"id":3',
          ',"data":{}}\n\ndata: not-json\n\n',
        ]),
      ),
    );
    const events: unknown[] = [];
    await streamAgentRun('run-1', (event) => events.push(event));
    expect(events).toHaveLength(3);
    expect(events.map((event) => (event as { type: string }).type)).toEqual([
      'run.started',
      'answer.delta',
      'message',
    ]);
  });

  it('rejects when the stream response is not ok', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('nope', { status: 500 })),
    );
    await expect(streamAgentRun('run-1', () => {})).rejects.toMatchObject({
      code: 'EVENT_STREAM_FAILED',
    });
  });

  it('tolerates CRLF line endings', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        sseResponse([
          'id: 7\r\nevent: run.completed\r\ndata: {"id":7,"data":{}}\r\n\r\n',
        ]),
      ),
    );
    const events: unknown[] = [];
    await streamAgentRun('run-1', (event) => events.push(event));
    expect(events).toEqual([{ id: 7, type: 'run.completed', data: {} }]);
  });
});
