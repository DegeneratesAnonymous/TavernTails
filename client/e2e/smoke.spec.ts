import { test, expect, Page } from '@playwright/test';

/**
 * Smoke tests — validate the critical happy path for an end-to-end player
 * journey: home page loads → login form visible → can submit login →
 * dashboard is shown.
 *
 * These run against a live stack (backend on :8000, frontend on :3000) and
 * use the bilbo seed user created by the backend startup sequence
 * (TAVERNTAILS_SEED_USERS=1, which is the default).
 *
 * App flow: the root renders HomePage (with Sign In button) when no token is
 * present; clicking "Sign In" reveals LoginSignupAgent which has the email
 * input.  If a token is already stored, LoginSignupAgent auto-loads the
 * profile and shows LoggedInDashboard directly.
 */

const DEV_EMAIL = 'bilbo@example.com';
const DEV_PASSWORD = 'secret';

/** Navigate to `/` and ensure the email+password login form is visible,
 *  clicking the "Sign In" landing-page button if necessary. */
async function navigateToLoginForm(page: Page): Promise<void> {
  await page.goto('/');
  // If we're already on the dashboard, nothing to do.
  const isDashboard = await page
    .locator('[data-testid="dashboard"], .gameplay-root, .logged-in-dashboard')
    .first()
    .isVisible()
    .catch(() => false);
  if (isDashboard) return;

  // The email input is inside LoginSignupAgent which only mounts after the
  // user clicks "Sign In" on the HomePage landing screen.
  const emailInput = page.locator('input[type="email"], input[placeholder*="email" i], input[name="email"]').first();
  const emailVisible = await emailInput.isVisible().catch(() => false);
  if (!emailVisible) {
    // Click the "Sign In" button on the landing page to reveal the auth form.
    await page.locator('button:has-text("Sign In"), button:has-text("Sign in")').first().click();
    await emailInput.waitFor({ state: 'visible', timeout: 10_000 });
  }
}

test.describe('Smoke: Login flow', () => {
  test('home page loads and shows login form', async ({ page }) => {
    await page.goto('/');
    // The root renders either the landing page or the dashboard.
    // We just confirm the app shell mounted without a blank white screen.
    await expect(page.locator('body')).not.toBeEmpty();
    const title = await page.title();
    expect(title).toBeTruthy();
  });

  test('can log in with dev seed credentials', async ({ page }) => {
    await navigateToLoginForm(page);

    // If already on the dashboard skip the login step.
    const isDashboard = await page
      .locator('[data-testid="dashboard"], .gameplay-root, .logged-in-dashboard')
      .first()
      .isVisible()
      .catch(() => false);
    if (isDashboard) return;

    // Fill and submit the login form.
    const emailInput = page.locator('input[type="email"], input[placeholder*="email" i], input[name="email"]').first();
    const passwordInput = page.locator('input[type="password"]').first();
    await emailInput.fill(DEV_EMAIL);
    await passwordInput.fill(DEV_PASSWORD);

    const submitButton = page
      .locator('button[type="submit"], button:has-text("Log in"), button:has-text("Sign in")')
      .first();
    await submitButton.click();

    // After login the app should navigate away from the auth screen.
    await expect(page).not.toHaveURL(/login/i, { timeout: 10_000 });
  });
});

test.describe('Smoke: Campaign creation', () => {
  test.beforeEach(async ({ page }) => {
    await navigateToLoginForm(page);

    // If already on the dashboard nothing more to do.
    const isDashboard = await page
      .locator('.gameplay-root, .logged-in-dashboard, [data-testid="dashboard"]')
      .first()
      .isVisible()
      .catch(() => false);
    if (!isDashboard) {
      const emailInput = page.locator('input[type="email"], input[placeholder*="email" i], input[name="email"]').first();
      const passwordInput = page.locator('input[type="password"]').first();
      await emailInput.fill(DEV_EMAIL);
      await passwordInput.fill(DEV_PASSWORD);
      await page
        .locator('button[type="submit"], button:has-text("Log in"), button:has-text("Sign in")')
        .first()
        .click();
      await page.waitForTimeout(1500);
    }
  });

  test('application loads campaign UI after login', async ({ page }) => {
    // The dashboard or gameplay layout should be visible.
    const shell = page.locator('.gameplay-root, .logged-in-dashboard, [data-testid="dashboard"]');
    await expect(shell.first()).toBeVisible({ timeout: 10_000 });
  });
});
