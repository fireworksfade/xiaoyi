import type { Context } from '@deepseek-ai/cordis';
import z from '@deepseek-ai/schemastery';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { clientRequestSchema } from '@deepseek-ai/dsh-client-connection';
import { BackendClient, BackendError, type PluginConfig } from './backend.js';
import { NativeTools } from './native-tools.js';
export type { PluginConfig } from './backend.js';
export { BackendClient, BackendError, apiPath, serviceUrl } from './backend.js';
export { NativeTools, harnessSchema, nativeName } from './native-tools.js';

export const name = 'xiaoyi-iot';
export const inject = ['tools', 'connection'];
export const Config = z.object({
  backendUrl: z.string().default('http://127.0.0.1:8000'),
  frontendUrl: z.string().default('http://127.0.0.1:3000'),
  instanceId: z.string().default('xiaoyi-desktop'),
  requestTimeoutMs: z.number().min(1000).max(120000).default(30000),
});

function jsonOutput() {
  return { schema: { type: 'json' as const }, render: (_args: unknown, value: unknown) => [{ type: 'text' as const, text: JSON.stringify(value) }] };
}

export function apply(ctx: Context, config: PluginConfig) {
  const backend = new BackendClient({ ...config });
  const native = new NativeTools(ctx, backend);
  ctx.effect(() => async () => {
    try { await backend.dispose(); }
    catch { ctx.logger.warn('小忆后端连接清理失败；后端租约将在 90 秒内过期并停止关联任务。'); }
  }, 'xiaoyi backend lifecycle');

  const handleRpc = async (endpoint: string, raw: unknown, signal: AbortSignal) => {
    try {
      const input = (raw ?? {}) as Record<string, any>;
      let value: unknown;
      switch (endpoint) {
        case 'xiaoyi-iot/status': value = { ...backend.status(), native_tools: native.count }; break;
        case 'xiaoyi-iot/login': {
          await backend.login(input.username, input.password, signal);
          try { await native.refresh(signal); }
          catch (error) { await backend.logout().catch(() => {}); throw error; }
          value = { ...backend.status(), native_tools: native.count }; break;
        }
        case 'xiaoyi-iot/logout': native.clear(); value = await backend.logout(); break;
        case 'xiaoyi-iot/refresh': value = { ...backend.status(), ...await native.refresh(signal) }; break;
        case 'xiaoyi-iot/request': {
          if (typeof input.path !== 'string' || !['GET', 'POST', 'PATCH', 'DELETE'].includes(input.method)) throw new BackendError('INVALID_REQUEST', '请求格式无效', 400);
          let body: BodyInit | undefined;
          if (input.form) {
            body = new FormData();
            let bytes = 0;
            for (const entry of input.form) {
              if (entry.file) {
                const buffer = Buffer.from(entry.file.base64, 'base64');
                bytes += buffer.length;
                if (bytes > 20 * 1024 * 1024) throw new BackendError('UPLOAD_TOO_LARGE', '上传内容超过 20 MiB', 413);
                body.append(entry.name, new Blob([buffer], { type: entry.file.type }), entry.file.name);
              } else body.append(entry.name, entry.value);
            }
          } else if (input.body !== undefined) {
            if (typeof input.body !== 'string' || Buffer.byteLength(input.body) > 2 * 1024 * 1024) throw new BackendError('BODY_TOO_LARGE', '请求内容过大', 413);
            body = input.body;
          }
          const response = await backend.request(input.path, { method: input.method, body }, signal);
          value = { status: response.status, headers: { 'Content-Type': response.headers.get('content-type') ?? 'application/json' }, body: await response.text() };
          break;
        }
        default: throw new BackendError('NOT_FOUND', '接口不存在', 404);
      }
      return { ok: true, value };
    } catch (error) {
      return { ok: false, error: { code: error instanceof BackendError ? error.code : 'BACKEND_UNAVAILABLE', message: error instanceof BackendError ? error.message : '无法连接小忆服务，请检查服务状态。', details: {} } };
    }
  };

  // The built-in API gateway owns the single shared RPC interceptor. Exact
  // Connection Fetch routes coexist with it and retain its authentication fence.
  for (const endpoint of ['status', 'login', 'logout', 'request', 'refresh']) {
    ctx.effect(() => ctx.connection.fetch.register({
      path: `/api/xiaoyi-iot/${endpoint}`, methods: ['POST'], requestBody: 'buffered',
      fetch: async request => {
        let raw: unknown;
        try { raw = await request.json(); } catch { return new Response('Invalid JSON', { status: 400 }); }
        const parsed = clientRequestSchema.safeParse(raw);
        if (!parsed.success || parsed.data.method !== `xiaoyi-iot/${endpoint}`) return new Response('Invalid RPC envelope', { status: 400 });
        return Response.json({ type: 'server-response', rpcId: parsed.data.rpcId,
          result: await handleRpc(parsed.data.method, parsed.data.payload, request.signal) });
      },
    }), `xiaoyi authenticated RPC ${endpoint}`);
  }

  ctx.effect(() => ctx.connection.fetch.register({
    path: '/api/xiaoyi-iot/events', methods: ['GET'], requestBody: 'buffered',
    fetch: async request => {
      const run = new URL(request.url).searchParams.get('run');
      if (!run || !/^[A-Za-z0-9_-]{1,80}$/.test(run)) return new Response('Invalid run', { status: 400 });
      try {
        const upstream = await backend.request(`/agent-runs/${run}/events`, { headers: { 'Last-Event-ID': request.headers.get('Last-Event-ID') ?? '0' } }, request.signal);
        return new Response(upstream.body, { status: upstream.status, headers: { 'Content-Type': upstream.headers.get('content-type') ?? 'text/event-stream', 'Cache-Control': 'no-cache' } });
      } catch { return new Response('Backend unavailable', { status: 502 }); }
    },
  }), 'xiaoyi event stream route');

  const tools = [
    defineTool({ name: 'xiaoyi_connection_status', description: '查询小忆原生工具连接状态。先在插件连接页登录，再在 Harness 主对话中直接调用设备、知识与记忆工具；推理和回答由当前 DeepSeek 模型完成。',
      parameters: {}, output: jsonOutput(), execute: async () => ({ ...backend.status(), native_tools: native.count }) }),
    defineTool({ name: 'xiaoyi_refresh_tools', description: '登录后刷新 Harness 主对话可见的小忆原生工具目录。不会启动后端 Agent 或调用另一套模型。',
      parameters: {}, output: jsonOutput(), execute: (_args, exec) => native.refresh(exec.signal) }),
  ];
  for (const tool of tools) ctx.effect(() => ctx.tools.register(tool), `xiaoyi tool ${tool.name}`);
}
