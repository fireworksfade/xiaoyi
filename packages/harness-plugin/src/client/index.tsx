import type { Context } from '@deepseek-ai/cordis';
import type { ConnectionHandle } from '@deepseek-ai/dsh-client-connection/client';
import type {} from '@deepseek-ai/dsh-client-ui-layout/client';
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client';
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client';
import React, { useEffect, useRef, useState } from 'react';

export const inject = ['slots', 'layout', 'connection'];
const PANEL = 'xiaoyi-iot';
type Status = { connected: boolean; user: { username: string; role: string } | null; frontendUrl: string; instanceId: string; native_tools?: number };

async function rpc(connection: ConnectionHandle, endpoint: string, payload: unknown = {}, signal?: AbortSignal) {
  const result = await connection.rpc.call('/api', `xiaoyi-iot/${endpoint}`, payload, signal);
  if (!result.ok) throw new Error(result.error.message);
  return result.value;
}

function Icon() {
  return <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="5" y="5" width="14" height="14" rx="3"/><path d="M9 1v4m6-4v4M9 19v4m6-4v4M1 9h4m-4 6h4m14-6h4m-4 6h4"/><circle cx="12" cy="12" r="2"/></svg>;
}

function Panel({ connection }: { connection: ConnectionHandle }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showFrame, setShowFrame] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);
  const nonce = useRef(crypto.randomUUID());

  useEffect(() => {
    const abort = new AbortController();
    void rpc(connection, 'status', {}, abort.signal).then(value => setStatus(value as Status)).catch(err => { if (!abort.signal.aborted) setError(err.message); });
    return () => abort.abort();
  }, [connection]);

  useEffect(() => {
    if (!status?.connected) return;
    const active = new Set<AbortController>();
    const receive = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow || event.origin !== new URL(status.frontendUrl).origin || event.data?.type !== 'xiaoyi-harness-request' || event.data.nonce !== nonce.current) return;
      const port = event.ports[0];
      if (!port) return;
      const abort = new AbortController();
      active.add(abort);
      port.onmessage = msg => { if (msg.data?.type === 'cancel') abort.abort(); };
      port.start();
      void (async () => {
        const input = event.data.request;
        try {
          const match = typeof input.path === 'string' && input.path.match(/^\/agent-runs\/([A-Za-z0-9_-]{1,80})\/events$/);
          if (match && input.method === 'GET') {
            const response = await fetch(`api/xiaoyi-iot/events?run=${encodeURIComponent(match[1])}`, { credentials: 'include', signal: abort.signal });
            port.postMessage({ type: 'headers', status: response.status, headers: { 'Content-Type': response.headers.get('content-type') ?? 'text/event-stream' } });
            const reader = response.body?.getReader();
            if (reader) {
              try {
                while (!abort.signal.aborted) {
                  const item = await reader.read();
                  if (item.done) break;
                  // One acknowledged chunk bounds buffered data across the iframe boundary.
                  await new Promise<void>((resolve, reject) => {
                    const cancel = () => reject(new Error('cancelled'));
                    abort.signal.addEventListener('abort', cancel, { once: true });
                    port.onmessage = message => {
                      if (message.data?.type === 'cancel') abort.abort();
                      if (message.data?.type === 'ack') { abort.signal.removeEventListener('abort', cancel); resolve(); }
                    };
                    port.postMessage({ type: 'chunk', bytes: item.value }, [item.value.buffer]);
                  });
                }
              } finally { await reader.cancel().catch(() => {}); }
            }
          } else {
            const response = await rpc(connection, 'request', input, abort.signal) as { status: number; headers: Record<string, string>; body: string };
            port.postMessage({ type: 'headers', status: response.status, headers: response.headers });
            port.postMessage({ type: 'chunk', bytes: new TextEncoder().encode(response.body) });
          }
          port.postMessage({ type: 'end' });
        } catch (err) { port.postMessage({ type: 'error', message: err instanceof Error ? err.message : '请求失败' }); }
        finally { active.delete(abort); port.close(); }
      })();
    };
    window.addEventListener('message', receive);
    return () => { window.removeEventListener('message', receive); for (const abort of active) abort.abort(); };
  }, [connection, status]);

  async function login(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { setStatus(await rpc(connection, 'login', { username, password }) as Status); setPassword(''); }
    catch (err) { setError(err instanceof Error ? err.message : '登录失败'); }
    finally { setBusy(false); }
  }

  async function logout() {
    setBusy(true); setError('');
    try { setStatus(await rpc(connection, 'logout') as Status); }
    catch (err) { setError(err instanceof Error ? err.message : '退出失败'); }
    finally { setBusy(false); }
  }

  const url = status?.connected ? new URL(status.frontendUrl) : null;
  if (url) {
    url.searchParams.set('xiaoyi_harness_bridge', nonce.current);
    url.searchParams.set('xiaoyi_parent_origin', location.origin);
  }
  return <section style={{ height: '100%', display: 'flex', flexDirection: 'column', color: 'var(--text-primary, inherit)', background: 'var(--bg-primary, transparent)' }}>
    <header style={{ padding: '16px 20px', display: 'flex', gap: 16, alignItems: 'center', borderBottom: '1px solid #8883' }}>
      <Icon/><strong style={{ fontSize: 17 }}>小忆 IoT</strong>
      <span style={{ opacity: .7, flex: 1 }}>{status?.connected ? `主对话工具已连接 · ${status.user?.username} · ${status.native_tools ?? 0} 个工具` : '连接 Harness 主对话的设备、知识与记忆工具'}</span>
      {status?.connected && <button disabled={busy} onClick={() => void logout()} style={{ padding: '6px 12px', border: '1px solid #8885', borderRadius: 8 }}>退出连接</button>}
    </header>
    {error && <p role="alert" style={{ margin: 16, color: '#d05c4d' }}>{error}</p>}
    {url ? <>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid #8883' }}>
        <p>现在可以在 Harness 主对话直接询问设备、检索知识和记忆，由当前 DeepSeek 模型调用工具并回答。</p>
        <p style={{ opacity: .7, marginTop: 8 }}>例如：使用小忆工具列出设备，并检查 ESP32_05 的 MQTT 状态。高风险操作仍需人工审批。</p>
        <button onClick={() => setShowFrame(!showFrame)} style={{ padding: '8px 12px', marginTop: 12, border: '1px solid #8885', borderRadius: 8 }}>{showFrame ? '收起数据与审批面板' : '打开数据与审批面板'}</button>
        <button disabled={busy} onClick={() => { setBusy(true); void rpc(connection, 'refresh').then(value => setStatus(value as Status)).catch(err => setError(err.message)).finally(() => setBusy(false)); }} style={{ padding: '8px 12px', marginLeft: 12, border: '1px solid #8885', borderRadius: 8 }}>刷新主对话工具</button>
      </div>
      {showFrame && <iframe ref={frame} title="小忆 IoT 平台" src={url.href} sandbox="allow-scripts allow-same-origin allow-forms allow-downloads" style={{ flex: 1, width: '100%', border: 0, minHeight: 0 }}/>}
    </>
      : <div style={{ margin: 'auto', width: 'min(420px, 90%)', padding: 28, border: '1px solid #8883', borderRadius: 16 }}>
        <h2 style={{ fontSize: 23, marginBottom: 12 }}>连接小忆平台</h2>
        <p style={{ opacity: .7, lineHeight: 1.7, marginBottom: 24 }}>登录后会把设备、知识和记忆工具直接接入 Harness 主对话，由当前 DeepSeek 模型使用。数据与审批面板可按需打开。</p>
        <form onSubmit={event => void login(event)} style={{ display: 'grid', gap: 14 }}>
          <label>账号<input aria-label="小忆账号" autoComplete="username" required maxLength={64} value={username} onChange={event => setUsername(event.target.value)} style={inputStyle}/></label>
          <label>密码<input aria-label="小忆密码" autoComplete="current-password" required maxLength={200} type="password" value={password} onChange={event => setPassword(event.target.value)} style={inputStyle}/></label>
          <button disabled={busy || !status} style={{ padding: 12, border: 0, borderRadius: 8, background: '#147d72', color: '#fff' }}>{busy ? '正在连接…' : '连接平台'}</button>
        </form>
        <p style={{ marginTop: 20, fontSize: 12, opacity: .6 }}>在“插件”页关闭“小忆 IoT”，会停止关联任务并保留平台数据。</p>
      </div>}
  </section>;
}

const inputStyle: React.CSSProperties = { display: 'block', width: '100%', boxSizing: 'border-box', padding: 10, marginTop: 6, background: 'transparent', color: 'inherit', border: '1px solid #8885', borderRadius: 8 };

export function apply(ctx: Context) {
  // Host and Client Connection interfaces share a context key but live in distinct runtimes.
  const connection = ctx.connection as unknown as ConnectionHandle;
  ctx.slots.inject('main', () => ctx.slots.register({ name: 'main', key: PANEL }, () => <Panel connection={connection}/>));
  ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({ name: 'sidebar.panellist', id: PANEL, order: 20, label: '小忆 IoT' }, Icon));
}
