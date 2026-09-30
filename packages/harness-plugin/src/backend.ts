import { randomUUID } from 'node:crypto';

export interface PluginConfig {
  backendUrl: string;
  frontendUrl: string;
  instanceId: string;
  requestTimeoutMs: number;
}

export class BackendError extends Error {
  constructor(public code: string, message: string, public status = 502) { super(message); }
}

export function serviceUrl(value: string): string {
  const url = new URL(value);
  const local = ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname);
  if ((!local && url.protocol !== 'https:') || !['http:', 'https:'].includes(url.protocol) ||
      url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('服务地址须为本机 HTTP 或 HTTPS 地址，不含路径、凭据和查询参数。');
  }
  return url.origin;
}

export function apiPath(path: string): string {
  if (!/^\/(?:auth\/me|conversations|agent-runs|agent-tools|memories|knowledge-documents|remediation-proposals|model-config|mcp-servers|attachments)(?:[/?]|$)/.test(path) ||
      /[\\#\r\n]/.test(path) || /%2f|%5c|%2e/i.test(path) || path.split('?')[0].split('/').includes('..')) {
    throw new BackendError('PATH_NOT_ALLOWED', '不支持的业务接口', 400);
  }
  return path;
}

export class BackendClient {
  private cookie = '';
  private csrf = '';
  private user: { id: string; username: string; role: string } | null = null;
  private lifetime = new AbortController();
  private closing = false;
  private heartbeat?: ReturnType<typeof setInterval>;
  private heartbeatBusy = false;
  private inFlight = new Set<Promise<unknown>>();

  constructor(public readonly config: PluginConfig, private fetcher: typeof fetch = fetch) {
    config.backendUrl = serviceUrl(config.backendUrl);
    config.frontendUrl = serviceUrl(config.frontendUrl);
    if (!/^[A-Za-z0-9_-]{1,80}$/.test(config.instanceId)) throw new Error('instanceId 无效');
  }

  status() { return { connected: !!this.cookie, user: this.user, frontendUrl: this.config.frontendUrl, instanceId: this.config.instanceId }; }

  private track<T>(work: Promise<T>): Promise<T> {
    this.inFlight.add(work);
    void work.finally(() => this.inFlight.delete(work)).catch(() => {});
    return work;
  }

  async login(username: string, password: string, signal?: AbortSignal) {
    if (this.closing) throw new BackendError('PLUGIN_DISABLED', '插件已关闭', 409);
    if (!username || username.length > 64 || !password || password.length > 200) throw new BackendError('INVALID_LOGIN', '请填写有效账号和密码', 400);
    if (this.cookie) await this.logout();
    const response = await this.raw('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }, signal);
    const payload = await this.envelope(response);
    if (this.closing) throw new BackendError('PLUGIN_DISABLED', '插件已关闭', 409);
    const cookie = response.headers.getSetCookie().find(item => item.startsWith('xiaoyi_session='))?.split(';')[0];
    if (!cookie || typeof payload.csrf_token !== 'string') throw new BackendError('AUTH_PROTOCOL_ERROR', '后端登录协议不匹配');
    this.cookie = cookie;
    this.csrf = payload.csrf_token;
    this.user = payload.user;
    try {
      const caps = await this.envelope(await this.raw('/harness/capabilities', {}, signal));
      if (caps.protocol !== 1) throw new BackendError('BACKEND_UPGRADE_REQUIRED', '请升级小忆后端后重试');
      await this.activate(signal);
      this.heartbeat = setInterval(() => {
        if (this.heartbeatBusy || this.closing) return;
        this.heartbeatBusy = true;
        void this.raw(`/harness/connections/${this.config.instanceId}/heartbeat`, { method: 'POST', body: '{}' }).then(response => this.envelope(response)).catch(() => {}).finally(() => { this.heartbeatBusy = false; });
      }, 20000);
      this.heartbeat.unref();
      return this.status();
    } catch (error) { await this.logout().catch(() => {}); throw error; }
  }

  private async activate(signal?: AbortSignal) {
    return this.envelope(await this.raw(`/harness/connections/${this.config.instanceId}/activate`, { method: 'POST', body: '{}' }, signal));
  }

  private raw(path: string, init: RequestInit = {}, signal?: AbortSignal, cleanup = false): Promise<Response> {
    const signals: AbortSignal[] = path.endsWith('/events') ? [] : [AbortSignal.timeout(this.config.requestTimeoutMs)];
    if (!cleanup) signals.push(this.lifetime.signal);
    if (signal) signals.push(signal);
    const headers = new Headers(init.headers);
    if (this.cookie) headers.set('Cookie', this.cookie);
    if (this.csrf && init.method && !['GET', 'HEAD'].includes(init.method)) headers.set('X-CSRF-Token', this.csrf);
    if (typeof init.body === 'string') headers.set('Content-Type', 'application/json');
    return this.track(this.fetcher(`${this.config.backendUrl}/api/v1${path}`, {
      ...init, headers, redirect: 'error', signal: AbortSignal.any(signals),
    }));
  }

  request(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<Response> {
    apiPath(path);
    if (this.closing) throw new BackendError('PLUGIN_DISABLED', '插件已关闭', 409);
    if (!this.cookie) throw new BackendError('LOGIN_REQUIRED', '请先在小忆 IoT 面板登录', 401);
    const headers = new Headers(init.headers);
    // Credentials and integration identity are exclusively Host-owned.
    headers.delete('Cookie'); headers.delete('Authorization'); headers.delete('X-CSRF-Token');
    headers.set('X-Xiaoyi-Harness-Instance', this.config.instanceId);
    return this.raw(path, { ...init, headers }, signal);
  }

  async envelope(response: Response): Promise<Record<string, any>> {
    const payload = await response.json() as Record<string, any>;
    if (!response.ok) throw new BackendError(payload.error?.code ?? payload.detail ?? `HTTP_${response.status}`, payload.error?.message ?? '小忆后端请求失败', response.status);
    return payload.data;
  }

  async data(path: string, body?: unknown, signal?: AbortSignal) {
    return this.envelope(await this.request(path, body === undefined ? {} : { method: 'POST', body: JSON.stringify(body) }, signal));
  }

  async nativeData(path: string, body?: unknown, signal?: AbortSignal) {
    if (!/^\/(?:tools|runs(?:\/[A-Za-z0-9_-]{1,80}\/(?:call|close))?)$/.test(path)) throw new BackendError('PATH_NOT_ALLOWED', '原生工具接口无效', 400);
    if (this.closing) throw new BackendError('PLUGIN_DISABLED', '插件已关闭', 409);
    if (!this.cookie) throw new BackendError('LOGIN_REQUIRED', '请先在小忆 IoT 插件连接页登录', 401);
    return this.envelope(await this.raw(`/harness/native${path}`, {
      ...(body === undefined ? {} : { method: 'POST', body: JSON.stringify(body) }),
      headers: { 'X-Xiaoyi-Harness-Instance': this.config.instanceId },
    }, signal));
  }

  async startTask(content: string, conversationId?: string, signal?: AbortSignal) {
    if (!content.trim() || content.length > 20000) throw new BackendError('INVALID_TASK', '任务内容不能为空或超过 20000 字', 400);
    const conversation = conversationId ? { id: conversationId } : await this.data('/conversations', { title: content.slice(0, 40) }, signal);
    const result = await this.data(`/conversations/${encodeURIComponent(conversation.id)}/messages`, {
      content, client_message_id: `harness-${randomUUID()}`, tool_mode: 'auto',
    }, signal);
    return { ...result, conversation_id: conversation.id, message: '任务由小忆后端执行，高风险动作等待人工审批。使用 xiaoyi_task_status 查询结果。' };
  }

  async taskStatus(runId: string, signal?: AbortSignal) {
    const run = await this.data(`/agent-runs/${encodeURIComponent(runId)}`, undefined, signal);
    if (run.final_message_id) {
      const messages = await this.data(`/conversations/${encodeURIComponent(run.conversation_id)}/messages?limit=100`, undefined, signal);
      return { ...run, answer: messages.items.find((item: any) => item.id === run.final_message_id)?.content ?? null };
    }
    return run;
  }

  async logout() {
    if (this.heartbeat) clearInterval(this.heartbeat);
    if (this.cookie) {
      try {
        await this.envelope(await this.raw(`/harness/connections/${this.config.instanceId}/deactivate`, { method: 'POST', body: '{}' }, undefined, true));
        await this.raw('/auth/logout', { method: 'POST', body: '{}' }, undefined, true);
      } finally { this.cookie = ''; this.csrf = ''; this.user = null; }
    }
    return this.status();
  }

  async dispose() {
    this.closing = true;
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.lifetime.abort(new Error('PLUGIN_DISABLED'));
    await Promise.allSettled([...this.inFlight]);
    await this.logout();
  }
}
