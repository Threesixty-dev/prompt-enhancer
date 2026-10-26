import { test, expect } from '@playwright/test';

async function recoveryFixture(page, { cleanup = false } = {}) {
  const state = { confirmed: false, requested: false, mutations: [], run: null };
  await page.route(/\/api\/recovery$/, async route => {
    if (!state.run) {
      const response = await route.fetch();
      await route.fulfill({ response }); return;
    }
    await route.fulfill({ json: { schemaVersion: 'bench-recovery-queue/v1', blocked: !state.confirmed,
      total: state.confirmed ? 0 : 1, truncated: false, runs: state.confirmed ? [] : [state.run] } });
  });
  await page.route(/\/api\/runs\/[^/?]+$/, async route => {
    const response = await route.fetch(), run = await response.json();
    run.status = 'interrupted'; run.reconciliation_required = state.confirmed ? 0 : 1;
    run.cleanup_pending = cleanup ? 1 : 0; run.error_code = 'core_uncertain';
    run.failure = { code: 'gateway_io_timeout', stage: 'evaluate_original', operationId: null,
      subjectId: 'example-boundary-case', unitId: 'example-concise', attemptId: run.attempts[0].id, attemptPosition: 0 };
    run.recovery = { nextAction: cleanup ? (state.requested ? 'wait_for_cleanup' : 'retry_cleanup') : 'confirm_remote_stop',
      cleanupCheck: cleanup ? { attempts: state.requested ? 0 : 3, checked_at: 1792800000,
        next_check: state.requested ? 1792800100 : null, error_code: 'container_operation_unconfirmed' } : null,
      reconciliation: state.confirmed ? { evidence_reference: 'operator-confirmation-00000000000040008000000000000001', created: 1792800200 } : null };
    run.attempts[0].status = 'interrupted'; run.attempts[0].result.status = 'uncertain';
    run.attempts[0].result.errors = [{ code: 'gateway_io_timeout', stage: 'evaluate_original', retryable: false }];
    state.run = run;
    await route.fulfill({ json: run });
  });
  await page.route(/\/api\/runs\/[^/?]+\/(reconcile|cleanup-check)$/, async route => {
    const action = route.request().url().split('/').pop();
    state.mutations.push({ action, body: route.request().postDataJSON() });
    if (action === 'reconcile') state.confirmed = true;
    if (action === 'cleanup-check') state.requested = true;
    await route.fulfill({ status: action === 'cleanup-check' ? 202 : 200, json: {} });
  });
  await page.goto('/runs');
  await page.locator('#all-runs').getByRole('link', { name: /Automatic run/ }).click();
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  return state;
}

test('timeout cause and unresolved recovery are prominent across pages and filters', async ({ page }) => {
  const state = await recoveryFixture(page);
  const issue = page.getByRole('region', { name: 'Execution issue', exact: true });
  await expect(issue).toContainText('gateway_io_timeout');
  await expect(issue).toContainText('Evaluating the original prompt');
  await expect(issue).toContainText('remote request may have finished');
  const recovery = page.getByRole('region', { name: 'Run recovery', exact: true });
  await expect(recovery).toContainText('Cleanup confirmed');
  await expect(recovery).toContainText('Completion unconfirmed');
  await expect(recovery).toContainText('automatic remote verification unavailable');
  await expect(recovery).toContainText('never replays');
  await expect(page.getByRole('link', { name: 'Rerun with changes', exact: true })).toHaveCount(0);
  await page.goto('/runs?status=succeeded');
  const banner = page.getByRole('region', { name: 'Queue recovery', exact: true });
  await expect(banner).toContainText('Queue paused: recovery required');
  await expect(banner).toContainText('gateway_io_timeout');
  await banner.getByRole('link', { name: /Open blocked run/ }).click();
  await expect(issue).toBeVisible();
  expect(state.mutations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('remote stop confirmation needs no typing and retains its automatic record and failure', async ({ page }) => {
  const state = await recoveryFixture(page);
  const recovery = page.getByRole('region', { name: 'Run recovery', exact: true });
  await expect(recovery.getByRole('textbox')).toHaveCount(0);
  await expect(recovery).toContainText('Bench saves this confirmation with the run and time automatically');
  const button = page.getByRole('button', { name: 'Confirm remote stopped', exact: true });
  const acknowledgement = page.getByRole('checkbox', { name: 'I verified that the affected remote operations finished or stopped.' });
  await expect(button).toBeDisabled();
  await acknowledgement.check();
  await expect(button).toBeEnabled();
  await acknowledgement.uncheck();
  await expect(button).toBeDisabled();
  expect(state.mutations).toHaveLength(0);
  await acknowledgement.check();
  await button.click();
  await expect(page.getByRole('heading', { name: 'Recovery recorded', exact: true })).toBeVisible();
  await expect(recovery).toContainText('Confirmation record: operator-confirmation-00000000000040008000000000000001');
  await expect(recovery).toContainText('Stopped - operator confirmed');
  await expect(page.getByRole('region', { name: 'Execution issue', exact: true })).toContainText('gateway_io_timeout');
  await expect(page.getByRole('region', { name: 'Queue recovery', exact: true })).toBeHidden();
  await expect(page.getByRole('link', { name: 'Rerun with changes', exact: true })).toBeVisible();
  expect(state.mutations).toEqual([{ action: 'reconcile', body: { remoteStopped: true } }]);
});

test('bounded cleanup retry is distinct from remote stop or execution replay', async ({ page }) => {
  const state = await recoveryFixture(page, { cleanup: true });
  const recovery = page.getByRole('region', { name: 'Run recovery', exact: true });
  await expect(recovery).toContainText('3 / 3');
  await expect(recovery).toContainText('container_operation_unconfirmed');
  await expect(page.getByRole('button', { name: 'Confirm remote stopped', exact: true })).toBeDisabled();
  await page.getByRole('checkbox', { name: 'I verified that the affected remote operations finished or stopped.' }).check();
  await expect(page.getByRole('button', { name: 'Confirm remote stopped', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Retry container cleanup', exact: true }).click();
  await expect(recovery).toContainText('Next cleanup check:');
  await expect(page.getByRole('button', { name: 'Retry container cleanup', exact: true })).toHaveCount(0);
  await expect(recovery).toContainText('Completion unconfirmed');
  expect(state.mutations).toEqual([{ action: 'cleanup-check', body: {} }]);
});

test('run list shows the cause alongside recorded execution status', async ({ page }) => {
  await page.route(/\/api\/runs(?:\?.*)?$/, async route => {
    const response = await route.fetch(), value = await response.json();
    value.runs[0].status = 'interrupted'; value.runs[0].reconciliation_required = 1;
    value.runs[0].failure = { code: 'gateway_io_timeout', stage: 'evaluate_original' };
    await route.fulfill({ json: value });
  });
  await page.goto('/runs');
  const card = page.locator('#all-runs .run-card').first();
  await expect(card).toContainText('Execution issue: gateway_io_timeout / evaluate_original');
  await expect(card).toContainText('Recovery required - queue paused');
  await expect(card).toContainText('interrupted');
});
