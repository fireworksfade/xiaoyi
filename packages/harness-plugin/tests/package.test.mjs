import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { Context } from '@deepseek-ai/cordis';
import { ToolRuntime } from '@deepseek-ai/dsh-tools';
import { HostConnectionService } from '@deepseek-ai/dsh-client-connection';
import * as plugin from '../lib/index.js';

test('installer recognizes the package as a Harness bundle', async () => {
  const manifest = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));
  assert.equal(manifest.dsh.bundle.patch, './cordis.patch.yml');
  const patch = await readFile(new URL(`../${manifest.dsh.bundle.patch}`, import.meta.url), 'utf8');
  assert.match(patch, /name: '@xiaoyi\/dsh-iot'/);
  assert.match(patch, /^- insert:/, 'a bundle must insert its new row, not override an absent id');
});

test('client is a lazy Harness module and uses the shared React runtime', async () => {
  const source = await readFile(new URL('../lib/client.js', import.meta.url), 'utf8');
  let definition;
  vm.runInNewContext(source, { window: { __ModuleLoader__: { load: value => { definition = value; } } } });
  assert.equal(definition.id, '@xiaoyi/dsh-iot');
  assert.equal(typeof definition.factory, 'function');
  const requests = [];
  const client = definition.factory(name => { requests.push(name); if (name === 'react') return { default: {}, useEffect() {}, useRef() {}, useState() {} }; throw new Error(`Unexpected client dependency ${name}`); });
  assert.equal(typeof client.apply, 'function');
  assert.deepEqual(requests, ['react']);
});

test('real Cordis and Connection coexist with the built-in gateway and unload only plugin routes', async () => {
  const ctx = new Context();
  ctx.reflect.provide('systemPrompt', { tools() {} });
  new HostConnectionService(ctx, [], { isAuthenticated: () => true });
  ctx.connection.rpc.intercept('/api', endpoint => endpoint === 'fixture/status', async () => ({ ok: true, value: 'gateway preserved' }));
  const handler = ctx.connection.createSharedFetchHandler('/api');
  const request = endpoint => new Request(`http://127.0.0.1/api/${endpoint}`, { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type: 'client-request', rpcId: 'test-rpc', method: endpoint, payload: {} }) });
  ctx.plugin(ToolRuntime, { mode: 'native' });
  const fiber = ctx.plugin(plugin, { backendUrl: 'http://127.0.0.1:8000', frontendUrl: 'http://127.0.0.1:3000', instanceId: 'test-desktop', requestTimeoutMs: 1000 });
  await fiber.await();
  assert.equal(ctx.tools.schemas().length, 2);
  assert.equal(ctx.tools.schemas().some(tool => tool.name === 'xiaoyi_task_start'), false);
  const result = await (await handler.fetch(request('xiaoyi-iot/status'))).json();
  assert.equal(result.result.value.connected, false);
  assert.equal((await (await handler.fetch(request('fixture/status'))).json()).result.value, 'gateway preserved');
  assert.equal((await handler.fetch(new Request('http://127.0.0.1/api/xiaoyi-iot/events'))).status, 400);
  await fiber.dispose();
  assert.equal(ctx.tools.schemas().length, 0);
  assert.equal((await handler.fetch(request('xiaoyi-iot/status'))).status, 404);
  assert.equal((await handler.fetch(new Request('http://127.0.0.1/api/xiaoyi-iot/events'))).status, 404);
  assert.equal((await (await handler.fetch(request('fixture/status'))).json()).result.value, 'gateway preserved');
  await ctx.fiber.dispose();
});
