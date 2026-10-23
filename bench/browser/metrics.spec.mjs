import { test, expect } from '@playwright/test';

const reading = (key, state, extra = {}) => ({ key, state, value: null, label: null, reason: 'example', ...extra });

test('results distinguish missing, unknown, abstained, ineligible, failed and categorical readings', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.route(/\/api\/runs\/[^/?]+$/, async route => {
    const response = await route.fetch(), run = await response.json();
    for (const attempt of run.attempts) {
      if (!attempt.result) continue;
      const result = attempt.result, evaluator = result.before[0];
      result.before = [{ ...evaluator, metrics: [
        reading('example.zero', 'known', { value: 0 }),
        reading('example.constraint', 'unknown', { reason: 'constraints_unobserved' }),
        reading('example.rubric', 'abstained', { reason: 'rubric_abstained' }),
        reading('example.ineligible', 'not_applicable', { reason: 'example_task_ineligible' }),
        reading('example.failure', 'execution_error', { reason: 'evaluator_failed' }),
        reading('example.nli', 'known', { label: 'neutral' }),
        reading('example.nli-limit', 'unknown', { reason: 'input_too_long' }),
      ] }];
      result.after = [{ ...evaluator, metrics: [
        reading('example.zero', 'known', { value: 0.5 }),
        reading('example.constraint', 'known', { value: 1 }),
        reading('example.rubric', 'known', { label: 'present' }),
        reading('example.ineligible', 'not_applicable', { reason: 'example_task_ineligible' }),
        reading('example.failure', 'known', { value: 0 }),
        reading('example.nli', 'known', { label: 'entailment' }),
        reading('example.nli-limit', 'known', { label: 'neutral' }),
        reading('example.after-only', 'known', { value: 1 }),
      ] }];
      result.deltas = result.before[0].metrics.map(metric => ({
        evaluator_id: evaluator.evaluator_id, metric_key: metric.key,
        state: metric.key === 'example.zero' ? 'comparable' : metric.key === 'example.nli' ? 'not_comparable' : 'unknown',
        value: metric.key === 'example.zero' ? 0.5 : null,
        reason: metric.key === 'example.zero' ? 'same_evaluator' : metric.key === 'example.nli' ? 'categorical_metric' : 'metric_unknown',
      }));
    }
    await route.fulfill({ json: run });
  });
  await page.goto('/');
  await page.locator('#all-runs').getByRole('link', { name: /Automatic run/ }).click();
  const panel = page.getByRole('region', { name: 'Evaluator measurements' }).first();
  await expect(panel.locator('.measurement-coverage')).toHaveText('Before and after: 9 known \u00b7 2 unknown \u00b7 1 abstained \u00b7 2 not applicable \u00b7 1 evaluation error \u00b7 1 not recorded');
  await expect(panel.getByRole('row').filter({ hasText: 'example.zero' }).getByRole('cell').nth(1)).toHaveText('0');
  await expect(panel).toContainText('Unknown: no constraint clause detected');
  await expect(panel).toContainText('Unknown: input exceeds the evaluator token limit');
  await expect(panel).toContainText('Abstained: rubric evaluator declined to classify');
  await expect(panel).toContainText('Evaluation error: evaluator request failed');
  await expect(panel).toContainText('No numeric delta: before abstained, after known');
  await expect(panel).toContainText('neutral \u2192 entailment (categorical)');
  await expect(panel.getByRole('row').filter({ hasText: 'example.after-only' }).getByRole('cell').nth(1)).toHaveText('Not recorded');
  await expect(panel).not.toContainText('undefined');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
