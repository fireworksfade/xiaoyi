import { expect, test, type Page } from '@playwright/test';

test.use({ actionTimeout: 15_000 });

async function openApp(page: Page) {
  const initialized = page.waitForResponse(
    (r) => r.url().includes('/conversations?') && r.status() === 200,
  );
  await page.goto('/');
  await initialized;
  await expect(page.getByText('正在加载对话…', { exact: true })).toHaveCount(0);
}

// Explicit opt-in: uses the existing backend and configured paid model APIs.
test('real IoT: SQL history, knowledge retrieval, clarification and refresh recovery', async ({
  page,
}) => {
  test.skip(
    process.env.E2E_IOT_LIVE !== '1',
    'Requires running Docker IoT services and configured models',
  );
  test.setTimeout(600_000);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await openApp(page);
  await expect(
    page.getByRole('button', { name: '新建对话', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: '新建对话', exact: true }).click();
  const input = page.getByRole('textbox', {
    name: '给小yi发送消息',
    exact: true,
  });
  const submitted = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' &&
      /\/conversations\/[^/]+\/messages$/.test(new URL(r.url()).pathname),
  );
  await input.fill(
    '使用 query_iot_data 查询过去24小时各节点的平均温度和有效样本数，按节点分组。只读查询，不执行设备操作。',
  );
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  const response = await submitted;
  expect(response.status()).toBe(202);
  const { run_id: runId } = (await response.json()).data;
  const root = '/api/backend/api/v1';
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`${root}/agent-runs/${runId}`)).json())
          .data.status,
      { timeout: 240_000, intervals: [1000, 3000] },
    )
    .toBe('completed');
  const sqlChip = page
    .getByRole('button', { name: /query_iot_data.*已完成/ })
    .first();
  await expect(sqlChip).toBeVisible();
  await sqlChip.click();
  await expect(page.getByLabel('历史数据查询结果')).toBeVisible();
  await expect(
    page.getByRole('columnheader', { name: '有效样本数' }),
  ).toBeVisible();
  await expect(page.getByRole('cell', { name: /ESP32/ }).first()).toBeVisible();
  const recovered = page.waitForResponse(
    (r) => /\/messages\?/.test(r.url()) && r.status() === 200,
  );
  await page.reload();
  await recovered;
  await page
    .getByRole('button', { name: /query_iot_data.*已完成/ })
    .first()
    .click();
  await expect(page.getByLabel('历史数据查询结果')).toBeVisible();

  await input.fill(
    '使用 search_knowledge 在 mqtt_docs 中检索 MQTT 连接异常排查知识，top_k=3，引用知识库来源。只读检索。',
  );
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  const retrieval = page
    .getByRole('button', { name: /search_knowledge.*已完成/ })
    .last();
  await expect(retrieval).toBeVisible({ timeout: 240_000 });
  await retrieval.click();
  await expect(page.getByLabel('检索服务状态')).toHaveText(
    /向量检索：API.*重排：API/,
  );
  await expect(page.getByText('引用来源', { exact: true })).toBeVisible();
  await expect(
    page.getByRole('button', { name: '发送消息', exact: true }),
  ).toBeVisible({ timeout: 120_000 });

  await input.fill(
    '使用 query_iot_data 查询过去24小时掉线次数。先调用工具，不要自行推算。',
  );
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  const clarification = page
    .getByRole('button', { name: /query_iot_data.*统一的掉线事件编号/ })
    .last();
  await expect(clarification).toBeVisible({ timeout: 180_000 });
  await clarification.click();
  await expect(page.getByRole('alert')).toContainText('需要补充查询条件');
  expect(errors).toEqual([]);
});

test('real knowledge upload, replacement and deletion synchronize all three indexes', async ({
  page,
}) => {
  test.skip(
    process.env.E2E_IOT_LIVE !== '1',
    'Requires running IoT services and all three indexes',
  );
  test.setTimeout(180_000);
  const documentId = `e2e-iot-${Date.now()}`;
  const title = `联调临时文档 ${documentId}`;
  const root = '/api/backend/api/v1';
  const collections = (
    process.env.E2E_QDRANT_COLLECTIONS ??
    'iot_diagnosis_dashscope_qwen37_flash_1024,iot_diagnosis_qwen3_512,iot_diagnosis_portable'
  ).split(',');
  const sizes = [1024, 512, 384];
  await openApp(page);
  await page.getByRole('button', { name: '知识文档', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByLabel('文档文件')).toBeVisible();
  const points = async (collection: string) => {
    const response = await page.request.post(
      `http://127.0.0.1:6333/collections/${collection}/points/scroll`,
      {
        data: {
          filter: {
            must: [{ key: 'document_id', match: { value: documentId } }],
          },
          limit: 100,
          with_payload: true,
          with_vector: true,
        },
      },
    );
    expect(response.ok()).toBeTruthy();
    return (await response.json()).result.points as {
      vector: number[];
      payload: { content: string };
    }[];
  };
  try {
    for (const revision of ['REVISION_ALPHA', 'REVISION_BETA']) {
      await dialog.getByLabel('文档文件').setInputFiles({
        name: `${documentId}.md`,
        mimeType: 'text/markdown',
        buffer: Buffer.from(
          `# 联调设备指南\n\n${revision}：检查设备心跳、网络连接和传感器温度。`,
        ),
      });
      await dialog.getByLabel('文档 ID（可选）').fill(documentId);
      await dialog.getByLabel('标题（可选）').fill(title);
      const uploaded = page.waitForResponse(
        (r) =>
          r.request().method() === 'POST' &&
          new URL(r.url()).pathname === `${root}/knowledge-documents`,
      );
      await dialog
        .getByRole('button', { name: '上传文档', exact: true })
        .click();
      const response = await uploaded;
      expect(response.status()).toBe(201);
      const result = (await response.json()).data;
      expect(result.vector_indexed).toBe(true);
      await expect(dialog.getByText(/已加入知识库/)).toBeVisible();
      for (const [index, collection] of collections.entries()) {
        const indexed = await points(collection);
        expect(indexed).toHaveLength(result.chunk_count);
        expect(
          indexed.every((p) => p.vector.length === sizes[index]),
        ).toBeTruthy();
        expect(
          indexed.every((p) => p.payload.content.includes(revision)),
        ).toBeTruthy();
        if (revision === 'REVISION_BETA')
          expect(
            indexed.every((p) => !p.payload.content.includes('REVISION_ALPHA')),
          ).toBeTruthy();
      }
    }
    const hardwareGroup = dialog.getByRole('button', {
      name: /设备与硬件.*篇文档/,
    });
    if ((await hardwareGroup.getAttribute('aria-expanded')) === 'false')
      await hardwareGroup.click();
    await dialog
      .getByRole('button', { name: `删除 ${title}`, exact: true })
      .click();
    const deleted = page.waitForResponse(
      (r) =>
        r.request().method() === 'DELETE' &&
        new URL(r.url()).pathname.endsWith(`/${documentId}`),
    );
    await dialog.getByRole('button', { name: '确认删除', exact: true }).click();
    const deletionResponse = await deleted;
    expect(deletionResponse.status()).toBe(200);
    expect((await deletionResponse.json()).data.vector_deleted).toBe(true);
    await expect(
      dialog.getByRole('button', { name: `删除 ${title}`, exact: true }),
    ).toHaveCount(0);
    for (const collection of collections)
      expect(await points(collection)).toHaveLength(0);
  } finally {
    // Only remove the uniquely named document created by this test if an assertion failed.
    const csrf = await page.evaluate(() =>
      sessionStorage.getItem('xiaoyi.csrf-token'),
    );
    const list = await page.request.get(
      `${root}/knowledge-documents?limit=200`,
    );
    const docs = (await list.json()).data.items as {
      source: string;
      document_id: string;
    }[];
    const own = docs.find((d) => d.document_id === documentId);
    if (own)
      await page.request.delete(
        `${root}/knowledge-documents/${own.source}/${documentId}`,
        { headers: { 'X-CSRF-Token': csrf! } },
      );
  }
});
