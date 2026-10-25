import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { historyResponse } from './history-fixture.mjs';

async function fixture(page, { cases = 1, variants = 1 } = {}) {
  const definition = JSON.parse(await readFile(new URL('../../experiments/example-robustness-prompt-check-20261023-r6.json', import.meta.url), 'utf8'));
  const effective = structuredClone(definition);
  effective.subjects = effective.subjects.slice(0, cases);
  effective.units = effective.units.slice(0, variants);
  const configuration = {
    caseCount: cases, subjectIds: effective.subjects.map(subject => subject.id), workflow: effective.workflow,
    units: effective.units.map(unit => ({ id: unit.id, strategy: unit.strategy })),
  };
  const run = { id: 'example-selected-run', stable_id: definition.stableId, revision: definition.revision,
    status: 'cancelled', origin: 'ui', created: 1, effective, configuration, attempts: [], events: [] };
  const runs = [run];
  await page.route('**/api/experiments', route => route.fulfill({ json: { experiments: [definition] } }));
  await page.route(/\/api\/runs(?:\?.*)?$/, route => route.fulfill({ json: historyResponse(
    runs.map(({ effective, attempts, events, ...summary }) => summary), new URL(route.request().url()).searchParams,
  ) }));
  await page.route('**/api/runs/example-selected-run', route => route.fulfill({ json: run }));
  return { definition, run, runs };
}

test('single-pair run names and scope agree across history, details and refresh', async ({ page }) => {
  const { definition, run } = await fixture(page);
  await page.route('**/api/experiments', route => route.fulfill({ json: { experiments: [
    { ...definition, revision: '7', title: 'Newer example revision' }, definition,
  ] } }));
  const title = 'Prompt Check \u00b7 example-sparse \u00b7 concise';
  for (const path of ['/experiments', '/experiments/' + definition.stableId + '?revision=6']) {
    await page.goto(path);
    const card = page.locator('.run-card');
    await expect(card.locator('.run-title')).toHaveText(title);
    await expect(card.locator('.run-subtitle')).toHaveText('Selected: 1 case \u00b7 1 variant \u00b7 1 attempt');
    await expect(card).toContainText('Experiment: ' + definition.title);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.locator('.run-card').focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(new RegExp('/runs/' + run.id + '$'));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
  await expect(page.locator('#page-description')).toHaveText('Selected: 1 case \u00b7 1 variant \u00b7 1 attempt / revision 6');
  await expect(page.locator('#run-detail')).toContainText('Full experiment matrix: 20 cases \u00b7 4 variants \u00b7 80 attempts');
  await expect(page).toHaveTitle(title + ' | Experiment Bench');
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const experiment = page.getByRole('link', { name: 'View experiment', exact: true });
  await expect(experiment).toHaveAttribute('href', '/experiments/' + definition.stableId + '?revision=6');
  await experiment.focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(new RegExp('/experiments/' + definition.stableId + '\\?revision=6$'));
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(definition.title);
  await expect(page.getByLabel('Revision', { exact: true })).toHaveValue('6');
});

test('different selections from one experiment have distinct titles', async ({ page }) => {
  const { run, runs } = await fixture(page);
  runs.push({ ...run, id: 'example-other-run', configuration: { ...run.configuration,
    subjectIds: ['example-complete'], units: [{ id: 'structured', strategy: 'prompt.check.v1' }] } });
  await page.goto('/experiments');
  await expect(page.locator('.run-title')).toHaveText([
    'Prompt Check \u00b7 example-sparse \u00b7 concise',
    'Prompt Check \u00b7 example-complete \u00b7 structured',
  ]);
});

test('multi-pair titles use the selected matrix rather than the full definition', async ({ page }) => {
  const { definition, run } = await fixture(page, { cases: 2, variants: 2 });
  await page.goto('/experiments');
  await expect(page.locator('.run-title')).toHaveText('Prompt Check \u00b7 2 cases \u00b7 2 variants');
  await expect(page.locator('.run-subtitle')).toHaveText('Selected: 2 cases \u00b7 2 variants \u00b7 4 attempts');
  await page.goto('/experiments/' + definition.stableId + '/runs/' + run.id);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Prompt Check \u00b7 2 cases \u00b7 2 variants');
  await expect(page.locator('#page-description')).toContainText('Selected: 2 cases \u00b7 2 variants \u00b7 4 attempts');
  await expect(page.locator('#run-detail')).toContainText('Full experiment matrix: 20 cases \u00b7 4 variants \u00b7 80 attempts');
});

test('older metadata keeps known counts and never borrows unselected cases', async ({ page }) => {
  const { run, runs } = await fixture(page);
  delete run.configuration.subjectIds;
  runs.push({ ...run, id: 'example-missing-run', configuration: undefined });
  await page.goto('/experiments');
  await expect(page.locator('.run-title')).toHaveText(['Prompt Check \u00b7 1 case \u00b7 concise', 'Run example-']);
  await expect(page.locator('.run-subtitle')).toHaveText([
    'Selected: 1 case \u00b7 1 variant \u00b7 1 attempt', 'Selected: Attempt count unknown',
  ]);
  for (const title of await page.locator('.run-title').allTextContents()) {
    expect(title).not.toContain('example-sparse');
    expect(title).not.toContain('20 cases');
  }
});

test('legacy runs and long identifiers stay readable without changing experiment titles', async ({ page }) => {
  const { definition, run } = await fixture(page);
  delete definition.workflow; delete run.effective.workflow; delete run.configuration.workflow;
  const subject = 'example-' + 's'.repeat(72), unit = 'example-' + 'v'.repeat(72);
  run.configuration.subjectIds = [subject]; run.configuration.units[0].id = unit;
  run.effective.subjects[0].id = subject; run.effective.units[0].id = unit;
  await page.goto('/experiments');
  await expect(page.locator('.run-title')).toHaveText('Run \u00b7 ' + subject + ' \u00b7 ' + unit);
  await expect(page.locator('.experiment-card h3')).toHaveText(definition.title);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.locator('.run-card').click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Run \u00b7 ' + subject + ' \u00b7 ' + unit);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
