import { expect, test, type Route } from '@playwright/test';

type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
};

const now = '2026-09-14T12:00:00Z';

function envelope(data: unknown) {
  return { data, request_id: 'e2e-request' };
}

async function fulfillJson(route: Route, data: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(data),
  });
}

test('login, create, stream, rename, refresh recovery, and delete', async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  const conversations: Conversation[] = [];
  const messages = new Map<string, Message[]>();
  let runConversationId = '';
  let conversationListRequests = 0;

  await page.route('**/api/backend/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace('/api/backend/api/v1', '');
    const method = request.method();

    if (path === '/auth/login' && method === 'POST') {
      return fulfillJson(
        route,
        envelope({ csrf_token: 'e2e-csrf', user: { id: 'u1' } }),
      );
    }
    if (path === '/auth/me') {
      return fulfillJson(
        route,
        envelope({ id: 'u1', username: 'admin', role: 'admin' }),
      );
    }
    if (path === '/conversations' && method === 'GET') {
      conversationListRequests += 1;
      return fulfillJson(
        route,
        envelope({
          items: conversations,
          page: 1,
          page_size: 100,
          total: conversations.length,
        }),
      );
    }
    if (path === '/conversations' && method === 'POST') {
      const conversation = {
        id: 'c1',
        title: '新对话',
        created_at: now,
        updated_at: now,
      };
      conversations.unshift(conversation);
      messages.set(conversation.id, []);
      return fulfillJson(route, envelope(conversation), 201);
    }

    const messageMatch = path.match(/^\/conversations\/([^/]+)\/messages$/);
    if (messageMatch && method === 'GET') {
      const items = messages.get(messageMatch[1]) ?? [];
      return fulfillJson(
        route,
        envelope({ items, next_cursor: null, has_more: false }),
      );
    }
    if (messageMatch && method === 'POST') {
      const conversationId = messageMatch[1];
      const body = request.postDataJSON() as { content: string };
      runConversationId = conversationId;
      messages.get(conversationId)?.push({
        id: 'm-user',
        role: 'user',
        content: body.content,
        metadata: {},
        created_at: now,
      });
      const conversation = conversations.find(
        (item) => item.id === conversationId,
      );
      if (conversation) conversation.title = body.content.slice(0, 40);
      return fulfillJson(
        route,
        envelope({ run_id: 'run-1', idempotent_replay: false }),
        202,
      );
    }
    if (path === '/agent-runs/run-1/events') {
      messages.get(runConversationId)?.push({
        id: 'm-assistant',
        role: 'assistant',
        content: '诊断完成',
        metadata: {},
        created_at: now,
      });
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body:
          'event: answer.delta\ndata: {"id":1,"data":{"delta":"诊断完成"}}\n\n' +
          'event: workflow.waiting_verification\ndata: {"id":2,"data":{"current_step":"verify","status":"waiting_verification"}}\n\n' +
          'event: run.completed\ndata: {"id":3,"data":{}}\n\n',
      });
    }
    if (path === '/agent-runs' && method === 'GET') {
      const items = runConversationId
        ? [
            {
              id: 'run-1',
              conversation_id: runConversationId,
              status: 'COMPLETED',
              final_message_id: 'm-assistant',
              error: null,
              created_at: now,
              updated_at: now,
            },
          ]
        : [];
      return fulfillJson(
        route,
        envelope({ items, page: 1, page_size: 50, total: items.length }),
      );
    }
    if (path === '/agent-runs/run-1/workflow') {
      return fulfillJson(
        route,
        envelope({
          id: 'workflow-1',
          agent_run_id: 'run-1',
          goal: 'remediation',
          status: 'waiting_verification',
          outcome: null,
          current_step: 'verify',
          device_id: 'ESP32_05',
          diagnosis_id: 'DIA_TEST',
          proposal_id: null,
          command_id: 'CMD_TEST',
          case_id: null,
          steps: [
            { step_key: 'diagnose', status: 'completed', sequence: 1 },
            { step_key: 'select_action', status: 'completed', sequence: 2 },
            { step_key: 'approve', status: 'skipped', sequence: 3 },
            { step_key: 'remediate', status: 'running', sequence: 4 },
            { step_key: 'verify', status: 'waiting', sequence: 5 },
            { step_key: 'archive_case', status: 'pending', sequence: 6 },
          ],
        }),
      );
    }

    const conversationMatch = path.match(/^\/conversations\/([^/]+)$/);
    if (conversationMatch && method === 'PATCH') {
      const body = request.postDataJSON() as { title: string };
      const conversation = conversations.find(
        (item) => item.id === conversationMatch[1],
      );
      if (!conversation)
        return fulfillJson(route, { error: { code: 'NOT_FOUND' } }, 404);
      conversation.title = body.title;
      return fulfillJson(route, envelope(conversation));
    }
    if (conversationMatch && method === 'DELETE') {
      const index = conversations.findIndex(
        (item) => item.id === conversationMatch[1],
      );
      if (index >= 0) conversations.splice(index, 1);
      return fulfillJson(route, envelope({ deleted: true }));
    }

    return fulfillJson(
      route,
      { error: { code: 'UNMOCKED', message: path } },
      500,
    );
  });

  await page.goto('/');
  await expect(page.getByText('今天要处理什么？')).toBeVisible();
  await expect.poll(() => conversationListRequests).toBeGreaterThan(0);

  await page.getByRole('button', { name: '查看设备状态' }).click();
  await page.waitForTimeout(100);
  expect(pageErrors).toEqual([]);
  await expect(page.getByText('诊断完成')).toBeVisible();

  await page
    .getByRole('button', { name: '管理对话：查看当前设备运行状态' })
    .click();
  await page.getByRole('menuitem', { name: '重命名' }).click();
  await page.getByLabel('对话名称').fill('设备诊断');
  await page.getByRole('button', { name: '保存' }).click();
  await expect(
    page.getByRole('button', { name: '管理对话：设备诊断' }),
  ).toBeVisible();

  await page.reload();
  await expect(page.getByText('诊断完成')).toBeVisible();
  await expect(page.getByRole('heading', { name: '设备诊断' })).toBeVisible();
  await page.getByRole('button', { name: '运行记录' }).click();
  await expect(page.getByText('ESP32_05 · 等待恢复验证')).toBeVisible();
  await expect(page.getByText('等待中')).toBeVisible();
  await expect(page.getByRole('link', { name: /artifact/i })).toHaveCount(0);
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: '管理对话：设备诊断' }).click();
  await page.getByRole('menuitem', { name: '删除' }).click();
  await page.getByRole('dialog').getByRole('button', { name: '删除' }).click();
  await expect(page.getByText('今天要处理什么？')).toBeVisible();
  await expect(page.getByText('还没有对话')).toBeVisible();
});
