// End-to-end tests against the real app: FastAPI serving the built frontend from frontend/dist.
//
// Local run:  npm run build && npm run test:e2e
//   Starts backend/scripts/serve_local.py on E2E_PORT (default 8765) with a fresh, demo-seeded data dir.
//   Set PYTHON to pick the interpreter that has backend/requirements.txt installed.
// CI (or an already running server): set E2E_BASE_URL and no server is started.
import { defineConfig, devices } from '@playwright/test'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const external = process.env.E2E_BASE_URL
const port = process.env.E2E_PORT ?? '8765'
const baseURL = external ?? `http://127.0.0.1:${port}`
const python = process.env.PYTHON ?? 'python'
// Created once in the main process; workers inherit it through the env so they don't make their own.
process.env.E2E_DATA_DIR ??= mkdtempSync(path.join(tmpdir(), 'finvault-e2e-'))

export default defineConfig({
  testDir: './e2e',
  // One shared demo database, so the specs run one after another in file order.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL,
    locale: 'en-CA',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.js/ },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], storageState: 'e2e/.auth/demo.json' },
      dependencies: ['setup'],
    },
  ],
  webServer: external ? undefined : {
    command: `"${python}" -m scripts.demo_seed && "${python}" scripts/serve_local.py`,
    cwd: path.resolve(import.meta.dirname, '../backend'),
    env: { FINVAULT_DATA_DIR: process.env.E2E_DATA_DIR, PORT: port },
    url: `${baseURL}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
