import { defineConfig } from '@playwright/test';
import path from 'node:path';

const origin = `http://127.0.0.1:${process.env.BENCH_BROWSER_PORT || '8088'}`;

export default defineConfig({
  testDir: './browser',
  timeout: 30000,
  retries: 0,
  workers: 1,
  reporter: 'line',
  outputDir: process.env.BENCH_BROWSER_OUTPUT || '/tmp/enhancement-bench-browser',
  use: { baseURL: origin, channel: process.env.BENCH_BROWSER_CHANNEL, screenshot: 'off', trace: 'off', video: 'off' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
  webServer: {
    command: `${process.env.BENCH_PYTHON || '.venv/bin/python'} ../tests/bench/browser_server.py`,
    url: origin + '/health/ready',
    reuseExistingServer: false,
    timeout: 15000,
    env: { BENCH_CONTRACTS: process.env.BENCH_CONTRACTS || path.resolve('../contracts/enhancement') },
  },
});
