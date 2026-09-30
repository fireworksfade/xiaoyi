import test from 'node:test';
import assert from 'node:assert/strict';
import { Context } from '@deepseek-ai/cordis';
import { ToolRuntime, assertObjectJsonSchema } from '@deepseek-ai/dsh-tools';
import { NativeTools, harnessSchema } from '../lib/index.js';

test('native schema converts nullable inputs and leaves constraints to the backend MCP validator', () => {
  const schema = harnessSchema({ type: 'object', properties: {
    device_id: { type: 'string', maxLength: 120 },
    logs: { anyOf: [{ type: 'array', items: { type: 'string' } }, { type: 'null' }], default: null },
  }, required: ['device_id'] });
  assertObjectJsonSchema(schema);
  assert.equal(schema.properties.device_id.type, 'string');
  assert.equal(schema.properties.logs.oneOf[1].type, 'null');
});

test('main-chat tools go directly to native calls, keep turns isolated, close the audit, and unregister', async () => {
  const ctx = new Context();
  ctx.reflect.provide('systemPrompt', { tools() {} });
  const runtime = ctx.plugin(ToolRuntime, { mode: 'native' });
  await runtime.await();
  const calls = [];
  const backend = { status: () => ({ connected: true }), nativeData: async (path, body, signal) => {
    calls.push({ path, body, signal });
    if (path === '/tools') return { items: [{ id: 'device-tool', name: 'iot__list_devices', original_name: 'list_devices',
      description: '列出设备', risk_policy: 'read_only', parameters: { type: 'object', properties: {} } }] };
    if (path === '/runs') return { run_id: `run-${calls.length}` };
    return { result: { ok: true, data: { devices: ['ESP32_01'] } } };
  }};
  const native = new NativeTools(ctx, backend);
  await native.refresh();
  assert.equal(ctx.tools.schemas()[0].name, 'xiaoyi_iot__list_devices');
  const tool = ctx.tools.get('xiaoyi_iot__list_devices');
  assert.ok(tool);
  const signal = new AbortController().signal;
  ctx.emit('session/event', { id: 'main-chat' }, { type: 'turn/start', data: { turn: 1 } });
  const result = await tool.execute({}, { agent: { id: 'main-chat' }, callId: 'call-1', signal });
  assert.equal(result.data.devices[0], 'ESP32_01');
  assert.deepEqual(calls.find(c => c.path === '/runs').body, { context_key: 'main-chat:1' });
  assert.equal(calls.some(c => /messages|agent-runs/.test(c.path)), false, 'no backend Agent is started');
  assert.equal(calls.at(-1).body.call_id, 'call-1');
  ctx.emit('session/event', { id: 'main-chat' }, { type: 'turn/end', data: { turn: 1, reason: { kind: 'completed' } } });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(calls.at(-1).path.endsWith('/close'), true);
  ctx.emit('session/event', { id: 'other-chat' }, { type: 'turn/start', data: { turn: 1 } });
  await tool.execute({}, { agent: { id: 'other-chat' }, callId: 'call-2', signal });
  assert.equal(calls.filter(c => c.path === '/runs').length, 2);
  native.clear();
  assert.equal(ctx.tools.schemas().length, 0);
  await ctx.fiber.dispose();
});
