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

// The identity, outage and vault journeys change shared state (the test doubles, one user's vault),
// so they run one file after the other, in Chromium only, after every other project has finished.
// (Files of one project may run in parallel workers, so each file is its own project in a chain.)
const SERIAL_SPECS = [
  'identity-journeys',
  'catalogue-outage',
  'vault-journeys',
  'vault-privacy',
  'scan-journey',
];
const SERIAL_PATTERN = new RegExp(`(${SERIAL_SPECS.join('|')})\\.spec\\.ts$`);
const regular = projects.map((project) => ({ ...project, testIgnore: SERIAL_PATTERN }));
const serial = wanted.includes('chromium')
  ? SERIAL_SPECS.map((spec, index) => ({
      name: spec === 'identity-journeys' ? 'identity' : spec,
      testMatch: new RegExp(`${spec}\\.spec\\.ts$`),
      fullyParallel: false,
      dependencies:
        index === 0
          ? regular.map((project) => project.name)
          : [
              SERIAL_SPECS[index - 1] === 'identity-journeys'
                ? 'identity'
                : SERIAL_SPECS[index - 1],
            ],
      use: { ...devices['Desktop Chrome'] },
    }))
  : [];

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/support/global-setup.ts',
  fullyParallel: true,
  // Sign-in redirects through the provider and back; Firefox in particular needs a few seconds.
  expect: { timeout: 10_000 },
  // A broken stack must fail fast instead of burning the whole job timeout.
  maxFailures: process.env['CI'] ? 15 : 0,
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
  projects: [...regular, ...serial],
});
