import { test, expect } from '@playwright/test';

async function form(page) {
  await page.goto('/experiments/example-widget/runs/new?revision=1');
  await expect(page.getByRole('heading', { name: 'Evaluators', exact: true })).toBeVisible();
}
const row = (page, number) => page.locator(`[data-evaluator="${number}"]`);
async function settings(page) {
  await page.getByText('Effective run settings', { exact: true }).click();
  return JSON.parse(await page.locator('details[data-key=effective] pre').textContent());
}
async function cancel(page) {
  await page.getByRole('button', { name: 'Cancel run', exact: true }).click();
  await expect(page.locator('#run-detail .badge.cancelled').first()).toBeVisible();
}

test('multiple evaluator models are frozen, previewed, and retained when rerunning', async ({ page }) => {
  await form(page);
  await page.getByRole('button', { name: 'Add evaluator', exact: true }).click();
  await row(page, 2).getByLabel('Evaluator model alias', { exact: true }).fill('example-qwen');
  await row(page, 2).getByLabel('Evaluation criterion', { exact: true }).selectOption('"constraint_precision"');
  await page.getByRole('button', { name: 'Add evaluator', exact: true }).click();
  await row(page, 3).getByLabel('Evaluator model alias', { exact: true }).fill('example-other-judge');
  await expect(page.locator('#run-preview .model-summary')).toContainText('example-qwen (rubric) / example-other-judge (rubric)');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel run', exact: true })).toBeVisible();
  const initial = await settings(page);
  expect(initial.evaluatorProfile.evaluators).toEqual([
    { evaluator_id: 'prompt', kind: 'deterministic', binding_id: 'deterministic.v1', target: null, rubric: null, generation: null },
    { evaluator_id: 'evaluator-2', kind: 'rubric', binding_id: 'example-qwen', rubric: 'constraint_precision' },
    { evaluator_id: 'evaluator-3', kind: 'rubric', binding_id: 'example-other-judge', rubric: 'acceptance_testability' },
  ]);
  expect(initial.evaluatorProfile.revision).toMatch(/^run-/);
  const previousUrl = page.url();
  await cancel(page);
  await page.getByRole('link', { name: 'Rerun with changes', exact: true }).click();
  await expect(row(page, 2).getByLabel('Evaluator model alias', { exact: true })).toHaveValue('example-qwen');
  await expect(row(page, 2).getByLabel('Evaluation criterion', { exact: true })).toHaveValue('"constraint_precision"');
  await row(page, 2).getByLabel('Evaluator model alias', { exact: true }).fill('example-routed-model');
  await row(page, 3).getByRole('button', { name: 'Remove evaluator 3', exact: true }).click();
  await expect(page.locator('#run-preview .model-summary')).not.toContainText('example-other-judge');
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel run', exact: true })).toBeVisible();
  const rerun = await settings(page);
  expect(rerun.evaluatorProfile.evaluators).toHaveLength(2);
  expect(rerun.evaluatorProfile.evaluators[1].binding_id).toBe('example-routed-model');
  expect(rerun.evaluatorProfile.revision).not.toBe(initial.evaluatorProfile.revision);
  await cancel(page);
  await page.goto(previousUrl);
  expect((await settings(page)).evaluatorProfile).toEqual(initial.evaluatorProfile);
});

test('typed evaluator controls reject incomplete routes and preserve explicit generation nulls', async ({ page }) => {
  let submitted;
  await page.route('**/api/runs', async route => {
    if (route.request().method() === 'POST') submitted = route.request().postDataJSON();
    await route.continue();
  });
  await form(page);
  await page.getByRole('button', { name: 'Add evaluator', exact: true }).click();
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  expect(submitted).toBeUndefined();
  const judge = row(page, 2);
  await judge.getByLabel('Evaluator model alias', { exact: true }).fill('example-judge');
  await judge.getByText('Evaluator generation settings', { exact: true }).click();
  await judge.getByLabel('Evaluation generation setting', { exact: true }).selectOption('value');
  await judge.getByLabel('Maximum tokens setting', { exact: true }).selectOption('null');
  await judge.getByLabel('Temperature setting', { exact: true }).selectOption('value');
  await judge.getByLabel('Temperature', { exact: true }).fill('0');
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel run', exact: true })).toBeVisible();
  expect(submitted.overrides.evaluators[1].generation).toEqual({ max_tokens: null, temperature: 0 });
  await cancel(page);
  await page.getByRole('link', { name: 'Rerun with changes', exact: true }).click();
  await judge.getByLabel('Evaluation method', { exact: true }).selectOption('embedding');
  await judge.getByLabel('Evaluator model alias', { exact: true }).fill('example-embedding');
  await judge.getByLabel('Reference text', { exact: true }).fill('A fictional acceptance contract.');
  await expect(judge.getByLabel('Evaluation criterion')).toHaveCount(0);
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel run', exact: true })).toBeVisible();
  expect(submitted.overrides.evaluators[1]).toEqual({ evaluator_id: 'evaluator-2', kind: 'embedding', binding_id: 'example-embedding', target: 'A fictional acceptance contract.' });
  await cancel(page);
});

test('removing an evaluator used by assertions produces an actionable error', async ({ page }) => {
  await form(page);
  await page.getByRole('button', { name: 'Add evaluator', exact: true }).click();
  await row(page, 2).getByLabel('Evaluator model alias', { exact: true }).fill('example-qwen');
  await row(page, 1).getByRole('button', { name: 'Remove evaluator 1', exact: true }).click();
  await expect(row(page, 2).getByRole('button', { name: 'Remove evaluator 2', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Keep evaluators referenced by the experiment’s assertions');
  await expect(page.getByRole('heading', { name: 'New run', exact: true })).toBeVisible();
});
