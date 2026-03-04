/**
 * take_screenshots.mjs
 *
 * Captures screenshots of each reachable page in TavernTails and saves them
 * to docs/screenshots/. Intended for use in CI (screenshot-update workflow)
 * and local development.
 *
 * Usage:
 *   BASE_URL=http://localhost:3000 node tools/take_screenshots.mjs
 *
 * Environment variables:
 *   BASE_URL   Frontend URL (default: http://localhost:3000)
 *
 * Requires:
 *   - A running frontend at BASE_URL
 *   - A running backend with the dev seed user (test@example.com / secret)
 *   - Playwright chromium browser installed (npx playwright install chromium)
 */

import { chromium } from 'playwright';
import { mkdir } from 'fs/promises';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const OUT_DIR = resolve(ROOT, 'docs', 'screenshots');
const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const VIEWPORT = { width: 1280, height: 800 };
const NAV_TIMEOUT = 15000;

async function shot(page, name) {
  const dest = resolve(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: dest, fullPage: false });
  console.log(`  ✓ ${name}.png`);
}

/**
 * Open the sidebar drawer, click a nav button by its visible text, then wait
 * for the view to settle. Waits for the CSS transition by polling for the
 * drawer-open class rather than using a fixed timeout.
 */
async function navTo(page, buttonText) {
  await page.click('[aria-label="Open navigation menu"]');
  // Wait for the drawer to slide in (CSS transition adds .drawer-open class)
  await page.waitForSelector('.dashboard-drawer.drawer-open', { timeout: 3000 });
  await page.locator('.dashboard-drawer.drawer-open button').filter({ hasText: buttonText }).click();
  await page.waitForTimeout(400);
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });

  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  const ctx = await browser.newContext({ viewport: VIEWPORT });
  const page = await ctx.newPage();

  // ── 1. Landing / Home page ────────────────────────────────────────────────
  console.log('Capturing: landing page');
  await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: NAV_TIMEOUT });
  await shot(page, '01-landing');

  // ── 2. Login form ─────────────────────────────────────────────────────────
  console.log('Capturing: login');
  await page.click('button:has-text("Sign In")');
  await page.waitForSelector('#loginEmail', { timeout: 5000 });
  await shot(page, '02-login');

  // ── 3. Sign-up form ───────────────────────────────────────────────────────
  console.log('Capturing: signup');
  await page.click('button:has-text("Create account")');
  await page.waitForSelector('#signupEmail', { timeout: 5000 });
  await shot(page, '03-signup');

  // ── 4. Dashboard home (log in with dev account) ───────────────────────────
  console.log('Capturing: dashboard home');
  await page.click('button.btn-ghost:has-text("Sign In")');
  await page.waitForSelector('#loginEmail', { timeout: 5000 });
  await page.fill('#loginEmail', 'test@example.com');
  await page.fill('#loginPassword', 'secret');
  await page.click('button[type="submit"]:has-text("Sign In")');
  await page.waitForSelector('.dashboard-root', { timeout: NAV_TIMEOUT });
  await page.waitForLoadState('networkidle');
  await shot(page, '04-dashboard');

  // ── 5. Manage Characters ──────────────────────────────────────────────────
  console.log('Capturing: characters');
  await navTo(page, 'Manage Characters');
  await shot(page, '05-characters');

  // ── 6. Import Character ───────────────────────────────────────────────────
  console.log('Capturing: import character');
  const importBtnCount = await page.locator('button:has-text("Import")').count();
  if (importBtnCount > 0) {
    await page.locator('button:has-text("Import")').first().click();
    await page.waitForTimeout(500);
    await shot(page, '06-import-character');
    const backBtnCount = await page.locator('button:has-text("Back"), button:has-text("Cancel")').count();
    if (backBtnCount > 0) {
      await page.locator('button:has-text("Back"), button:has-text("Cancel")').first().click();
      await page.waitForTimeout(400);
    }
  } else {
    console.log('  ⚠ No Import button visible – skipping');
  }

  // ── 7. Manage Campaigns ───────────────────────────────────────────────────
  console.log('Capturing: campaigns');
  await navTo(page, 'Manage Campaigns');
  await shot(page, '07-campaigns');

  // ── 8. New Campaign modal ─────────────────────────────────────────────────
  console.log('Capturing: new campaign modal');
  const newCampaignCount = await page.locator('[aria-label="New Campaign"]').count();
  if (newCampaignCount > 0) {
    await page.locator('[aria-label="New Campaign"]').first().click();
    await page.waitForTimeout(500);
    await shot(page, '08-new-campaign');
    // Fill in a campaign name and create it so the Settings and gameplay screenshots work.
    await page.locator('input[placeholder="Campaign name"]').fill('Screenshot Campaign');
    await page.locator('.modal button:has-text("Create")').click();
    // Wait for the modal to close and the campaign list to refresh.
    await page.waitForSelector('.modal', { state: 'hidden', timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(800);
  } else {
    console.log('  ⚠ No "New Campaign" button found – skipping');
  }

  // ── 9. Campaign settings ──────────────────────────────────────────────────
  console.log('Capturing: campaign settings');
  const settingsBtnCount = await page.locator('[aria-label="Settings"]').count();
  if (settingsBtnCount > 0) {
    await page.locator('[aria-label="Settings"]').first().click();
    await page.waitForTimeout(500);
    await shot(page, '09-campaign-settings');
  } else {
    console.log('  ⚠ No campaign Settings button – skipping');
  }

  // ── 10. Gameplay / Session view ───────────────────────────────────────────
  console.log('Capturing: gameplay / session');
  // Dismiss any alert dialog that may appear during session start.
  page.once('dialog', dialog => dialog.dismiss().catch(() => {}));
  const startSessionCount = await page.locator('button:has-text("Start Session")').count();
  if (startSessionCount > 0) {
    await page.locator('button:has-text("Start Session")').first().click();
    await page.waitForSelector('.gameplay-root, .gameplay-panel', { timeout: NAV_TIMEOUT });
    await page.waitForTimeout(800);
    await shot(page, '10-gameplay');
    // Return to dashboard home before taking remaining screenshots.
    const backBtnCount = await page.locator('button:has-text("Back to Dashboard"), button:has-text("Exit Session"), button[aria-label="Back"]').count();
    if (backBtnCount > 0) {
      await page.locator('button:has-text("Back to Dashboard"), button:has-text("Exit Session"), button[aria-label="Back"]').first().click();
      await page.waitForTimeout(600);
    }
  } else {
    console.log('  ⚠ No session start button visible – skipping');
  }

  // ── 11. Documents ─────────────────────────────────────────────────────────
  console.log('Capturing: documents');
  await navTo(page, 'Documents');
  await page.waitForTimeout(400);
  await shot(page, '11-documents');

  // ── 12. Explore ───────────────────────────────────────────────────────────
  console.log('Capturing: explore');
  await navTo(page, 'Explore');
  await page.waitForTimeout(400);
  await shot(page, '12-explore');

  // ── 13. Guides ────────────────────────────────────────────────────────────
  console.log('Capturing: guides');
  await navTo(page, 'Guides');
  await page.waitForTimeout(400);
  await shot(page, '13-guides');

  // ── 14. Account settings ──────────────────────────────────────────────────
  console.log('Capturing: account settings');
  await page.click('[aria-label="Account"]');
  await page.waitForTimeout(600);
  await shot(page, '14-account');

  // ── 15. Beyond 20 integration ─────────────────────────────────────────────
  console.log('Capturing: beyond 20');
  const beyond20BtnCount = await page.locator('button:has-text("Beyond 20 settings")').count();
  if (beyond20BtnCount > 0) {
    await page.locator('button:has-text("Beyond 20 settings")').first().click();
    await page.waitForTimeout(600);
    await shot(page, '15-beyond20');
  } else {
    console.log('  ⚠ No "Beyond 20 settings" button visible – skipping');
  }

  await browser.close();
  console.log(`\nAll screenshots saved to docs/screenshots/`);
}

main().catch((err) => {
  console.error('Screenshot capture failed:', err.message);
  process.exit(1);
});
