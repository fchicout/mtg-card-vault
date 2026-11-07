import { defineConfig, devices } from '@playwright/test';

import { CAMERA_FILE } from './e2e/support/fake-camera';

/**
 * End-to-end tests run against an already running stack (deploy/compose.yaml locally, reached over HTTPS through the proxy, an ephemeral
 * compose stack with the `ci` profile in CI). Override the target with E2E_BASE_URL.
 *
 *  - Browsers: Chromium, Firefox and WebKit; narrow with E2E_BROWSERS=chromium,firefox.
 *  - Chromium also gets a fake camera: the generated fixture video (e2e/support/fake-camera.ts)
 *    replaces the webcam, and the permission prompt is answered automatically.
 *  - The local proxy uses a certificate from its own CA, hence ignoreHTTPSErrors.
 *  - A failure keeps its trace, video and screenshot (uploaded as CI artifacts); one retry at most.
 */
const wanted = (process.env['E2E_BROWSERS'] ?? 'chromium,firefox,webkit')
  .split(',')
  .map((b) => b.trim());

const projects = [
  {
    name: 'chromium',
    use: {
      ...devices['Desktop Chrome'],
      launchOptions: {
        args: [
          '--use-fake-device-for-media-stream',
          '--use-fake-ui-for-media-stream',
          `--use-file-for-fake-video-capture=${CAMERA_FILE}`,
        ],
      },
    },
  },
  { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  { name: 'webkit', use: { ...devices['Desktop Safari'] } },
].filter((project) => wanted.includes(project.name));

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/support/global-setup.ts',
  fullyParallel: true,
  forbidOnly: !!process.env['CI'],
  retries: process.env['CI'] ? 1 : 0,
  reporter: process.env['CI'] ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'https://localhost:8443',
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects,
});
