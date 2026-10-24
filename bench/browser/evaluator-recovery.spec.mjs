import { test, expect } from '@playwright/test';

test('evaluator interruption shows its cause and holds retry without a consumer binding', async ({ page }) => {
  let mutations = 0;
  page.on('request', request => { if (request.method() === 'POST') mutations++; });
  await page.route(/\/api\/runs\/[^/?]+$/, async route => {
    const response = await route.fetch(), run = await response.json();
    run.status = 'interrupted'; run.reconciliation_required = 1; run.cleanup_pending = 0;
    run.error_code = 'core_uncertain'; run.effective.consumerBinding = null;
    for (const unit of run.effective.units) { unit.consumerBinding = null; unit.stepSettings = {}; }
    const attempt = run.attempts[0];
    attempt.status = 'interrupted'; attempt.error_code = 'core_uncertain';
    attempt.result.status = 'uncertain'; attempt.result.consumer_binding = null;
    attempt.result.after = []; attempt.result.deltas = [];
    attempt.result.candidate = null; attempt.result.enhanced_prompt = null;
    attempt.result.errors = [{ code: 'gateway_io_timeout', stage: 'evaluate_original', retryable: false }];
    await route.fulfill({ json: run });
  });
  await page.goto('/');
  await page.locator('#all-runs').getByRole('link', { name: /Automatic run/ }).click();
  await expect(page.getByText('gateway_io_timeout (stage: evaluate_original)', { exact: true })).toBeVisible();
  await expect(page.getByText('Verify that all remote consumer and evaluator operations have stopped before releasing the execution slot.', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Reconciliation evidence reference')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirm remote stopped', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Rerun with changes', exact: true })).toHaveCount(0);
  const first = page.locator('.run-panel').first();
  await expect(first).toContainText('No enhanced prompt available.');
  await expect(first).not.toContainText('undefined');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(mutations).toBe(0);
});
