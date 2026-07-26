import { readFile } from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { expect, type Page } from '@playwright/test';

const E2E_ADMIN_USERNAME = process.env.E2E_ADMIN_USERNAME ?? 'admin';
const E2E_ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'Admin12345678';
const E2E_LOCALE = process.env.E2E_LOCALE ?? 'zh-CN';
const PASSWORD_CANDIDATES = Array.from(new Set([
  E2E_ADMIN_PASSWORD,
  'Admin12345678',
  'TestAdmin@12345',
  'admin123',
  'admin',
]));

type StorageState = {
  origins?: Array<{
    localStorage?: Array<{ name: string; value: string }>;
  }>;
};

const storageStatePath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../fixtures/storage-state.json',
);

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
  // The desktop sidebar is intentionally collapsed on mobile. The main
  // application surface exists in every authenticated layout.
  await expect(page.getByRole('main')).toBeVisible({ timeout: 10000 });
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

  await page.evaluate(({ token, locale }) => {
    window.localStorage.setItem('token', token);
    window.localStorage.setItem('locale', locale);
  }, { token: accessToken, locale: E2E_LOCALE });
}

/**
 * Restore the auth session before a test page loads.
 *
 * Playwright deliberately omits sessionStorage from `storageState`. The app
 * keeps its Pinia auth payload in sessionStorage, so the global setup mirrors
 * the access token into localStorage and this helper restores the authoritative
 * session value through an init script for each fresh browser context.
 */
export async function restorePersistedAuthSession(page: Page): Promise<void> {
  const rawState = await readFile(storageStatePath, 'utf8');
  const storageState = JSON.parse(rawState) as StorageState;
  const localEntries = storageState.origins?.flatMap((origin) => origin.localStorage ?? []) ?? [];
  const accessToken = localEntries.find((entry) => entry.name === 'token')?.value;
  const locale = localEntries.find((entry) => entry.name === 'locale')?.value ?? E2E_LOCALE;

  if (!accessToken) {
    throw new Error(
      'E2E auth state is missing its access token. Ensure globalSetup completes before authenticated tests.',
    );
  }

  await page.addInitScript(({ token, language }: { token: string; language: string }) => {
    window.sessionStorage.setItem('auth', JSON.stringify({ token, refreshToken: null }));
    window.localStorage.setItem('token', token);
    window.localStorage.setItem('locale', language);
  }, { token: accessToken, language: locale });
}

export function getAdminCredentials() {
  return {
    username: E2E_ADMIN_USERNAME,
    password: E2E_ADMIN_PASSWORD,
  };
}
