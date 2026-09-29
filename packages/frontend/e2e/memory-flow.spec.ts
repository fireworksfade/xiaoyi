import { expect, test } from '@playwright/test';

test.use({ actionTimeout: 10_000 });
test('real memory worker: capture, review, version, recall, retain and forget source', async ({
  page,
}) => {
  test.skip(
    process.env.E2E_MEMORY_LIVE !== '1',
    'Requires the isolated real backend fixture',
  );
  test.setTimeout(90_000);
  const root = '/api/backend/api/v1';
  const initialized = page.waitForResponse(
    (response) =>
      response.url().includes('/conversations?') && response.status() === 200,
  );
  await page.goto('/');
  const initialResponse = await initialized;
  // Fail before any message/action if local bindings point at an existing backend.
  expect(initialResponse.headers()['x-request-id']).toMatch(/^memory-e2e-/);
  await expect(page.getByText('今天要处理什么？')).toBeVisible();
  await page
    .getByRole('textbox', { name: '给小yi发送消息', exact: true })
    .fill('检查 MQTT 心跳异常');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await expect(
    page.getByText('诊断完成：MQTT 心跳异常，根因需核实。'),
  ).toBeVisible();
  const token = await page.evaluate(() =>
    sessionStorage.getItem('xiaoyi.csrf-token'),
  );
  const headers = { 'X-CSRF-Token': token! };
  const memories = async () =>
    (await (await page.request.get(`${root}/memories?kind=experience`)).json())
      .data.items;
  await expect.poll(async () => (await memories()).length).toBe(1);
  const original = (await memories())[0];
  const detail = async () =>
    (await (await page.request.get(`${root}/memories/${original.id}`)).json())
      .data;
  const lookup = async () =>
    (
      await (
        await page.request.post(`${root}/memories/search`, {
          headers,
          data: {
            query: 'MQTT 心跳配置',
            mcp_server_id: 'memory-e2e-service',
            device_id: 'memory-e2e-device',
          },
        })
      ).json()
    ).data.items;
  expect(
    (await lookup()).some(
      (item: { memory_id: string }) => item.memory_id === original.id,
    ),
  ).toBe(false);
  await page.getByRole('button', { name: '记忆', exact: true }).click();
  const confirm = page.getByRole('button', {
    name: `确认 ${original.title}`,
    exact: true,
  });
  await confirm.click();
  await expect(page.getByText('检查心跳配置后再考虑重连')).toBeVisible();
  expect((await detail()).status).toBe('candidate');
  await confirm.click();
  await expect.poll(async () => (await detail()).active_revision).toBe(1);
  await page
    .getByRole('button', { name: `编辑 ${original.title}`, exact: true })
    .click();
  await page
    .getByLabel('摘要', { exact: true })
    .fill('修订版：先核实心跳配置，再决定是否重连。');
  await page.getByRole('button', { name: '保存新版本' }).click();
  await expect.poll(async () => (await detail()).current_revision).toBe(2);
  expect((await detail()).active_revision).toBe(1);
  await expect(page.getByText('旧版 v1 与当前 v2 对照')).toBeVisible();
  const stale = await page.request.post(
    `${root}/memories/${original.id}/confirm`,
    {
      headers,
      data: { expected_revision: 1 },
    },
  );
  expect(stale.status()).toBe(409);
  await confirm.click();
  await expect.poll(async () => (await detail()).active_revision).toBe(2);
  expect(
    (await lookup()).find(
      (item: { memory_id: string }) => item.memory_id === original.id,
    ).revision,
  ).toBe(2);
  await page.keyboard.press('Escape');
  const firstConversation = (
    await (await page.request.get(`${root}/conversations`)).json()
  ).data.items[0];
  const before = (await detail()).use_count;
  await page.getByRole('button', { name: '新建对话', exact: true }).click();
  await page
    .getByRole('textbox', { name: '给小yi发送消息', exact: true })
    .fill('MQTT 心跳配置再次诊断');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  await expect(
    page.getByText('诊断完成：MQTT 心跳异常，根因需核实。'),
  ).toBeVisible();
  await expect
    .poll(async () => (await detail()).use_count)
    .toBeGreaterThan(before);
  await page
    .getByRole('button', { name: `管理对话：${firstConversation.title}` })
    .click();
  await page.getByRole('menuitem', { name: '删除', exact: true }).click();
  await expect(page.getByRole('checkbox')).not.toBeChecked();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: '删除', exact: true })
    .click();
  await expect
    .poll(async () => (await detail()).sources[0].access_state)
    .toBe('conversation_deleted');
  expect((await detail()).status).toBe('active');
  await page.getByRole('button', { name: '记忆', exact: true }).click();
  if (
    !(await page
      .getByRole('button', { name: '清除已删除聊天的记忆', exact: true })
      .isVisible())
  ) {
    await page.getByRole('button').filter({ hasText: original.title }).click();
  }
  await page
    .getByRole('button', { name: '清除已删除聊天的记忆', exact: true })
    .click();
  await expect.poll(async () => (await detail()).status).toBe('suspended');
  expect(JSON.stringify(await detail())).not.toContain('心跳配置可能导致');
  expect(
    (await lookup()).some(
      (item: { memory_id: string }) => item.memory_id === original.id,
    ),
  ).toBe(false);
  await page.keyboard.press('Escape');
  await expect.poll(async () => (await memories()).length).toBe(2);
  const secondConversation = (
    await (await page.request.get(`${root}/conversations`)).json()
  ).data.items[0];
  await page
    .getByRole('button', { name: `管理对话：${secondConversation.title}` })
    .click();
  await page.getByRole('menuitem', { name: '删除', exact: true }).click();
  await page.getByRole('checkbox').check();
  await expect(page.getByText(/将清除 \d+ 条情景/)).toBeVisible();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: '删除', exact: true })
    .click();
  await expect
    .poll(async () =>
      (await memories()).every(
        (item: { status: string }) => item.status === 'suspended',
      ),
    )
    .toBe(true);
});
