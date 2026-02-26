import { defineConfig, devices } from '@playwright/test';

/**
 * E2E smoke configuration.
 *
 * These tests require both the backend (port 8000) and the frontend
 * (port 3000) to be running.  In CI the `e2e` workflow job starts both
 * services before running playwright.
 *
 * Locally: run `./start-app.ps1` (Windows) or start each service
 * individually, then: npx playwright test
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 1,
  use: {
    baseURL: 'http://localhost:3000',
    headless: true,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
