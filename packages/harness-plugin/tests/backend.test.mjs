import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { BackendClient, apiPath, serviceUrl } from '../lib/index.js';

async function fixture(t) {
  const calls = [];
  const server = createServer(async (req, res) => {
    let text = ''; for await (const part of req) text += part;
    const data = text ? JSON.parse(text) : null;
    calls.push({ url: req.url, headers: req.headers, data });
    if (req.url.endsWith('/events')) {
      res.setHeader('Content-Type', 'text/event-stream');
      res.flushHeaders();
      const timer = setTimeout(() => res.write('data: {"connected":true}\n\n'), 1100);
      res.on('close', () => clearTimeout(timer));
      return;
    }
    res.setHeader('Content-Type', 'application/json');
    let value = {};
    if (req.url.endsWith('/auth/login')) {
      res.setHeader('Set-Cookie', 'xiaoyi_session=test-secret; HttpOnly; SameSite=Lax');
      value = { csrf_token: 'test-csrf', user: { id: 'owner', username: data.username, role: 'operator' } };
    } else {
      assert.equal(req.headers.cookie, 'xiaoyi_session=test-secret');
      if (req.method === 'POST') assert.equal(req.headers['x-csrf-token'], 'test-csrf');
      if (req.url.endsWith('/capabilities')) value = { protocol: 1 };
      else if (req.url.endsWith('/conversations')) value = { id: 'conversation-1' };
      else if (req.url.endsWith('/messages')) value = { run_id: 'run-1' };
      else if (req.url.endsWith('/agent-runs/run-1')) value = { id: 'run-1', conversation_id: 'conversation-1', status: 'running' };
      else if (req.url.endsWith('/deactivate')) value = { stopped_run_ids: ['run-1'] };
    }
    res.end(JSON.stringify({ data: value }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const backend = new BackendClient({ backendUrl: `http://127.0.0.1:${server.address().port}`, frontendUrl: 'http://127.0.0.1:3000', instanceId: 'test-desktop', requestTimeoutMs: 1000 });
  t.after(() => backend.dispose().catch(() => {}));
  return { backend, calls };
}

test('credentials stay Host-owned, tasks carry plugin identity, and dispose revokes the lease', async t => {
  const { backend, calls } = await fixture(t);
  await backend.login('operator', 'password');
  assert.equal(backend.status().connected, true);
  assert.equal(JSON.stringify(backend.status()).includes('test-secret'), false);
  const task = await backend.startTask('排查离线设备');
  assert.equal(task.run_id, 'run-1');
  const submit = calls.find(call => call.url.endsWith('/messages'));
  assert.equal(submit.headers['x-xiaoyi-harness-instance'], 'test-desktop');
  assert.equal(submit.data.tool_mode, 'auto');
  assert.match(submit.data.client_message_id, /^harness-/);
  await backend.request('/auth/me', { headers: { Cookie: 'attacker', Authorization: 'attacker', 'X-CSRF-Token': 'attacker' } });
  assert.equal(calls.at(-1).headers.authorization, undefined);
  await backend.dispose();
  assert.equal(backend.status().connected, false);
  assert.equal(calls.filter(call => call.url.endsWith('/deactivate')).length, 1);
  assert.throws(() => backend.request('/memories'), /插件已关闭/);
});

test('API bridge refuses absolute URLs, traversal, authentication writes and lifecycle controls', () => {
  for (const path of ['https://example.com', '//example.com', '/memories/../auth/login', '/memories/%2e%2e/auth/login', '/auth/login', '/harness/connections/test/activate', '/memories\\auth', '/memories#x']) assert.throws(() => apiPath(path));
  assert.equal(apiPath('/memories/search'), '/memories/search');
  assert.throws(() => serviceUrl('http://example.com'));
  assert.throws(() => serviceUrl('http://user:password@127.0.0.1'));
});

test('an unauthenticated plugin cannot start backend work', async t => {
  const { backend, calls } = await fixture(t);
  await assert.rejects(backend.startTask('排查设备'), error => error.code === 'LOGIN_REQUIRED');
  assert.equal(calls.length, 0);
});

test('SSE survives the ordinary request deadline and is aborted on unload', async t => {
  const { backend } = await fixture(t);
  await backend.login('operator', 'password');
  const response = await backend.request('/agent-runs/run-1/events');
  const reader = response.body.getReader();
  const first = await reader.read();
  assert.match(new TextDecoder().decode(first.value), /connected/);
  const pending = reader.read();
  const rejected = assert.rejects(pending, error => error.message === 'PLUGIN_DISABLED' || error.name === 'AbortError');
  await backend.dispose();
  await rejected;
});
