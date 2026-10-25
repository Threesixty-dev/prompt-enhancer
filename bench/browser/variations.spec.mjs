import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { historyResponse } from './history-fixture.mjs';

const definitionFile = new URL('../../experiments/example-clarification-focus.json', import.meta.url);
const resultFile = new URL('../../contracts/enhancement/examples/result.json', import.meta.url);
const matrix = page => page.getByRole('region', { name: 'Run variations', exact: true });
const editor = (page, id) => page.locator(`.strategy-editor[data-unit="${id}"]`);

async function fixture(page, { consumer = false } = {}) {
  const definition = JSON.parse(await readFile(definitionFile, 'utf8'));
  if (consumer) {
    definition.units[1].strategy = 'consumer.rewrite.v1';
    definition.consumerBinding = { binding_id: 'example-base-model', provider: 'inference' };
    definition.units[1].consumerBinding = { binding_id: 'example-unit-model' };
    definition.evaluatorProfile.evaluators.push({ evaluator_id: 'example-judge', kind: 'rubric', binding_id: 'example-judge-model', target: null, rubric: 'acceptance_testability', generation: null });
  }
  const effective = structuredClone(definition);
  effective.units = effective.units.map(unit => ({ ...unit, parameters: { ...effective.baseParameters, ...unit.parameters }, steering: { ...effective.baseSteering, ...unit.steering }, objective: { ...effective.objective, ...unit.objective }, consumerBinding: unit.strategy.startsWith('consumer.') ? { ...effective.consumerBinding, ...unit.consumerBinding } : null }));
  const run = { id: 'example-matrix-run', stable_id: definition.stableId, revision: '1', origin: 'ui', created: 1, status: 'running', assertion_outcome: 'not_evaluated', effective, events: [], attempts: [] };
  for (const subject of effective.subjects) for (const unit of effective.units) {
    const position = run.attempts.length;
    run.attempts.push({ id: 'example-attempt-' + position, position, unit_id: unit.id, subject_id: subject.id, status: position === 0 ? 'running' : 'queued', result: null });
  }
  const configuration = { enhancerVersion: effective.enhancerVersion, caseCount: effective.subjects.length, units: effective.units.map(({ id, strategy, consumerBinding }) => ({ id, strategy, consumerBinding })), evaluatorProfile: effective.evaluatorProfile };
  await page.route('**/api/experiments', route => route.fulfill({ json: { experiments: [definition] } }));
  await page.route(/\/api\/runs(?:\?.*)?$/, route => route.fulfill({ json: historyResponse([{ id: run.id, stable_id: run.stable_id, revision: run.revision, origin: run.origin, created: run.created, status: run.status, configuration }], new URL(route.request().url()).searchParams) }));
  await page.route('**/api/runs/example-matrix-run', route => route.fulfill({ json: run }));
  return { definition, run, configuration };
}

test('two cases and two scripted variants show four distinct attempts and clarification focus', async ({ page }) => {
  const { definition } = await fixture(page);
  await page.goto('/experiments/' + definition.stableId + '?revision=1');
  await expect(matrix(page)).toContainText('2 cases \u00b7 2 variants \u00b7 4 attempts');
  await expect(matrix(page).getByRole('cell')).toHaveCount(4);
  await expect(matrix(page).getByRole('rowheader')).toHaveCount(2);
  const general = matrix(page).getByRole('columnheader').filter({ hasText: 'General clarification' });
  const acceptance = matrix(page).getByRole('columnheader').filter({ hasText: 'Acceptance-focused clarification' });
  await expect(general).toContainText('goal, scope, context, constraints, acceptance, deliverable');
  await expect(acceptance).toContainText('Clarification focus: acceptance.');
  await expect(general).toContainText('No model (packaged script)');
  await expect(acceptance).toContainText('script.clarify.v1');
  await expect(matrix(page)).toContainText('Before / After compares the original and enhanced prompt within one attempt');
  await expect(matrix(page).getByRole('row').filter({ hasText: 'example-widget' })).toContainText('Attempt 1');
  await expect(matrix(page).getByRole('row').filter({ hasText: 'example-list' })).toContainText('Attempt 4');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('run design responds to selected cases, variants and model settings without starting work', async ({ page }) => {
  let submissions = 0;
  page.on('request', request => { if (request.method() === 'POST') submissions++; });
  const { definition } = await fixture(page, { consumer: true });
  await page.goto('/experiments/' + definition.stableId + '/runs/new?revision=1');
  await expect(matrix(page)).toContainText('2 cases \u00b7 2 variants \u00b7 4 attempts');
  await page.getByRole('checkbox', { name: 'example-list', exact: true }).uncheck();
  await expect(matrix(page)).toContainText('1 case \u00b7 2 variants \u00b7 2 attempts');
  await editor(page, 'general-clarification').getByRole('checkbox', { name: 'General clarification', exact: true }).uncheck();
  await expect(matrix(page)).toContainText('1 case \u00b7 1 variant \u00b7 1 attempt');
  await expect(matrix(page)).toContainText('example-unit-model (inference)');
  await editor(page, 'acceptance-clarification').getByLabel('Model alias', { exact: true }).fill('example-edited-model');
  await expect(matrix(page)).toContainText('example-edited-model (inference)');
  await editor(page, 'acceptance-clarification').getByText('Style and steering', { exact: true }).click();
  await editor(page, 'acceptance-clarification').getByRole('checkbox', { name: 'Goal', exact: true }).check();
  await expect(matrix(page)).toContainText('Focus: goal, acceptance.');
  await page.getByRole('checkbox', { name: 'example-widget', exact: true }).uncheck();
  await expect(matrix(page)).toContainText('0 cases \u00b7 1 variant \u00b7 0 attempts');
  await expect(matrix(page).getByRole('table')).toHaveCount(0);
  expect(submissions).toBe(0);
});

test('run matrix follows recorded attempts and exposes generation and both evaluation identities', async ({ page }) => {
  const { definition, run } = await fixture(page, { consumer: true });
  const result = JSON.parse(await readFile(resultFile, 'utf8'));
  result.consumer_provenance = { ...result.consumer_provenance, provider: 'example-provider', model: 'example-configured-model', reported_model: 'example-reported-model', model_revision: 'example-revision-7', identity_source: 'configured' };
  for (const side of ['before', 'after']) result[side].push({ evaluator_id: 'example-judge', kind: 'rubric', metrics: [], provenance: { provider: 'example-evaluation-provider', model: 'example-judge-model', reported_model: side === 'before' ? 'example-judge-before' : 'example-judge-after', model_revision: null, identity_source: 'configured' } });
  run.attempts[1].status = 'succeeded'; run.attempts[1].result = result;
  // Server position is the identity for numbering, even when delivery is out of order.
  run.attempts.reverse();
  await page.goto('/experiments/' + definition.stableId + '/runs/' + run.id);
  await expect(matrix(page).getByRole('link', { name: /Attempt 1:/ })).toContainText('running');
  const attemptLink = matrix(page).getByRole('link', { name: /Attempt 2:/ });
  await attemptLink.focus(); await page.keyboard.press('Enter');
  const panel = page.locator('#attempt-example-attempt-1');
  await expect(panel).toBeFocused();
  await expect(panel.getByRole('heading', { name: /^Attempt 2:/ })).toBeVisible();
  await expect(panel.locator('.model-evidence')).toContainText('example-reported-model');
  await expect(panel.locator('.model-evidence')).toContainText('example-revision-7');
  await expect(panel.locator('.model-evidence')).toContainText('example-judge-before');
  await expect(panel.locator('.model-evidence')).toContainText('example-judge-after');
  await expect(panel.locator('.model-evidence')).toContainText('Unknown');
  await expect(page.locator('#attempt-example-attempt-0')).toContainText('Reported model: unknown.');
  run.attempts.find(attempt => attempt.position === 0).status = 'failed';
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(matrix(page).getByRole('link', { name: /Attempt 1:/ })).toContainText('failed');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('long attempt prompts stay compact and expand independently across refresh', async ({ page }) => {
  const { definition, run } = await fixture(page);
  const original = 'Fictional example input. '.repeat(850) + 'EXAMPLE_ORIGINAL_TAIL';
  const enhanced = 'Fictional example output.\n'.repeat(850) + 'EXAMPLE_ENHANCED_TAIL';
  run.effective.subjects[0].text = original;
  run.attempts = [run.attempts[0]];
  run.attempts[0].result = JSON.parse(await readFile(resultFile, 'utf8'));
  run.attempts[0].result.enhanced_prompt = enhanced;
  await page.goto('/experiments/' + definition.stableId + '/runs/' + run.id);
  const comparison = page.locator('.comparison').first();
  await expect(comparison).toBeVisible();
  for (const prompt of await comparison.locator('.prompt').all()) {
    if (await prompt.isVisible()) expect((await prompt.boundingBox()).height).toBeLessThan(130);
  }
  expect((await matrix(page).locator('.case-preview').first().boundingBox()).height).toBeLessThan(60);
  const originalColumn = comparison.locator(':scope > div').nth(0);
  const enhancedColumn = comparison.locator(':scope > div').nth(1);
  await expect(originalColumn.locator('.prompt-preview')).not.toContainText('EXAMPLE_ORIGINAL_TAIL');
  await expect(enhancedColumn.locator('.prompt-preview')).not.toContainText('EXAMPLE_ENHANCED_TAIL');
  await expect(originalColumn.locator('.prompt-full')).toBeHidden();
  await expect(enhancedColumn.locator('.prompt-full')).toBeHidden();
  const showOriginal = originalColumn.locator('summary');
  await showOriginal.focus(); await page.keyboard.press('Enter');
  expect(await originalColumn.locator('.prompt-full').textContent()).toBe(original);
  await expect(originalColumn.locator('.prompt-full')).toBeVisible();
  await expect(enhancedColumn.locator('.prompt-full')).toBeHidden();
  run.attempts[0].status = 'succeeded';
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.locator('#attempt-example-attempt-0 .badge')).toHaveText('succeeded');
  await expect(originalColumn.locator('.prompt-full')).toBeVisible();
  await originalColumn.getByText('Show less original prompt', { exact: true }).click();
  await expect(originalColumn.locator('.prompt-full')).toBeHidden();
  await enhancedColumn.getByText('Show full enhanced prompt', { exact: true }).click();
  expect(await enhancedColumn.locator('.prompt-full').textContent()).toBe(enhanced);
  await expect(enhancedColumn.locator('.prompt-full')).toBeVisible();
  await enhancedColumn.getByText('Show less enhanced prompt', { exact: true }).click();
  await expect(enhancedColumn.locator('.prompt-full')).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('case previews expand in the matrix on experiment, setup and result pages', async ({ page }) => {
  const { definition, run } = await fixture(page);
  const text = 'Fictional example prompt.\n'.repeat(850) + 'EXAMPLE_CASE_TAIL';
  definition.subjects[0].text = text;
  run.effective.subjects[0].text = text;
  let submissions = 0;
  page.on('request', request => { if (request.method() === 'POST') submissions++; });
  const base = '/experiments/' + definition.stableId;
  for (const path of [base + '?revision=1', base + '/runs/new?revision=1', base + '/runs/' + run.id]) {
    await page.goto(path);
    const row = matrix(page).getByRole('rowheader').filter({ hasText: definition.subjects[0].id });
    const summary = row.locator('summary');
    await expect(row.getByText('Expand prompt', { exact: true })).toBeVisible();
    await expect(row.locator('.case-full')).toBeHidden();
    await summary.focus(); await page.keyboard.press('Enter');
    await expect(row.getByText('Collapse prompt', { exact: true })).toBeVisible();
    await expect(row.locator('.case-preview')).toBeHidden();
    await expect(row.locator('.case-full')).toBeVisible();
    expect(await row.locator('.case-full').textContent()).toBe(text);
    expect((await row.locator('.case-full').boundingBox()).height).toBeLessThanOrEqual(384);
    await expect(matrix(page).getByRole('rowheader').nth(1).locator('.case-full')).toBeHidden();
    if (path.endsWith(run.id)) {
      run.attempts[0].status = 'failed';
      await page.getByRole('button', { name: 'Refresh', exact: true }).click();
      await expect(matrix(page).getByRole('link', { name: /Attempt 1:/ })).toContainText('failed');
      await expect(row.locator('.case-full')).toBeVisible();
    }
    await summary.focus(); await page.keyboard.press('Space');
    await expect(row.getByText('Expand prompt', { exact: true })).toBeVisible();
    await expect(row.locator('.case-full')).toBeHidden();
    expect((await row.locator('.case-preview').boundingBox()).height).toBeLessThan(60);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  expect(submissions).toBe(0);
});

test('run cards preserve saved model choices and counts independently of experiment defaults', async ({ page }) => {
  const { definition, run, configuration } = await fixture(page, { consumer: true });
  configuration.caseCount = 1; configuration.units = [configuration.units[1]];
  configuration.units[0].consumerBinding = { binding_id: 'example-saved-model', provider: 'inference' };
  run.effective.subjects = [run.effective.subjects[0]];
  run.effective.units = [{ ...run.effective.units[1], consumerBinding: configuration.units[0].consumerBinding }];
  run.status = 'cancelled'; run.attempts = [];
  await page.goto('/experiments');
  const card = page.locator('#all-runs .run-card');
  await expect(card).toContainText('1 case \u00b7 1 variant \u00b7 1 attempt');
  await expect(card).toContainText('example-saved-model');
  await expect(card).not.toContainText('example-unit-model');
  await expect(page.locator('.experiment-card')).toContainText('example-unit-model');
  await expect(card).toContainText('example-judge-model');
  await page.goto('/experiments/' + definition.stableId + '?revision=1');
  await expect(page.locator('#runs .run-card')).toContainText('example-saved-model');
  await page.goto('/experiments/' + definition.stableId + '/runs/' + run.id);
  await expect(matrix(page)).toContainText('Not recorded');
  await expect(matrix(page).getByRole('link')).toHaveCount(0);
  await page.getByRole('link', { name: 'Rerun with changes', exact: true }).click();
  await expect(matrix(page)).toContainText('1 case \u00b7 1 variant \u00b7 1 attempt');
  await expect(matrix(page)).toContainText('example-saved-model');
});
