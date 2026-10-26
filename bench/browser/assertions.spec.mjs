import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { historyResponse } from './history-fixture.mjs';

const summary = page => page.getByRole('region', { name: 'Run quality assertions', exact: true });
const details = page => page.getByRole('region', { name: 'Attempt quality assertions', exact: true });
const assertion = (key, operator = 'minimum_delta', threshold = 0) => ({ evaluator_id: 'prompt', metric_key: key, operator, threshold });

async function fixture(page) {
  const definition = JSON.parse(await readFile(new URL('../examples/example-widget.json', import.meta.url), 'utf8'));
  const result = JSON.parse(await readFile(new URL('../../contracts/enhancement/examples/result.json', import.meta.url), 'utf8'));
  definition.units = [definition.units[0]];
  const checks = [assertion('prompt.acceptance_testability'), assertion('example.zero', 'minimum_value')];
  definition.units[0].assertions = checks;
  const effective = structuredClone(definition);
  for (const side of ['before', 'after']) result[side] = [{ ...result[side][0], metrics: [
    { key: checks[0].metric_key, state: 'known', value: side === 'before' ? 1 : 0.75 },
    { key: checks[1].metric_key, state: 'known', value: 0 },
  ] }];
  result.deltas = [{ evaluator_id: 'prompt', metric_key: checks[0].metric_key, state: 'comparable', value: -0.25 }];
  result.assertions = [{ assertion: checks[0], outcome: 'failed', observed: -0.25 }, { assertion: checks[1], outcome: 'passed', observed: 0 }];
  result.assertion_outcome = 'failed';
  const attempt = { id: 'example-assertion-attempt', position: 0, unit_id: effective.units[0].id, subject_id: effective.subjects[0].id, status: 'succeeded', result };
  const run = { id: 'example-assertion-run', stable_id: definition.stableId, revision: definition.revision, origin: 'ui', created: 1,
    status: 'succeeded', assertion_outcome: 'failed', effective, events: [], attempts: [attempt] };
  const configuration = { enhancerVersion: effective.enhancerVersion, caseCount: 1, subjectIds: effective.subjects.map(s => s.id), units: effective.units, evaluatorProfile: effective.evaluatorProfile };
  const posts = [], errors = [];
  page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()); });
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/experiments', route => route.fulfill({ json: { experiments: [definition] } }));
  await page.route(/\/api\/runs(?:\?.*)?$/, route => route.fulfill({ json: historyResponse([{
    id: run.id, stable_id: run.stable_id, revision: run.revision, origin: run.origin, created: run.created,
    status: run.status, assertion_outcome: run.assertion_outcome, configuration,
  }], new URL(route.request().url()).searchParams) }));
  await page.route('**/api/runs/' + run.id, route => route.fulfill({ json: run }));
  return { run, attempt, result, checks, posts, errors, path: '/experiments/' + definition.stableId + '/runs/' + run.id };
}

test('a successful execution exposes its failed assertion in history, summary and attempt details', async ({ page }) => {
  const data = await fixture(page);
  await page.goto('/runs');
  const card = page.locator('#all-runs .run-card');
  await expect(card).toContainText('Execution: succeeded');
  await expect(card).toContainText('Assertions: Failed');
  await card.click();
  await expect(summary(page)).toContainText('Execution: succeeded');
  await expect(summary(page)).toContainText('1 passed \u00b7 1 failed');
  await expect(summary(page).getByRole('heading', { name: '1 failed quality assertion' })).toBeVisible();
  await expect(summary(page)).toContainText('prompt.acceptance_testability: expected Change (after - before) >= 0; observed -0.25.');
  expect(await summary(page).evaluate(element => element.compareDocumentPosition(document.querySelector('.experiment-flow')) & Node.DOCUMENT_POSITION_FOLLOWING)).toBeTruthy();
  const matrixLink = page.getByRole('region', { name: 'Run variations', exact: true }).getByRole('link', { name: /Attempt 1:/ });
  await expect(matrixLink).toContainText('Execution: succeeded');
  await expect(matrixLink).toContainText('Assertions: Failed');
  await expect(matrixLink).toHaveAttribute('data-assertion-outcome', 'failed');
  const failedLink = summary(page).getByRole('link', { name: /Attempt 1:/ });
  await failedLink.focus(); await page.keyboard.press('Enter');
  await expect(page.locator('#attempt-example-assertion-attempt')).toBeFocused();
  const check = details(page).getByRole('listitem').filter({ hasText: 'prompt.acceptance_testability' });
  await expect(check).toBeVisible();
  await expect(check).toContainText('Before: 1 / After: 0.75');
  await expect(check).toContainText('Change (after - before) >= 0');
  await expect(check.locator('dd').nth(1)).toHaveText('-0.25');
  const zero = details(page).getByRole('listitem').filter({ hasText: 'example.zero' });
  await expect(zero).toContainText('After value >= 0');
  await expect(zero.locator('dd').nth(1)).toHaveText('0');
  await expect(page.locator('details[open]')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(data.posts).toEqual([]); expect(data.errors).toEqual([]);
});

test('unknown checks explain missing candidates, abstention and incompatible evaluator identities', async ({ page }) => {
  const { run, result, path } = await fixture(page);
  result.assertion_outcome = run.assertion_outcome = 'unknown';
  result.enhanced_prompt = null; result.after = [];
  result.before[0].metrics[0] = { key: 'prompt.acceptance_testability', state: 'abstained', reason: 'rubric_abstained', value: null };
  result.deltas[0] = { ...result.deltas[0], state: 'unknown', value: null, reason: 'workflow_no_candidate' };
  result.assertions.forEach(check => { check.outcome = 'unknown'; check.observed = null; });
  await page.goto(path);
  await expect(summary(page)).toContainText('2 unknown');
  await expect(summary(page)).not.toContainText('failed quality assertion');
  await expect(details(page)).toContainText('Abstained: rubric evaluator declined to classify');
  await expect(details(page)).toContainText('After: Not recorded');
  await expect(details(page)).toContainText('No numeric delta: workflow produced no candidate');
  await expect(details(page).locator('.assertion-facts dd').nth(1)).toHaveText('Not recorded');
  result.deltas[0].reason = 'provenance_mismatch';
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(details(page)).toContainText('No numeric delta: evaluator identities or versions differ');
  await expect(details(page)).not.toContainText('undefined');
});

test('configured checks without results stay distinct from an experiment with no assertions', async ({ page }) => {
  const { run, attempt, result, path } = await fixture(page);
  attempt.result = null; attempt.status = run.status = 'queued'; run.assertion_outcome = 'not_evaluated';
  await page.goto(path);
  await expect(summary(page)).toContainText('2 not evaluated');
  await expect(details(page).locator('.assertion-outcome')).toHaveText('Assertions: Not evaluated');
  await expect(page.locator('.attempt-cell')).toContainText('Assertions: Not evaluated');
  await expect(details(page).locator('.assertion-check[data-outcome=not_evaluated]')).toHaveCount(2);
  attempt.status = run.status = 'succeeded'; attempt.result = result;
  result.assertions = []; result.assertion_outcome = 'not_evaluated';
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(summary(page)).toContainText('2 not recorded');
  await expect(details(page).locator('.assertion-check[data-outcome=not_recorded]')).toHaveCount(2);
  run.effective.units[0].assertions = [];
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(summary(page)).toContainText('No quality assertions configured for this run.');
  await expect(details(page)).toContainText('No quality assertions configured for this attempt.');
  await expect(details(page).getByRole('listitem')).toHaveCount(0);
  delete run.effective.units[0].assertions;
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(summary(page)).toContainText('Assertion configuration not recorded.');
  await expect(summary(page)).not.toContainText('No quality assertions configured');
});

test('refresh preserves disclosures and exact threshold values without inferring outcomes from rounding', async ({ page }) => {
  const { run, result, path } = await fixture(page);
  result.assertions[0].observed = -0.0000001;
  await page.goto(path);
  const check = details(page).getByRole('listitem').first();
  await expect(check.locator('dd').nth(1)).toHaveText('-1e-7');
  await expect(check.locator('.assertion-state')).toHaveText('Failed');
  await page.getByText('Show full original prompt', { exact: true }).click();
  result.assertions[0].observed = 0;
  result.assertions[0].outcome = result.assertion_outcome = run.assertion_outcome = 'passed';
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(summary(page)).toContainText('2 passed');
  await expect(summary(page).getByRole('link')).toHaveCount(0);
  await expect(summary(page)).toHaveCount(1);
  await expect(details(page)).toHaveCount(1);
  await expect(check.locator('dd').nth(1)).toHaveText('0');
  await expect(page.locator('.prompt-full').first()).toBeVisible();
  await expect(page.locator('.attempt-cell')).toContainText('Assertions: Passed');
});

test('recorded checks match their rules even when reordered, and text cannot create markup', async ({ page }) => {
  const { result, path, errors } = await fixture(page);
  result.assertions.reverse();
  result.assertions.push({ assertion: assertion('<img src=x onerror=alert(1)>', 'example_future_rule'), outcome: 'unknown', observed: null });
  await page.goto(path);
  const rows = details(page).getByRole('listitem');
  await expect(rows).toHaveCount(3);
  await expect(rows.nth(0)).toContainText('Failed');
  await expect(rows.nth(1)).toContainText('Passed');
  await expect(rows.nth(2)).toContainText('<img src=x onerror=alert(1)>');
  await expect(rows.nth(2)).toContainText('Unrecognized rule: example_future_rule');
  await expect(details(page).locator('img')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('a historical failed outcome remains visible when detailed checks are absent', async ({ page }) => {
  const { run, result, path } = await fixture(page);
  result.assertions = []; delete run.effective.units[0].assertions;
  await page.goto(path);
  await expect(summary(page)).toContainText('Assertions: Failed');
  await expect(summary(page)).toContainText('individual failed-check details are unavailable');
  await expect(summary(page)).not.toContainText('0 failed');
});
