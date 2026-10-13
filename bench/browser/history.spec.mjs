import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { historyResponse } from './history-fixture.mjs';

async function fixture(page) {
  const definition = JSON.parse(await readFile(new URL('../examples/example-widget.json', import.meta.url), 'utf8'));
  const runs = Array.from({ length: 24 }, (_, index) => ({
    id: 'example-history-' + String(index).padStart(3, '0'), stable_id: definition.stableId, revision: '1',
    status: index < 12 ? 'succeeded' : 'failed', origin: index % 2 ? 'ui' : 'gitops',
    created: Date.parse('2026-10-10T12:00:00Z') / 1000 - index, model: 'example-model-a',
  }));
  const metric = { experiment: definition.stableId, revision: '1', coreVersion: '0.1.0', evaluator: 'prompt', kind: 'deterministic', metric: 'prompt.task_definition_coverage', provenance: { metric_version: 'example-metric-v1', provider: 'deterministic' }, scopeKey: 'example-coverage', strategy: 'consumer.rewrite.v1', generation: { model: 'example-reported-model', model_revision: 'example-version-1' }, variant: 'example-general', model: 'example-model-a', before: .25, after: .75, delta: .5, count: 2, excluded: 1 };
  const comparisons = { groups: [metric, { ...metric, variant: 'example-focused', model: 'example-model-b', before: .5, after: .5, delta: 0, count: 1, excluded: 0 }, { ...metric, scopeKey: 'example-unknown', metric: 'prompt.context_sufficiency', before: null, after: null, delta: null, count: 0, excluded: 3 }], truncated: false };
  await page.route('**/api/experiments', route => route.fulfill({ json: { experiments: [definition, { ...definition, stableId: 'example-other' }] } }));
  await page.route(/\/api\/runs(?:\?.*)?$/, route => route.fulfill({ json: historyResponse(runs, new URL(route.request().url()).searchParams, comparisons) }));
  return { runs, comparisons };
}
const filters = page => page.getByRole('form', { name: 'Filter runs' });
const charts = page => page.getByRole('region', { name: 'Run history charts' });

test('filters cover full history, persist with pagination and reset the cursor when changed', async ({ page }) => {
  await fixture(page); await page.goto('/experiments');
  await expect(page.locator('#all-runs .run-card')).toHaveCount(10);
  await expect(charts(page).locator('.history-totals')).toContainText('24Matching runs');
  await filters(page).getByLabel('Execution status').selectOption('failed');
  await filters(page).getByLabel('Experiment', { exact: true }).selectOption('example-widget');
  await filters(page).getByLabel('Revision', { exact: true }).selectOption('1');
  await filters(page).getByLabel('Model alias', { exact: true }).fill('example-model-a');
  await filters(page).getByLabel('Created from (UTC)').fill('2026-10-10');
  await filters(page).getByLabel('Created through (UTC)').fill('2026-10-10');
  await filters(page).getByRole('button', { name: 'Apply filters' }).click();
  await expect(page.locator('#all-runs .run-card')).toHaveCount(10);
  await expect(charts(page).locator('.history-totals')).toContainText('12Matching runs');
  await page.getByRole('link', { name: 'Older runs', exact: true }).click();
  await expect(page.locator('#all-runs .run-card')).toHaveCount(2);
  expect(new URL(page.url()).searchParams.get('status')).toBe('failed');
  await page.reload();
  await expect(page.locator('#all-runs .run-card')).toHaveCount(2);
  await expect(filters(page).getByLabel('Model alias', { exact: true })).toHaveValue('example-model-a');
  await filters(page).getByLabel('Trigger', { exact: true }).selectOption('ui');
  await filters(page).getByRole('button', { name: 'Apply filters' }).click();
  await expect(page.locator('#all-runs .run-card')).toHaveCount(6);
  expect(new URL(page.url()).searchParams.has('before')).toBe(false);
  await page.goBack(); await expect(page.locator('#all-runs .run-card')).toHaveCount(2);
  await filters(page).getByRole('link', { name: 'Reset filters' }).click();
  await expect(page).toHaveURL(/\/experiments$/);
  await expect(charts(page).locator('.history-totals')).toContainText('24Matching runs');
});

test('experiment history supports filters, keyboard chart navigation, and empty recovery', async ({ page }) => {
  await fixture(page); await page.goto('/experiments/example-widget?revision=1');
  await expect(page.locator('#runs .run-card')).toHaveCount(10);
  await expect(filters(page).getByLabel('Experiment', { exact: true })).toHaveCount(0);
  await charts(page).getByRole('link', { name: 'failed: 12 runs, filter runs', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(filters(page).getByLabel('Execution status')).toHaveValue('failed');
  await page.getByRole('link', { name: 'Older runs', exact: true }).click();
  await expect(page.locator('#runs .run-card')).toHaveCount(2);
  await filters(page).getByLabel('Model alias', { exact: true }).fill('example-missing');
  await filters(page).getByRole('button', { name: 'Apply filters' }).click();
  await expect(page.locator('#runs')).toContainText('No runs match these filters.');
  await expect(charts(page)).toContainText('No recorded metrics for these filters yet.');
  await filters(page).getByRole('link', { name: 'Reset filters' }).click();
  await expect(page).toHaveURL(/\/experiments\/example-widget\?revision=1$/);
  await expect(page.locator('#runs .run-card')).toHaveCount(10);
});

test('metric charts show pairs, models and variants, preserve unknowns and survive refresh', async ({ page }) => {
  const { runs } = await fixture(page); await page.goto('/experiments');
  const metrics = page.getByRole('region', { name: 'Metric comparisons' });
  await expect(metrics.getByRole('heading', { name: 'By generation model' })).toBeVisible();
  await expect(metrics.getByRole('heading', { name: 'By variant and model' })).toBeVisible();
  await expect(metrics).toContainText('example-model-b');
  await expect(metrics.locator('.comparison-overall')).toContainText('3 paired observations');
  await expect(metrics.locator('.comparison-overall')).toContainText('0.6667');
  await metrics.getByLabel('Metric and evaluation scope').selectOption('example-unknown');
  await expect(metrics.locator('.comparison-overall')).toContainText('Unknown');
  await expect(metrics.locator('.comparison-overall')).toContainText('0 paired observations');
  await filters(page).getByLabel('Model alias', { exact: true }).fill('example-unsaved');
  await charts(page).getByText('Daily counts', { exact: true }).click();
  await expect(charts(page).getByRole('cell', { name: '2026-10-10', exact: true })).toBeVisible();
  runs[0].status = 'failed';
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(charts(page).getByRole('link', { name: 'failed: 13 runs, filter runs', exact: true })).toBeVisible();
  await expect(metrics.getByLabel('Metric and evaluation scope')).toHaveValue('example-unknown');
  await expect(filters(page).getByLabel('Model alias', { exact: true })).toHaveValue('example-unsaved');
  await expect(charts(page).getByRole('cell', { name: '2026-10-10', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('invalid date range does not navigate or submit, and stale filtered responses cannot replace the page', async ({ page }) => {
  await fixture(page); await page.goto('/experiments');
  await filters(page).getByLabel('Created from (UTC)').fill('2026-10-11');
  await filters(page).getByLabel('Created through (UTC)').fill('2026-10-10');
  await filters(page).getByRole('button', { name: 'Apply filters' }).click();
  await expect(filters(page).getByLabel('Created through (UTC)')).toBeFocused();
  await expect(page).toHaveURL(/\/experiments$/);
  let release; const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/api/runs?status=failed**', async route => { await gate; await route.fallback(); });
  await charts(page).getByRole('link', { name: 'failed: 12 runs, filter runs', exact: true }).click();
  await page.locator('#breadcrumbs').getByRole('link', { name: 'Experiments', exact: true }).click();
  release();
  await expect(filters(page).getByLabel('Execution status')).toHaveValue('');
  await expect(charts(page).locator('.history-totals')).toContainText('24Matching runs');
});
