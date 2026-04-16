import { expect, Page } from '@playwright/test';

const E2E_ADMIN_USERNAME = process.env.E2E_ADMIN_USERNAME ?? 'admin';
const E2E_ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'Admin12345678';

function testInput(page: Page, testId: string) {
  return page.getByTestId(testId);
}

export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto('/login');

  const usernameInput = testInput(page, 'login-username');
  const passwordInput = testInput(page, 'login-password');
  const submitButton = page.getByTestId('login-submit');

  await expect(usernameInput).toBeVisible();
  await expect(passwordInput).toBeVisible();
  await expect(submitButton).toBeVisible();

  await usernameInput.fill(E2E_ADMIN_USERNAME);
  await passwordInput.fill(E2E_ADMIN_PASSWORD);
  await submitButton.click();
  await page.waitForFunction(() => !window.location.pathname.startsWith('/login'), null, {
    timeout: 10000,
  });
  await expect(page.locator('.el-menu')).toBeVisible({ timeout: 10000 });
}

export function getAdminCredentials() {
  return {
    username: E2E_ADMIN_USERNAME,
    password: E2E_ADMIN_PASSWORD,
  };
}
