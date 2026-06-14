import { expect, type Page } from '@playwright/test';

const E2E_ADMIN_USERNAME = process.env.E2E_ADMIN_USERNAME ?? 'admin';
const E2E_ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'Admin12345678';
const PASSWORD_CANDIDATES = Array.from(new Set([
  E2E_ADMIN_PASSWORD,
  'Admin12345678',
  'TestAdmin@12345',
  'admin123',
  'admin',
]));

function testInput(page: Page, testId: string) {
  return page.getByTestId(testId);
}

export async function loginAsAdmin(page: Page): Promise<void> {
  let loggedIn = false;
  for (const password of PASSWORD_CANDIDATES) {
    await page.goto('/login');

    const usernameInput = testInput(page, 'login-username');
    const passwordInput = testInput(page, 'login-password');
    const submitButton = page.getByTestId('login-submit');

    await expect(usernameInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(submitButton).toBeVisible();

    await usernameInput.fill(E2E_ADMIN_USERNAME);
    await passwordInput.fill(password);
    await submitButton.click();
    try {
      await page.waitForFunction(() => !window.location.pathname.startsWith('/login'), null, {
        timeout: 5000,
      });
      loggedIn = true;
      break;
    } catch {
      // Try the next known local-dev password candidate.
    }
  }
  if (!loggedIn) {
    throw new Error(
      `Could not log in as ${E2E_ADMIN_USERNAME}. Set E2E_ADMIN_PASSWORD or seed the default admin account.`,
    );
  }
  await expect(page.locator('.el-menu')).toBeVisible({ timeout: 10000 });
}

export async function persistAuthTokenForStorageState(page: Page): Promise<void> {
  const accessToken = await page.evaluate(() => {
    const authState = window.sessionStorage.getItem('auth');
    if (authState) {
      try {
        const parsed = JSON.parse(authState);
        if (typeof parsed?.token === 'string' && parsed.token) {
          return parsed.token;
        }
      } catch {
        // Fall through to legacy storage below.
      }
    }
    return window.localStorage.getItem('token');
  });

  if (!accessToken) {
    throw new Error('Login succeeded, but no access token was persisted.');
  }

  await page.evaluate((token) => {
    window.localStorage.setItem('token', token);
  }, accessToken);
}

export function getAdminCredentials() {
  return {
    username: E2E_ADMIN_USERNAME,
    password: E2E_ADMIN_PASSWORD,
  };
}
