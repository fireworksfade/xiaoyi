import { spawn, execFile } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { once } from 'node:events';
import { writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { promisify } from 'node:util';
import { expect, test, type Page } from '@playwright/test';

const execute = promisify(execFile);
const root = '/api/backend/api/v1';
const cases = [
  {
    action: 'reconnect_mqtt',
    scenario: 'mqtt_timeout',
    parameters: {},
    high: false,
  },
  {
    action: 'reconnect_wifi',
    scenario: 'wifi_weak',
    parameters: {},
    high: false,
  },
  {
    action: 'calibrate_sensor',
    scenario: 'sensor_error',
    parameters: {},
    high: false,
  },
  {
    action: 'set_reporting_interval',
    scenario: 'normal',
    parameters: { seconds: 3 },
    high: false,
  },
  {
    action: 'restart_device',
    scenario: 'memory_leak',
    parameters: {},
    high: true,
  },
  {
    action: 'update_firmware',
    scenario: 'watchdog_reset',
    parameters: { version: '1.3.9' },
    high: true,
  },
];

// Only the uniquely named simulator is changed. Real chat, diagnosis, backend,
// MCP, Broker, ACK handling and the production observation window remain active.
const simulatorCode = `
import sys
from iot_diagnosis.simulator.models import DeviceProfile
from iot_diagnosis.simulator.device_simulator import DeviceSimulator
profile = DeviceProfile(device_id=sys.argv[1], scenario=sys.argv[2], interval=2)
device = DeviceSimulator(profile, '127.0.0.1', 1883)
device.start()
try:
    sys.stdin.readline()
finally:
    device.stop()
`;

// Independent read-only evidence avoids asking the chat model to poll forever.
// No synthetic ACKs, verification results or clock advancement are injected.
const evidenceCode = `
import json, os, sqlite3, sys
kind, identifier = sys.argv[1:]
path = os.environ['DIAGNOSIS_DATABASE_PATH' if kind == 'device' else 'CONTROL_DATABASE_PATH']
db = sqlite3.connect('file:' + path + '?mode=ro', uri=True)
db.row_factory = sqlite3.Row
if kind == 'device':
    row = db.execute('SELECT * FROM device_current_state WHERE device_id = ?', (identifier,)).fetchone()
else:
    row = db.execute('SELECT c.*, o.delivery_status, o.baseline_json FROM device_command c JOIN command_outbox o USING(command_id) WHERE c.command_id = ?', (identifier,)).fetchone()
print(json.dumps(dict(row) if row else None))
db.close()
`;

async function evidence(kind: 'device' | 'command', identifier: string) {
  const { stdout } = await execute(
    'docker',
    [
      'compose',
      'exec',
      '-T',
      'iot-mcp',
      'python',
      '-c',
      evidenceCode,
      kind,
      identifier,
    ],
    { cwd: resolve('../..'), windowsHide: true, timeout: 15_000 },
  );
  return JSON.parse(stdout);
}

async function messages(page: Page, conversationId: string) {
  const response = await page.request.get(
    `${root}/conversations/${conversationId}/messages`,
  );
  expect(response.ok()).toBeTruthy();
  return (await response.json()).data.items as Array<{
    role: string;
    metadata: {
      tool_calls?: Array<{
        tool_name: string;
        output: Record<string, unknown>;
      }>;
    };
  }>;
}

for (const item of cases) {
  test(`real action: ${item.action}, ACK, verification and refresh`, async ({
    page,
  }, testInfo) => {
    test.skip(
      process.env.E2E_IOT_ACTIONS_LIVE !== '1',
      'Requires Docker IoT, configured chat/diagnosis APIs and simulator Python',
    );
    test.setTimeout(360_000);
    const deviceId = `iot-action-e2e-${item.action}-${randomUUID().slice(0, 8)}`;
    const simulator = spawn(
      process.env.E2E_IOT_PYTHON ?? 'python',
      ['-u', '-c', simulatorCode, deviceId, item.scenario],
      {
        cwd: resolve('../mcp-services'),
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      },
    );
    let simulatorLog = '';
    simulator.stdout.on('data', (chunk) => {
      simulatorLog += chunk.toString();
    });
    simulator.stderr.on('data', (chunk) => {
      simulatorLog += chunk.toString();
    });
    simulator.on('error', (error) => {
      simulatorLog += error.message;
    });
    const pageErrors: string[] = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));
    try {
      await expect
        .poll(async () => (await evidence('device', deviceId))?.online, {
          timeout: 30_000,
          intervals: [1000, 2000],
        })
        .toBe(1);
      const initialized = page.waitForResponse(
        (r) => r.url().includes('/conversations?') && r.status() === 200,
      );
      await page.goto('/');
      await initialized;
      await page.getByRole('button', { name: '新建对话', exact: true }).click();
      const submitted = page.waitForResponse(
        (r) =>
          r.request().method() === 'POST' &&
          /\/conversations\/[^/]+\/messages$/.test(new URL(r.url()).pathname),
      );
      await page
        .getByRole('textbox', { name: '给小yi发送消息', exact: true })
        .fill(
          `这是联调专用模拟设备 ${deviceId}，只允许操作这台设备。请先调用 diagnose_fault 做真实诊断，再用 list_device_actions 确认动作，随后${item.high ? '调用 create_remediation_proposal 创建待审批提案，等待我在页面批准' : '调用 execute_device_action 执行动作'}。指定 action=${item.action}，parameters=${JSON.stringify(item.parameters)}。${item.action === 'set_reporting_interval' ? '我明确要求把上报间隔改为 3 秒以验证配置下发。' : ''}只执行或提交一次指定动作，不选择其他修复动作。受理后结束回复，恢复验证由后台跟踪。`,
        );
      await page.getByRole('button', { name: '发送消息', exact: true }).click();
      const submittedResponse = await submitted;
      expect(submittedResponse.status()).toBe(202);
      const { run_id: runId } = (await submittedResponse.json()).data;
      const conversationId = new URL(submittedResponse.url()).pathname
        .split('/')
        .at(-2)!;
      await expect
        .poll(
          async () =>
            (
              await (
                await page.request.get(`${root}/agent-runs/${runId}`)
              ).json()
            ).data.status,
          { timeout: 240_000, intervals: [1000, 3000] },
        )
        .toBe('completed');
      const history = await messages(page, conversationId);
      const calls = history
        .filter((m) => m.role === 'assistant')
        .flatMap((m) => m.metadata.tool_calls ?? []);
      await writeFile(
        testInfo.outputPath('tool-results.json'),
        JSON.stringify(calls, null, 2),
      );
      await testInfo.attach('tool-results', {
        body: JSON.stringify(calls, null, 2),
        contentType: 'application/json',
      });
      expect(
        calls.some(
          (call) =>
            call.tool_name === 'diagnose_fault' && call.output.ok === true,
        ),
      ).toBeTruthy();
      const toolName = item.high
        ? 'create_remediation_proposal'
        : 'execute_device_action';
      const call = calls.find(
        (entry) => entry.tool_name === toolName && entry.output.ok === true,
      );
      expect(
        call,
        'The requested action must actually be accepted',
      ).toBeTruthy();
      const data = call!.output.data as Record<string, unknown>;
      expect(data.device_id).toBe(deviceId);
      expect(data.action).toBe(item.action);
      let commandId = data.command_id as string;
      if (item.high) {
        const proposalId = data.proposal_id as string;
        expect(data.status).toBe('pending');
        const before = (
          await (
            await page.request.get(
              `${root}/remediation-proposals/${proposalId}`,
            )
          ).json()
        ).data;
        expect(before.command).toBeNull();
        await expect(
          page.getByRole('button', { name: '批准执行', exact: true }),
        ).toBeVisible();
        const decided = page.waitForResponse(
          (r) =>
            r.request().method() === 'POST' &&
            r.url().endsWith(`/remediation-proposals/${proposalId}/decision`),
        );
        await page
          .getByRole('button', { name: '批准执行', exact: true })
          .click();
        const decision = await decided;
        expect(decision.status()).toBe(200);
        const approved = (await decision.json()).data;
        expect(approved.status).toBe('approved');
        commandId = approved.command.command_id;
        await expect(
          page.getByText('设备已恢复，验证通过', { exact: true }),
        ).toBeVisible({ timeout: 100_000 });
      } else {
        await expect(
          page.getByRole('button', { name: /execute_device_action.*已完成/ }),
        ).toBeVisible();
      }
      await expect
        .poll(
          async () => (await evidence('command', commandId))?.verify_status,
          { timeout: 100_000, intervals: [2000, 5000] },
        )
        .toBe('succeeded');
      const command = await evidence('command', commandId);
      expect(command.status).toBe('applied');
      expect(command.delivery_status).toBe('device_acked');
      expect(JSON.parse(command.parameters_json)).toEqual(item.parameters);
      expect(command.diagnosis_id).toMatch(/^DIA_\d{8}_[A-F0-9]{8}$/);
      await writeFile(
        testInfo.outputPath('verified-command.json'),
        JSON.stringify(command, null, 2),
      );
      await testInfo.attach('verified-command', {
        body: JSON.stringify(command, null, 2),
        contentType: 'application/json',
      });
      await page.reload();
      await expect(
        page.getByRole('button', { name: new RegExp(`${toolName}.*已完成`) }),
      ).toBeVisible();
      if (item.high) {
        await expect(
          page.getByText('设备已恢复，验证通过', { exact: true }),
        ).toBeVisible();
        await expect(
          page.getByRole('button', { name: '批准执行', exact: true }),
        ).toHaveCount(0);
      }
      expect(pageErrors).toEqual([]);
      await page.screenshot({
        path: testInfo.outputPath('verified.png'),
        fullPage: true,
      });
    } finally {
      const exited = once(simulator, 'exit');
      if (simulator.exitCode === null && !simulator.killed) {
        simulator.stdin.end('\n');
        const timer = setTimeout(() => simulator.kill(), 10_000);
        await exited;
        clearTimeout(timer);
      }
      await writeFile(testInfo.outputPath('simulator.log'), simulatorLog);
      await testInfo.attach('simulator-log', {
        body: simulatorLog,
        contentType: 'text/plain',
      });
    }
  });
}
