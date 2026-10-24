import { test, expect } from '@playwright/test';

for (const [failure, trigger, recovery] of [
  ['network loss', 'manual', 'reload'],
  ['gateway HTML response', 'automatic', 'automatic'],
  ['expired JSON session', 'manual', 'manual'],
]) {
  test(`${failure} marks retained results stale and recovers without another run`, async ({ page }) => {
    let submissions = 0;
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith('/api/runs')) submissions++;
    });
    await page.goto('/');
    await page.locator('.experiment-card').filter({ hasText: 'Clarify a fictional widget request' }).click();
    await page.getByRole('link', { name: /Automatic run/ }).first().click();
    await expect(page.locator('#run-detail')).toBeVisible();
    const runUrl = page.url();
    const heading = await page.locator('#page-title').innerText();
    const measurements = await page.locator('.metric-readings').first().innerText();

    let failures = 0;
    await page.route('**/api/experiments', route => {
      failures++;
      return failure === 'network loss' ? route.abort('failed') : route.fulfill(failure === 'gateway HTML response'
        ? { status: 200, contentType: 'text/html', body: '<html>Fictional gateway login</html>' }
        : { status: 401, json: { error: { code: 'unauthorized' } } });
    });
    if (trigger === 'manual') await page.getByRole('button', { name: 'Refresh', exact: true }).click();

    await expect(page.getByRole('status')).toContainText('Displayed results may be out of date.', { timeout: 6000 });
    await expect(page.getByRole('button', { name: 'Reload to reconnect', exact: true })).toBeVisible();
    await expect(page.locator('#page-title')).toHaveText(heading);
    await expect(page.locator('.metric-readings').first()).toHaveText(measurements, { useInnerText: true });
    await expect(page.locator('input[type=password]')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    if (trigger === 'automatic') {
      await page.getByRole('button', { name: 'Reload to reconnect', exact: true }).focus();
      await expect.poll(() => failures, { timeout: 6000 }).toBeGreaterThanOrEqual(2);
      await expect(page.getByRole('button', { name: 'Reload to reconnect', exact: true })).toBeFocused();
    }

    await page.unroute('**/api/experiments');
    if (recovery === 'reload') await page.getByRole('button', { name: 'Reload to reconnect', exact: true }).click();
    if (recovery === 'manual') await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Reload to reconnect', exact: true })).toHaveCount(0, { timeout: 6000 });
    await expect(page).toHaveURL(runUrl);
    await expect(page.locator('#page-title')).toHaveText(heading);
    await expect(page.locator('#notice')).not.toContainText('Displayed results may be out of date.');
    await expect(page.locator('.metric-readings').first()).toHaveText(measurements, { useInnerText: true });
    expect(submissions).toBe(0);
  });
}
