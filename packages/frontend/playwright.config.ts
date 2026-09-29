import { defineConfig, devices } from '@playwright/test';

const liveMemory = process.env.E2E_MEMORY_LIVE === '1';
const baseURL = liveMemory ? 'http://127.0.0.1:13000' : 'http://127.0.0.1:3000';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    ...(liveMemory
      ? [
          {
            command: `"${process.env.E2E_PYTHON ?? 'python'}" ../backend/tests/e2e_memory_server.py`,
            url: 'http://127.0.0.1:18001/ready',
            reuseExistingServer: false,
            timeout: 60_000,
          },
        ]
      : []),
    {
      command: liveMemory ? 'npm run dev -- --port 13000' : 'npm run dev',
      url: baseURL,
      env: liveMemory
        ? {
            BACKEND_BASE_URL: 'http://127.0.0.1:18001',
            // Wrangler otherwise overlays .env.local onto the configured binding.
            CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV: 'false',
          }
        : {},
      reuseExistingServer: !liveMemory && !process.env.CI,
      timeout: 120_000,
    },
  ],
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
