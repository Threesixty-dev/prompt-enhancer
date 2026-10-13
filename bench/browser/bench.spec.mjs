import { test, expect } from '@playwright/test';

test('inspect evidence, run immutable overrides, cancel, and retain status across reload', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await page.getByLabel('Operator access token').fill('example-operator-token-not-a-secret');
  await page.getByRole('button', { name: 'Open bench' }).click();
  await expect(page.getByRole('heading', { name: 'Test Bench', exact: true })).toBeVisible();
  await page.getByRole('button', { name: /Automatic.*revision/ }).first().click();
  await expect(page.getByRole('heading', { name: /Packaged clarification/ })).toBeVisible();
  await expect(page.getByText('Unknown values stay unknown.', { exact: false })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Before', exact: true }).first()).toBeVisible();
  await page.getByLabel('Parameter overrides (JSON)').fill('{"timeout_seconds":45}');
  await page.getByLabel('Experiment Unit selection').selectOption('script');
  await page.getByText('Objective and Experiment Unit steering', { exact: true }).click();
  await page.getByLabel('Steering overrides by Experiment Unit ID (JSON)').fill('{"script":{"focus":["acceptance"]}}');
  await page.getByRole('button', { name: 'Run with these settings' }).click();
  await expect(page.getByRole('button', { name: 'Cancel run', exact: true })).toBeVisible();
  await page.getByText('Immutable effective settings', { exact: true }).click();
  await expect(page.locator('#run-detail pre').first()).toContainText('"timeout_seconds": 45');
  await expect(page.locator('#run-detail pre').first()).toContainText('"acceptance"');
  await page.getByRole('button', { name: 'Cancel run', exact: true }).click();
  await expect(page.locator('#run-detail .badge.cancelled').first()).toBeVisible();
  await page.getByRole('button', { name: 'Rerun effective settings', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel run', exact: true })).toBeVisible();
  await expect(page.locator('#run-detail pre').first()).toContainText('"timeout_seconds": 45');
  await expect(page.locator('#run-detail pre').first()).toContainText('"acceptance"');
  await page.getByRole('button', { name: 'Cancel run', exact: true }).click();
  await expect(page.locator('#run-detail .badge.cancelled').first()).toBeVisible();
  await page.reload();
  await page.getByLabel('Operator access token').fill('example-operator-token-not-a-secret');
  await page.getByRole('button', { name: 'Open bench' }).click();
  await expect(page.locator('#runs .badge.cancelled').first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('invalid override is rejected without adding a run', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Operator access token').fill('example-operator-token-not-a-secret');
  await page.getByRole('button', { name: 'Open bench' }).click();
  await expect(page.getByRole('button', { name: 'Run with these settings' })).toBeVisible();
  const before = await page.locator('.run-card').count();
  await page.getByLabel('Parameter overrides (JSON)').fill('{"timeout_seconds":999999}');
  await page.getByRole('button', { name: 'Run with these settings' }).click();
  await expect(page.getByRole('status')).toContainText('invalid_override_parameters');
  expect(await page.locator('.run-card').count()).toBe(before);
});

test('consumer model override is retained by rerun', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Operator access token').fill('example-operator-token-not-a-secret');
  await page.getByRole('button', { name: 'Open bench' }).click();
  await page.getByLabel('Experiment Unit selection').selectOption('consumer');
  await page.getByText('Objective and Experiment Unit steering', { exact: true }).click();
  await page.getByLabel('Consumer bindings by Experiment Unit ID (JSON)').fill('{"consumer":{"binding_id":"example-browser-model"}}');
  await page.getByRole('button', { name: 'Run with these settings' }).click();
  await page.getByText('Immutable effective settings', { exact: true }).click();
  await expect(page.locator('#run-detail pre').first()).toContainText('example-browser-model');
  await page.getByRole('button', { name: 'Cancel run', exact: true }).click();
  await expect(page.locator('#run-detail .badge.cancelled').first()).toBeVisible();
  await page.getByRole('button', { name: 'Rerun effective settings', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Cancel run', exact: true })).toBeVisible();
  await expect(page.locator('#run-detail pre').first()).toContainText('example-browser-model');
  await page.getByRole('button', { name: 'Cancel run', exact: true }).click();
  await expect(page.locator('#run-detail .badge.cancelled').first()).toBeVisible();
});
