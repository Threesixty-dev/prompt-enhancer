import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

async function fixture(page, workflowId = 'prompt-check', version = '1.0.0', definitionFile = '../examples/example-versioned-review.json') {
  const definition = JSON.parse(await readFile(new URL(definitionFile, import.meta.url), 'utf8'));
  const catalog = JSON.parse(await readFile(new URL('../../contracts/enhancement/workflows.json', import.meta.url), 'utf8'));
  const workflow = catalog.find(item => item.workflow_id === workflowId && item.version === version);
  definition.workflow = Object.fromEntries(['workflow_id', 'version', 'definition_sha256'].map(key => [key, workflow[key]]));
  definition.units[0].strategy = workflow.strategy;
  const effective = structuredClone(definition);
  effective.units = effective.units.map(unit => ({ ...unit, parameters: effective.baseParameters, objective: effective.objective, steering: effective.baseSteering, consumerBinding: effective.consumerBinding }));
  const run = { id: 'example-versioned-run', stable_id: definition.stableId, revision: definition.revision, status: 'succeeded', effective, attempts: [], events: [], origin: 'ui', created: 1 };
  await page.route('**/api/experiments', route => route.fulfill({ json: { experiments: [definition] } }));
  await page.route('**/api/runs/example-versioned-run', route => route.fulfill({ json: run }));
  return { definition, run };
}

for (const [id, version] of [['prompt-check', '1.1.0'], ['prompt-rewrite', '2.1.0'], ['prompt-clarify', '2.1.0']]) {
  test(`${id} diagram follows its revision, evaluator order and selected variant`, async ({ page }) => {
    const { definition } = await fixture(page, id, version, `../../experiments/example-robustness-${id}-20261023-r4.json`);
    await page.goto('/experiments/' + definition.stableId + '?revision=4');
    const flow = page.getByRole('region', { name: 'Experiment flow', exact: true });
    await expect(flow.getByRole('heading', { name: 'Experiment flow', exact: true })).toBeVisible();
    await expect(flow).toContainText('20 cases');
    await expect(flow).toContainText('80 attempts');
    await expect(flow.getByRole('list', { name: 'Before evaluator order' }).locator('strong')).toHaveText(definition.evaluatorProfile.evaluators.map(e => e.evaluator_id));
    await expect(flow.getByRole('list', { name: 'After evaluator order' }).locator('strong')).toHaveText(definition.evaluatorProfile.evaluators.map(e => e.evaluator_id));
    await expect(flow.getByRole('list', { name: 'Diagram workflow steps' }).getByRole('listitem')).toHaveText(['Score prompt', 'Infer context', 'Optional model review and rewrite']);
    await expect(flow).toContainText('Harness scores are kept outside its model input');
    await expect(flow).toContainText('provider managed (unknown)');
    await flow.getByLabel('Flow variant').selectOption('structured');
    await expect(flow).toContainText(definition.units.find(u => u.id === 'structured').stepSettings.review.policy.policy_id);
    await flow.getByLabel('Flow variant').selectOption('diagnostics-only');
    await expect(flow).toContainText('No model (diagnostics only)');
    await expect(flow).toContainText('The review step is skipped');
    await expect(flow.getByRole('list', { name: 'After evaluator order' })).toHaveCount(0);
    await expect(flow).toContainText('After measurements are absent');
    await expect(flow).toContainText('operator reconciliation');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

test('run diagram uses frozen binding and policies, and shows safe validation diagnostics', async ({ page }) => {
  const { definition, run } = await fixture(page);
  run.status = 'failed';
  run.continuation = { decision: 'continue_independent_case', reason: 'completed_invalid_review', replayAllowed: false };
  run.effective.units[0].stepSettings = { review: { binding: { binding_id: 'example-frozen-model', provider: 'inference' } } };
  run.attempts = [{ id: 'example-invalid-attempt', position: 0, unit_id: run.effective.units[0].id,
    subject_id: run.effective.subjects[0].id, status: 'failed', result: {
      status: 'failed', before: [], after: [], deltas: [], errors: [{ code: 'workflow_review_reply_invalid', stage: 'generate' }],
      workflow_result: { workflow: definition.workflow, steps: [{ step_id: 'review', status: 'failed' }], review: {
        state: 'reply_invalid', validation_issue: { reason: 'enum_mismatch', field: 'reformulated_elements[1].element' }, findings: [],
      } },
    } }];
  await page.goto('/experiments/' + definition.stableId + '/runs/' + run.id);
  await expect(page.getByRole('region', { name: 'Experiment flow', exact: true })).toContainText('example-frozen-model (inference)');
  await expect(page.getByText('Validation: enum_mismatch at reformulated_elements[1].element.', { exact: true })).toBeVisible();
  await expect(page.locator('.continuation-guidance')).toContainText('Independent cases may continue after preflight');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('diagram follows the chosen revision and does not invent a missing workflow manifest', async ({ page }) => {
  const { definition } = await fixture(page);
  const later = structuredClone(definition);
  later.revision = '2'; later.generation = 2;
  later.workflow.version = '99.0.0';
  later.units[0].stepSettings = { review: { binding: { binding_id: 'example-later-model', provider: 'inference' } } };
  await page.route('**/api/experiments', route => route.fulfill({ json: { experiments: [later, definition] } }));
  await page.goto('/experiments/' + definition.stableId + '?revision=1');
  const flow = page.getByRole('region', { name: 'Experiment flow', exact: true });
  await expect(flow.getByRole('list', { name: 'Diagram workflow steps' }).getByRole('listitem')).toHaveText([
    'Score prompt', 'Infer context', 'Optional model review and rewrite',
  ]);
  await page.goto('/experiments/' + definition.stableId + '?revision=2');
  await expect(flow).toContainText('example-later-model (inference)');
  await expect(flow).toContainText('Workflow manifest unavailable for this exact revision.');
  await expect(flow.getByRole('list', { name: 'Diagram workflow steps' })).toHaveText('Workflow order unknown');
});

for (const [id, title] of [['prompt-rewrite', 'Rewrite review'], ['prompt-clarify', 'Clarification review']]) {
  test(`${id} displays the pre-Bench sequence and submits the review model`, async ({ page }) => {
    const { definition } = await fixture(page, id, '2.0.0');
    let submitted;
    await page.route(/\/api\/runs$/, async route => {
      submitted = route.request().postDataJSON();
      await route.fulfill({ json: { runId: 'example-versioned-run' } });
    });
    await page.goto('/experiments/' + definition.stableId + '?revision=1');
    await expect(page.getByRole('heading', { name: title + ' (pre-Bench flow)', exact: true })).toBeVisible();
    await expect(page.getByRole('list', { name: 'Workflow logic steps' }).getByRole('listitem')).toHaveText([
      'Score prompt', 'Infer context', 'Optional model review and rewrite',
    ]);
    await page.getByRole('link', { name: 'New run', exact: true }).click();
    await expect(page.getByText(id + ' / 2.0.0', { exact: true })).toBeVisible();
    await expect(page.getByText('Objective and targets', { exact: true })).toHaveCount(0);
    await page.locator('#example-review-steps-review-binding-mode').selectOption('value');
    await page.locator('#example-review-steps-review-binding-binding_id').fill('example-review-alternate');
    await page.locator('#example-review-steps-review-binding-provider').selectOption('"inference"');
    await expect(page.locator('#run-preview')).toContainText('example-review-alternate (inference)');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.getByRole('button', { name: 'Start run', exact: true }).click();
    await expect.poll(() => submitted).toBeTruthy();
    expect(submitted.overrides.unitStepSettings['example-review'].review.binding.binding_id).toBe('example-review-alternate');
    await expect(page.getByRole('heading', { name: title + ' (pre-Bench flow)', exact: true })).toBeVisible();
  });
}

test('legacy clarification remains visibly distinct from the pre-Bench flow', async ({ page }) => {
  const { definition } = await fixture(page, 'prompt-clarify');
  await page.goto('/experiments/' + definition.stableId + '?revision=1');
  await expect(page.getByRole('heading', { name: 'Rule-based clarification (Bench legacy)', exact: true })).toBeVisible();
  await expect(page.getByRole('list', { name: 'Workflow logic steps' }).getByRole('listitem')).toHaveText([
    'Score prompt', 'Add clarification placeholders',
  ]);
});

test('versioned run form fixes workflow and evaluation while allowing model and policy changes', async ({ page }) => {
  const { definition } = await fixture(page);
  let submitted;
  await page.route(/\/api\/runs$/, async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ json: { runId: 'example-versioned-run' } });
  });
  await page.goto('/experiments/' + definition.stableId + '/runs/new?revision=1');
  await expect(page.getByText('prompt-check / 1.0.0', { exact: true })).toBeVisible();
  await expect(page.getByText(definition.coreBuild.image, { exact: true })).toBeVisible();
  await expect(page.getByText('Workflow, step implementations, core build and harness evaluation stay fixed.', { exact: false })).toBeVisible();
  await page.locator('#example-review-steps-review-binding-mode').selectOption('value');
  await page.locator('#example-review-steps-review-binding-binding_id').fill('example-alternate-model');
  await page.locator('#example-review-steps-review-binding-provider').selectOption('"inference"');
  await page.locator('#example-review-steps-review-policy-mode').selectOption('value');
  await page.locator('#example-review-steps-review-policy-policy_id').fill('example-review-policy');
  await page.locator('#example-review-steps-review-policy-revision').fill('1');
  await page.locator('#example-review-steps-review-policy-instructions').fill('Review the fictional prompt and return the required JSON.');
  await expect(page.locator('#run-preview')).toContainText('example-alternate-model (inference)');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Start run', exact: true }).click();
  await expect.poll(() => submitted).toBeTruthy();
  expect(submitted.overrides.unitStepSettings['example-review'].review.binding.binding_id).toBe('example-alternate-model');
  expect(submitted.overrides.unitStepSettings['example-review'].review.policy.policy_id).toBe('example-review-policy');
  expect(submitted.overrides).not.toHaveProperty('workflow');
  expect(submitted.overrides).not.toHaveProperty('evaluatorProfile');
  expect(submitted.overrides).not.toHaveProperty('coreBuild');
});

test('review-only results show commentary and unavailable after measurements', async ({ page }) => {
  const { definition, run } = await fixture(page);
  const unit = run.effective.units[0], subject = run.effective.subjects[0];
  run.attempts = [{ id: 'example-review-attempt', position: 0, unit_id: unit.id, subject_id: subject.id, status: 'succeeded', result: {
    enhanced_prompt: null, before: [], after: [], deltas: [], workflow_result: {
      workflow: definition.workflow, steps: [], diagnostics: [], review: {
        state: 'ok', notes: 'The fictional request needs no rewrite.', findings: [],
      },
    },
  } }];
  await page.goto('/experiments/' + definition.stableId + '/runs/' + run.id);
  await expect(page.getByRole('heading', { name: 'Workflow review', exact: true })).toBeVisible();
  await expect(page.getByText('Valid review', { exact: true })).toBeVisible();
  await expect(page.getByText('The fictional request needs no rewrite.', { exact: true })).toBeVisible();
  await expect(page.getByText('This workflow returned no rewrite. After measurements and deltas remain unavailable.', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const [reviewState, label] of [['reply_invalid', 'Review failed: invalid response'], ['model_error', 'Review failed: model request failed']]) {
  for (const status of ['failed', 'succeeded']) {
    test(`${reviewState} is visible with recorded execution status ${status}`, async ({ page }) => {
      const { definition, run } = await fixture(page);
      const unit = run.effective.units[0], subject = run.effective.subjects[0];
      run.status = status;
      run.attempts = [{ id: 'example-review-attempt', position: 0, unit_id: unit.id, subject_id: subject.id, status, result: {
        enhanced_prompt: null, before: [], after: [], deltas: [], errors: status === 'failed'
          ? [{ code: 'workflow_review_' + reviewState, stage: 'generate', retryable: false }] : [],
        workflow_result: { workflow: definition.workflow, diagnostics: [],
          steps: [{ step_id: 'diagnose', status: 'succeeded' }, { step_id: 'context', status: 'succeeded' }, { step_id: 'review', status: 'failed' }],
          review: { state: reviewState, notes: null, findings: [] },
        },
      } }];
      await page.goto('/experiments/' + definition.stableId + '/runs/' + run.id);
      await expect(page.getByText(label, { exact: true })).toBeVisible();
      if (reviewState === 'reply_invalid') await expect(page.getByText('Detailed validation cause: unknown (not recorded by this core).', { exact: true })).toBeVisible();
      await expect(page.getByText('Workflow failed. Retained measurements are partial evidence; this attempt is not a valid completed review.', { exact: true })).toBeVisible();
      await expect(page.getByRole('list', { name: 'Recorded workflow steps' }).getByRole('listitem')).toHaveText([
        'diagnose: succeeded', 'context: succeeded', 'review: failed',
      ]);
      await expect(page.getByText('No valid rewrite is available because the workflow failed. After measurements and deltas are unavailable.', { exact: true })).toBeVisible();
      await expect(page.getByText('This workflow returned no rewrite. After measurements and deltas remain unavailable.', { exact: true })).toHaveCount(0);
      if (status === 'succeeded') {
        await expect(page.getByText('Historical status mismatch:', { exact: false })).toBeVisible();
        await expect(page.locator('.run-heading .badge')).toHaveText('succeeded');
      } else {
        await expect(page.getByText('workflow_review_' + reviewState + ' (stage: generate)', { exact: true })).toBeVisible();
        await expect(page.getByText('Historical status mismatch:', { exact: false })).toHaveCount(0);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
}

test('optional review without a model is explicitly skipped', async ({ page }) => {
  const { definition, run } = await fixture(page);
  const unit = run.effective.units[0], subject = run.effective.subjects[0];
  run.attempts = [{ id: 'example-review-attempt', position: 0, unit_id: unit.id, subject_id: subject.id, status: 'succeeded', result: {
    enhanced_prompt: null, before: [], after: [], deltas: [], workflow_result: {
      workflow: definition.workflow, steps: [{ step_id: 'review', status: 'skipped' }], diagnostics: [],
      review: { state: 'no_active_model', notes: null, findings: [] },
    },
  } }];
  await page.goto('/experiments/' + definition.stableId + '/runs/' + run.id);
  await expect(page.getByText('Review skipped: no model configured', { exact: true })).toBeVisible();
  await expect(page.getByRole('list', { name: 'Recorded workflow steps' })).toHaveText('review: skipped');
  await expect(page.getByText('Workflow failed.', { exact: false })).toHaveCount(0);
});
