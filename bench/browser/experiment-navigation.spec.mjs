import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { historyResponse } from './history-fixture.mjs';

test('experiment search and progress filters retain their URL and top navigation state', async ({ page }) => {
  const base = JSON.parse(await readFile(new URL('../examples/example-widget.json', import.meta.url), 'utf8'));
  const definitions = [base,
    { ...base, stableId: 'example-other', title: 'Another fictional experiment' },
    { ...base, stableId: 'example-empty', title: 'Unused fictional experiment' }];
  const runs = [
    { id: 'example-partial-run', stable_id: base.stableId, revision: base.revision, status: 'running',
      origin: 'ui', created: 2, attemptProgress: { finished: 1, total: 4 } },
    { id: 'example-finished-run', stable_id: 'example-other', revision: base.revision, status: 'succeeded',
      origin: 'gitops', created: 1, attemptProgress: { finished: 4, total: 4 } },
  ];
  await page.route('**/api/experiments', route => route.fulfill({ json: { experiments: definitions } }));
  await page.route(/\/api\/runs(?:\?.*)?$/, route => route.fulfill({ json: historyResponse(runs, new URL(route.request().url()).searchParams) }));
  await page.goto('/experiments');
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  const form = page.getByRole('form', { name: 'Filter experiments' });
  await expect(nav.getByRole('link', { name: 'Experiments' })).toHaveAttribute('aria-current', 'page');
  await expect(page.locator('#experiments .experiment-card')).toHaveCount(3);
  await form.getByLabel('Search experiments').fill('OTHER');
  await form.getByLabel('Progress').selectOption('finished');
  await form.getByRole('button', { name: 'Apply filters' }).click();
  await expect(page).toHaveURL(/\/experiments\?q=OTHER&progress=finished$/);
  await expect(page.locator('#experiments .experiment-card')).toHaveCount(1);
  await expect(page.locator('#experiments .experiment-card')).toContainText('Another fictional experiment');
  await expect(page.locator('#experiment-count')).toHaveText('1 of 3 experiments');
  await page.reload();
  await expect(form.getByLabel('Search experiments')).toHaveValue('OTHER');
  await expect(form.getByLabel('Progress')).toHaveValue('finished');
  await expect(page.locator('#experiments .experiment-card')).toHaveCount(1);
  await nav.getByRole('link', { name: 'Runs' }).click();
  await expect(page).toHaveURL(/\/runs$/);
  await expect(nav.getByRole('link', { name: 'Runs' })).toHaveAttribute('aria-current', 'page');
  await page.goBack();
  await expect(page.locator('#experiments .experiment-card')).toHaveCount(1);
  await form.getByLabel('Search experiments').fill('');
  await form.getByLabel('Progress').selectOption('no-runs');
  await form.getByRole('button', { name: 'Apply filters' }).click();
  await expect(page.locator('#experiments .experiment-card')).toContainText('Unused fictional experiment');
  await form.getByLabel('Progress').selectOption('unfinished');
  await form.getByRole('button', { name: 'Apply filters' }).click();
  await expect(page.locator('#experiments .experiment-card')).toContainText(base.title);
  await form.getByLabel('Search experiments').fill('nothing matches');
  await form.getByRole('button', { name: 'Apply filters' }).click();
  await expect(page.getByText('No experiments match these filters. Adjust or reset the filters.')).toBeVisible();
  await form.getByRole('button', { name: 'Reset filters' }).click();
  await expect(page).toHaveURL(/\/experiments$/);
  await expect(page.locator('#experiments .experiment-card')).toHaveCount(3);
  await nav.getByRole('link', { name: 'Stats' }).click();
  await expect(nav.getByRole('link', { name: 'Stats' })).toHaveAttribute('aria-current', 'page');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('skeletons stay visible while initial and route data are loading', async ({ page }) => {
  let releaseExperiments, releaseRuns;
  const experimentsGate = new Promise(resolve => { releaseExperiments = resolve; });
  const runsGate = new Promise(resolve => { releaseRuns = resolve; });
  await page.route('**/api/experiments', async route => { await experimentsGate; await route.continue(); });
  await page.route(/\/api\/runs(?:\?.*)?$/, async route => {
    if (new URL(route.request().url()).pathname === '/api/runs' && page.url().endsWith('/runs')) await runsGate;
    await route.continue();
  });
  await page.goto('/experiments');
  await expect(page.locator('#workspace')).toBeVisible();
  await expect(page.locator('#page-content')).toHaveAttribute('aria-busy', 'true');
  await expect(page.getByText('Loading experiments...')).toBeVisible();
  await expect(page.locator('.skeleton-card')).toHaveCount(3);
  await expect(page.locator('.skeleton-stack')).toHaveAttribute('aria-hidden', 'true');
  releaseExperiments();
  await expect(page.locator('#experiments .experiment-card')).toBeVisible();
  await expect(page.locator('.skeleton-card')).toHaveCount(0);
  await expect(page.locator('#page-content')).toHaveAttribute('aria-busy', 'false');
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Runs' }).click();
  await expect(page.getByText('Loading runs...')).toBeVisible();
  await expect(page.locator('.skeleton-card')).toHaveCount(2);
  releaseRuns();
  await expect(page.locator('#all-runs .run-card').first()).toBeVisible();
  await expect(page.locator('.skeleton-card')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
