import { createHash } from 'node:crypto';
import type { Context } from '@deepseek-ai/cordis';
import { assertObjectJsonSchema, type ToolRunContext } from '@deepseek-ai/dsh-tools';
import { BackendClient, BackendError } from './backend.js';

type CatalogTool = { id: string; name: string; original_name: string; description: string; parameters: any; risk_policy: string };
type Turn = { key: string; run?: Promise<Record<string, any>>; queue: Promise<unknown> };

// Harness enforces a smaller schema dialect. Bounds remain enforced by the MCP
// server; optional nullable branches are disjoint oneOf in its presentation.
export function harnessSchema(source: any): any {
  if (!source || typeof source !== 'object') return {};
  if (source.anyOf || source.oneOf) return { oneOf: (source.anyOf ?? source.oneOf).map(harnessSchema) };
  if (source.$ref || source.allOf) return {};
  const result: any = {};
  for (const key of ['type', 'description', 'title', 'default', 'examples', 'enum', 'const']) {
    if (source[key] !== undefined) result[key] = source[key];
  }
  if (source.type === 'object') {
    result.properties = Object.fromEntries(Object.entries(source.properties ?? {}).map(([key, node]) => [key, harnessSchema(node)]));
    result.required = source.required ?? [];
    result.additionalProperties = source.additionalProperties !== false;
  }
  if (source.type === 'array' && source.items) result.items = harnessSchema(source.items);
  return result;
}

export function nativeName(tool: CatalogTool) {
  const raw = `xiaoyi_${tool.name}`.replace(/[^A-Za-z0-9_-]/g, '_');
  return raw.length <= 64 ? raw : `${raw.slice(0, 51)}_${createHash('sha256').update(raw).digest('hex').slice(0, 12)}`;
}

export class NativeTools {
  private disposers: (() => void)[] = [];
  private turns = new Map<string, Turn>();
  private closing = false;
  constructor(private ctx: Context, private backend: BackendClient) {
    ctx.on('session/event', (session, event) => {
      if (event.type === 'turn/start') this.turns.set(session.id, { key: `${session.id}:${event.data.turn}`, queue: Promise.resolve() });
      if (event.type === 'turn/end') {
        const turn = this.turns.get(session.id);
        if (turn?.key === `${session.id}:${event.data.turn}`) {
          this.turns.delete(session.id);
          void this.closeTurn(turn, event.data.reason.kind !== 'completed').catch(() => ctx.logger.warn('原生工具审计记录结束失败，请检查后端连接。'));
        }
      }
    });
    ctx.effect(() => () => { this.closing = true; this.clear(); }, 'xiaoyi native tools');
  }

  get count() { return this.disposers.length; }
  clear() { for (const dispose of this.disposers.splice(0)) dispose(); }

  async refresh(signal?: AbortSignal) {
    const catalog = await this.backend.nativeData('/tools', undefined, signal);
    if (this.closing) throw new BackendError('PLUGIN_DISABLED', '插件已关闭', 409);
    const definitions = (catalog.items as CatalogTool[]).map(tool => {
      const parameters = harnessSchema(tool.parameters);
      // Identity and diagnosis memory are injected by the backend boundary.
      for (const key of ['memory_context', 'repair_context', 'owner_user_id', 'issued_by', 'correlation_key']) {
        delete parameters.properties[key];
        parameters.required = parameters.required.filter((name: string) => name !== key);
      }
      assertObjectJsonSchema(parameters);
      return { name: nativeName(tool), description: `小忆原生工具，直接返回结果，由 Harness 当前 DeepSeek 模型回答。${tool.description}${tool.risk_policy === 'proposal_only' ? ' 高风险动作仅创建提案，等待人类审批。' : ''}`,
        parameters: { ...parameters }, output: { schema: {}, render: (_args: unknown, value: unknown) => [{ type: 'text' as const, text: JSON.stringify(value) }] },
        execute: (args: unknown, exec: ToolRunContext) => this.call(tool, args, exec) };
    });
    this.clear();
    try { for (const definition of definitions) this.disposers.push(this.ctx.tools.register(definition)); }
    catch (error) { this.clear(); throw error; }
    return { native_tools: this.count, executor: 'deepseek-harness' };
  }

  private async call(tool: CatalogTool, args: unknown, exec: ToolRunContext) {
    const turn = exec.agent && this.turns.get(exec.agent.id);
    if (!turn) throw new BackendError('HARNESS_TURN_REQUIRED', '请在 Harness 主对话中开启新一轮消息后调用', 409);
    const work = turn.queue.catch(() => {}).then(async () => {
      exec.signal.throwIfAborted();
      turn.run ??= this.backend.nativeData('/runs', { context_key: turn.key }, exec.signal);
      const run = await turn.run;
      const result = await this.backend.nativeData(`/runs/${run.run_id}/call`, {
        tool_id: tool.id, arguments: args, call_id: exec.callId,
      }, exec.signal);
      return result.result;
    });
    turn.queue = work;
    return work;
  }

  private async closeTurn(turn: Turn, cancelled: boolean) {
    await turn.queue.catch(() => {});
    if (!turn.run || this.closing || !this.backend.status().connected) return;
    const run = await turn.run;
    await this.backend.nativeData(`/runs/${run.run_id}/close`, { cancelled });
  }
}
