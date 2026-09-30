import { defineConfig, devices } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const PY = process.env.PYTHON || (fs.existsSync(path.join(ROOT, '.venv/bin/python')) ? path.join(ROOT, '.venv/bin/python') : 'python3');
const DATA = fs.mkdtempSync(path.join(os.tmpdir(), 'writeai-e2e-'));
const CHROMIUM = process.env.PW_CHROMIUM || ['/opt/pw-browsers/chromium-1194/chrome-linux/chrome'].find((p) => fs.existsSync(p));
const API_PORT = 8765;
const WEB_PORT = 5199;

process.env.WRITEAI_E2E_PYTHON = PY;
process.env.WRITEAI_E2E_ROOT = ROOT;

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: 'retain-on-failure',
    permissions: ['clipboard-read', 'clipboard-write'],
    viewport: { width: 1400, height: 900 },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1400, height: 900 }, launchOptions: CHROMIUM ? { executablePath: CHROMIUM } : {} },
    },
  ],
  webServer: [
    {
      command: `${PY} -m uvicorn backend.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: ROOT,
      url: `http://127.0.0.1:${API_PORT}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        WRITEAI_ENV: 'development',
        WRITEAI_DATA_DIR: DATA,
        WRITEAI_LLM_PROVIDER: 'mock',
        WRITEAI_EMBEDDING_BACKEND: 'hashing',
        WRITEAI_RATE_LIMIT_PER_MINUTE: '1000',
        ANTHROPIC_API_KEY: '',
      },
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { WRITEAI_API_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
