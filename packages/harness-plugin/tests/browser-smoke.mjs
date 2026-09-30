// A real Cordis Host and Chromium exercise the shipped client against the real
// frontend and an isolated mock-runtime backend. This does not automate Desktop.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { readFile, mkdir } from 'node:fs/promises';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { chromium, expect } from '@playwright/test';
import { Context } from '@deepseek-ai/cordis';
import { ToolRuntime } from '@deepseek-ai/dsh-tools';
import { HostConnectionService } from '@deepseek-ai/dsh-client-connection';
import * as plugin from '../lib/index.js';

const backendUrl = process.env.HARNESS_TEST_BACKEND ?? 'http://127.0.0.1:18002';
const frontendUrl = process.env.HARNESS_TEST_FRONTEND ?? 'http://127.0.0.1:13000';
assert.equal((await fetch(`${backendUrl}/ready`)).ok, true, 'Start the isolated backend first');
assert.equal((await fetch(frontendUrl)).ok, true, 'Start the frontend first');
const ctx = new Context();
ctx.reflect.provide('systemPrompt', { tools() {} });
const requests = [], errors = [];
new HostConnectionService(ctx, [], { isAuthenticated: () => true });
ctx.connection.rpc.intercept('/api', () => false, async () => ({ ok: false, error: { code: 'fixture/unused', message: 'unused', details: {} } }));
const shared = ctx.connection.createSharedFetchHandler('/api');
ctx.plugin(ToolRuntime, { mode: 'native' });
const fiber = ctx.plugin(plugin, { backendUrl, frontendUrl, instanceId: `browser-${randomUUID()}`, requestTimeoutMs: 30000 });
await fiber.await();
const shippedClient = await readFile(new URL('../lib/client.js', import.meta.url), 'utf8');
const fixture = await build({
  stdin: { contents: `
    import React from 'react';
    import {createRoot} from 'react-dom/client';
    const root=createRoot(document.getElementById('panel'));
    let definition;
    window.__ModuleLoader__={load(value){definition=value}};
    const connection={rpc:{async call(_channel,endpoint,payload,signal){
      const response=await fetch('/api/'+endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:crypto.randomUUID(),method:endpoint,payload}),signal});
      return (await response.json()).result;
    }}};
    window.mount=()=>definition.factory(name=>{if(name==='react')return React;throw Error(name)}).apply({connection,slots:{
      inject(_slot,register){register()},register(meta,Component){if(meta.name==='main')root.render(React.createElement(Component))}
    }});
    document.getElementById('disable').onclick=async()=>{root.unmount();await fetch('/fixture/disable',{method:'POST'});document.getElementById('disabled').textContent='已停用'};
  `, resolveDir: fileURLToPath(new URL('../../frontend', import.meta.url)), loader: 'js' },
  bundle: true, platform: 'browser', format: 'iife', write: false,
});
const session = randomUUID();
const server = createServer(async (req, res) => {
  try {
    if (req.url === '/') {
      res.setHeader('Set-Cookie', `fixture_session=${session}; HttpOnly; SameSite=Strict; Path=/`);
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.end('<html><body style="margin:0"><button id="disable">停用插件</button><span id="disabled"></span><div id="panel" style="height:calc(100vh - 24px)"></div><script src="/fixture.js"></script><script src="/client.js"></script><script>mount()</script></body></html>');
      return;
    }
    if (req.url === '/fixture.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(fixture.outputFiles[0].text); return; }
    if (req.url === '/client.js') { res.setHeader('Content-Type', 'text/javascript'); res.end(shippedClient); return; }
    if (!req.headers.cookie?.includes(`fixture_session=${session}`)) { res.writeHead(401); res.end(); return; }
    if (req.url === '/fixture/disable' && req.method === 'POST') {
      await fiber.dispose(); res.end('{}'); return;
    }
    const url = new URL(req.url, 'http://127.0.0.1');
    if (url.pathname.startsWith('/api/')) {
      let body;
      if (req.method === 'POST') {
        const chunks = []; for await (const chunk of req) chunks.push(chunk);
        body = Buffer.concat(chunks);
        const message = JSON.parse(body.toString());
        requests.push({ endpoint: message.method, path: message.payload?.path });
      } else requests.push({ path: url.pathname });
      const abort = new AbortController(); res.on('close', () => abort.abort());
      const response = await shared.fetch(new Request(url, { method: req.method, headers: { 'Content-Type': 'application/json' }, body, signal: abort.signal }));
      res.writeHead(response.status, Object.fromEntries(response.headers));
      if (response.body) await pipeline(Readable.fromWeb(response.body), res); else res.end();
      return;
    }
    res.writeHead(404); res.end();
  } catch (error) {
    if (req.url?.includes('/events')) return;
    errors.push(error.message); if (!res.headersSent) res.writeHead(500); res.end();
  }
});
server.listen(0, '127.0.0.1'); await once(server, 'listening');
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
const browserErrors = [];
try {
  page.on('pageerror', error => browserErrors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.getByLabel('小忆账号').fill('admin');
  await page.getByLabel('小忆密码').fill('wrong-password');
  await page.getByRole('button', { name: '连接平台', exact: true }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByLabel('小忆密码').fill('admin123');
  await page.getByRole('button', { name: '连接平台', exact: true }).click();
  await expect(page.getByText(/主对话工具已连接 · admin/)).toBeVisible();
  assert.ok(ctx.tools.schemas().length >= 2);
  await page.getByRole('button', { name: '打开数据与审批面板' }).click();
  const frame = page.frameLocator('iframe[title="小忆 IoT 平台"]');
  const composer = frame.getByPlaceholder('给小yi发送消息');
  await expect(composer).toBeVisible({ timeout: 60000 });
  await expect.poll(() => requests.some(item => item.path?.startsWith('/conversations?'))).toBe(true);
  await frame.getByRole('button', { name: '记忆', exact: true }).click();
  await expect(frame.getByRole('heading', { name: '记忆', exact: true })).toBeVisible();
  await expect.poll(() => requests.some(item => item.path?.startsWith('/memories'))).toBe(true);
  await page.keyboard.press('Escape');
  await frame.getByRole('button', { name: '知识文档', exact: true }).click();
  await expect(frame.getByRole('heading', { name: '知识库', exact: true })).toBeVisible();
  await expect.poll(() => requests.some(item => item.path?.startsWith('/knowledge-documents'))).toBe(true);
  await page.keyboard.press('Escape');
  await frame.locator('input[type="file"]').first().setInputFiles({ name: 'harness-smoke.txt', mimeType: 'text/plain', buffer: Buffer.from('插件上传检查：只读设备说明。') });
  await expect(frame.getByText('harness-smoke.txt', { exact: true })).toBeVisible();
  await composer.fill('请读取附件并回答：插件连接检查。');
  await composer.press('Enter');
  await expect(frame.getByText(/小yi 已收到/)).toBeVisible({ timeout: 30000 });
  await expect.poll(() => requests.some(item => item.path === '/api/xiaoyi-iot/events')).toBe(true);
  assert.equal(requests.some(item => item.path === '/auth/login'), false, 'iframe never receives or uses login credentials');
  await expect.poll(() => requests.some(item => item.path === '/attachments')).toBe(true);
  const screenshots = fileURLToPath(new URL('../../../output', import.meta.url));
  await mkdir(screenshots, { recursive: true });
  await page.screenshot({ path: `${screenshots}/harness-plugin-browser.png`, fullPage: true });
  await page.getByRole('button', { name: '停用插件', exact: true }).click();
  await expect(page.getByText('已停用', { exact: true })).toBeVisible();
  assert.equal(ctx.tools.schemas().length, 0);
  assert.equal((await shared.fetch(new Request('http://127.0.0.1/api/xiaoyi-iot/events'))).status, 404);
  assert.deepEqual(errors, []); assert.deepEqual(browserErrors, []);
  console.log('PASS: invalid login, login, full iframe UI, memory and knowledge requests, multipart attachment, conversation, SSE answer, scoped unload.');
} catch (error) {
  console.error('Browser errors:', browserErrors, 'Host errors:', errors, 'Forwarded:', requests);
  const child = page.frames().find(value => value.url().startsWith(frontendUrl));
  console.error('Iframe:', await child?.locator('body').innerText());
  throw error;
} finally {
  await browser.close(); await fiber.dispose(); await ctx.fiber.dispose(); server.close(); server.closeAllConnections();
}
