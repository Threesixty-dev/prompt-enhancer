import { test, expect } from '@playwright/test';

const title = 'Clarify a fictional widget request';

test('gateway admission and expired sessions never show an application token prompt', async ({ page }) => {
  await connect(page);
  await expect(page.getByRole('heading', { name: 'Experiments', exact: true })).toBeVisible();
  await page.route('**/api/experiments', route => route.fulfill({ status: 401, contentType: 'application/json', body: '{"error":{"code":"unauthorized"}}' }));
  await page.reload();
  await expect(page.getByText('Your session is unavailable. Reload the page to reconnect through Cloudflare Access.')).toBeVisible();
  await expect(page.locator('input[type=password], #connect-form')).toHaveCount(0);
});
async function connect(page, path = '/') {
  await page.goto(path);
  await expect(page.locator('#workspace')).toBeVisible();
  await expect(page.locator('input[type=password]')).toHaveCount(0);
  await expect(page.getByLabel('Operator access token')).toHaveCount(0);
}
async function openExperiment(page) {
  await connect(page);
  await page.locator('.experiment-card').filter({ hasText: title }).click();
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
}
const strategy = (page, id) => page.locator('.strategy-editor[data-unit="' + id + '"]');
async function start(page) {
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel run', exact: true })).toBeVisible();
}
async function cancel(page) {
  await page.getByRole('button', { name: 'Cancel run', exact: true }).click();
  await expect(page.locator('#run-detail .badge.cancelled').first()).toBeVisible();
}
async function settings(page) {
  await page.getByText('Effective run settings', { exact: true }).click();
  return JSON.parse(await page.locator('#run-detail pre').first().textContent());
}

test('experiment, run form, and result have separate routes with back, forward, and deep links', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await openExperiment(page);
  await expect(page).toHaveURL(/\/experiments\/example-widget\?revision=1$/);
  await expect(page.locator('#run-form, #run-detail')).toHaveCount(0);
  await page.getByRole('link', { name: 'New run', exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/new\?revision=1$/);
  await expect(page.getByRole('heading', { name: 'New run', exact: true })).toBeVisible();
  await expect(page.locator('#experiments, #runs, #run-detail')).toHaveCount(0);
  await expect(page.getByLabel(/JSON/)).toHaveCount(0);
  await page.goBack();
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole('heading', { name: 'New run', exact: true })).toBeVisible();
  await connect(page, '/experiments/example-widget/runs/new?revision=1');
  await expect(strategy(page, 'script').getByLabel('Timeout (seconds)', { exact: true })).toHaveValue('120');
  await page.getByRole('link', { name: 'Cancel', exact: true }).click();
  await page.getByRole('link', { name: /Automatic run/ }).first().click();
  const resultPath = new URL(page.url()).pathname;
  await expect(page.locator('#run-detail')).toBeVisible();
  await expect(page.locator('#run-form, #runs')).toHaveCount(0);
  await expect(page.getByRole('columnheader', { name: 'Before', exact: true }).first()).toBeVisible();
  await connect(page, resultPath);
  await expect(page.locator('#run-detail')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('normal fields create typed overrides and rerun edits preserve saved settings', async ({ page }) => {
  await openExperiment(page);
  await page.getByRole('link', { name: 'New run', exact: true }).click();
  await strategy(page, 'consumer').getByRole('checkbox', { name: 'Consumer rewrite', exact: true }).uncheck();
  const script = strategy(page, 'script');
  await script.getByLabel('Timeout (seconds)', { exact: true }).fill('45');
  await script.getByLabel('Temperature setting').selectOption('value');
  await script.getByLabel('Temperature', { exact: true }).fill('0');
  await script.getByText('Style and steering', { exact: true }).click();
  await script.getByRole('checkbox', { name: 'Acceptance', exact: true }).check();
  await start(page);
  let effective = await settings(page);
  expect(effective.units).toHaveLength(1);
  expect(effective.units[0].parameters).toEqual({ timeout_seconds: 45, generation: { max_output_chars: 20000, max_tokens: null, temperature: 0 } });
  expect(effective.units[0].steering.focus).toEqual(['acceptance']);
  await cancel(page);
  await page.getByRole('link', { name: 'Rerun with changes', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Rerun experiment', exact: true })).toBeVisible();
  await expect(script.getByLabel('Timeout (seconds)', { exact: true })).toHaveValue('45');
  await expect(script.getByLabel('Temperature', { exact: true })).toHaveValue('0');
  await expect(strategy(page, 'consumer').getByRole('checkbox', { name: 'Consumer rewrite', exact: true })).not.toBeChecked();
  await script.getByLabel('Timeout (seconds)', { exact: true }).fill('60');
  await start(page);
  effective = await settings(page);
  expect(effective.units[0].parameters.timeout_seconds).toBe(60);
  expect(effective.units[0].steering.focus).toEqual(['acceptance']);
  await cancel(page);
  const path = new URL(page.url()).pathname;
  await connect(page, path);
  await expect(page.locator('#run-detail .badge.cancelled').first()).toBeVisible();
});

test('consumer model, objective targets, style, and nulls survive a rerun', async ({ page }) => {
  await openExperiment(page);
  await page.getByRole('link', { name: 'New run', exact: true }).click();
  await strategy(page, 'script').getByRole('checkbox', { name: 'Packaged clarification', exact: true }).uncheck();
  const consumer = strategy(page, 'consumer');
  await consumer.getByLabel('Model alias', { exact: true }).fill('example-browser-model');
  await consumer.getByText('Style and steering', { exact: true }).click();
  await consumer.getByLabel('Style', { exact: true }).selectOption('"concise"');
  await consumer.getByLabel('Instructions setting', { exact: true }).selectOption('value');
  await consumer.getByLabel('Instructions', { exact: true }).fill('Use fictional examples.');
  await consumer.getByText('Objective and targets', { exact: true }).click();
  await consumer.getByLabel('Desired value setting', { exact: true }).selectOption('value');
  await consumer.getByLabel('Desired value', { exact: true }).fill('0.5');
  await start(page);
  let effective = await settings(page);
  expect(effective.units[0].consumerBinding.binding_id).toBe('example-browser-model');
  expect(effective.units[0].objective.targets[0].desired_value).toBe(0.5);
  expect(effective.units[0].steering.style).toBe('concise');
  expect(effective.units[0].steering.instructions).toBe('Use fictional examples.');
  await cancel(page);
  await page.getByRole('link', { name: 'Rerun with changes', exact: true }).click();
  await expect(consumer.getByLabel('Model alias', { exact: true })).toHaveValue('example-browser-model');
  await expect(consumer.getByLabel('Maximum tokens setting', { exact: true })).toHaveValue('null');
  await start(page);
  effective = await settings(page);
  expect(effective.units[0].consumerBinding.binding_id).toBe('example-browser-model');
  expect(effective.units[0].objective.targets[0].desired_value).toBe(0.5);
  expect(effective.units[0].parameters.generation.max_tokens).toBeNull();
  await cancel(page);
});

test('invalid numbers and empty selections never submit a run', async ({ page }) => {
  let submissions = 0;
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/api/runs')) submissions++; });
  await openExperiment(page);
  await page.getByRole('link', { name: 'New run', exact: true }).click();
  const field = strategy(page, 'script').getByLabel('Timeout (seconds)', { exact: true });
  await field.fill('999999');
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(field).toBeFocused();
  expect(submissions).toBe(0);
  await field.fill('');
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  expect(submissions).toBe(0);
  await field.fill('30');
  await strategy(page, 'script').getByRole('checkbox', { name: 'Packaged clarification', exact: true }).uncheck();
  await strategy(page, 'consumer').getByRole('checkbox', { name: 'Consumer rewrite', exact: true }).uncheck();
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Select at least one unit and one subject.');
  expect(submissions).toBe(0);
});

test('polling preserves completed result nodes, open disclosures, and form input', async ({ page }) => {
  await openExperiment(page);
  await page.getByRole('link', { name: /Automatic run/ }).first().click();
  await page.getByText('Effective run settings', { exact: true }).click();
  await page.evaluate(() => {
    window.resultNode = document.querySelector('.run-panel');
    window.resultMutations = 0;
    window.resultObserver = new MutationObserver(records => { window.resultMutations += records.length; });
    window.resultObserver.observe(document.querySelector('#run-detail'), { childList: true });
  });
  await page.waitForTimeout(6500);
  expect(await page.evaluate(() => window.resultNode === document.querySelector('.run-panel'))).toBe(true);
  expect(await page.evaluate(() => window.resultMutations)).toBe(0);
  expect(await page.locator('.run-panel').first().evaluate(el => getComputedStyle(el).animationName)).toBe('none');
  await expect(page.locator('details[data-key=effective]')).toHaveAttribute('open', '');
  await page.getByRole('link', { name: 'Rerun with changes', exact: true }).click();
  const field = strategy(page, 'script').getByLabel('Timeout (seconds)', { exact: true });
  await field.fill('37');
  await page.waitForTimeout(3500);
  await expect(field).toHaveValue('37');
  await expect(field).toBeFocused();
});

test('late result response cannot replace another page and wrong experiment run is rejected', async ({ page }) => {
  await openExperiment(page);
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/api/runs/*', async route => { await gate; await route.continue(); });
  await page.getByRole('link', { name: /Automatic run/ }).first().click();
  await page.locator('#breadcrumbs').getByRole('link', { name: 'Experiments', exact: true }).click();
  release();
  await expect(page.locator('.experiment-card')).toBeVisible();
  await expect(page.locator('#run-detail')).toHaveCount(0);
  await page.unroute('**/api/runs/*');
  await page.locator('.experiment-card').first().click();
  const runHref = await page.getByRole('link', { name: /Automatic run/ }).first().getAttribute('href');
  await connect(page, runHref.replace('/example-widget/', '/example-other/'));
  await expect(page.getByText('This run does not belong to the selected experiment revision.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancel run' })).toHaveCount(0);
});
