import { mkdir } from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { chromium, firefox, webkit, FullConfig } from '@playwright/test';
import { persistAuthTokenForStorageState } from './support/auth';

/**
 * 全局测试设置
 *
 * 在所有测试运行前执行，用于创建已登录的 storage state
 */
async function globalSetup(config: FullConfig) {
  const currentDir = path.dirname(fileURLToPath(import.meta.url));
  const baseURL = String(config.projects[0]?.use?.baseURL ?? 'http://127.0.0.1:3000');
  const browserName = process.env.E2E_SETUP_BROWSER
    ?? String(config.projects[0]?.use?.browserName ?? 'chromium');
  const username = process.env.E2E_ADMIN_USERNAME ?? 'admin';
  const preferredPassword = process.env.E2E_ADMIN_PASSWORD ?? 'Admin12345678';
  const passwordCandidates = Array.from(new Set([
    preferredPassword,
    'Admin12345678',
    'TestAdmin@12345',
    'admin123',
    'admin',
  ]));
  const storageStatePath = path.resolve(currentDir, 'fixtures/storage-state.json');
  const browserType =
    browserName === 'firefox'
      ? firefox
      : browserName === 'webkit'
        ? webkit
        : chromium;

  await mkdir(path.dirname(storageStatePath), { recursive: true });

  const browser = await browserType.launch();
  const page = await browser.newPage({ baseURL });

  try {
    let loggedIn = false;
    for (const password of passwordCandidates) {
      await page.goto('/login');
      await page.getByTestId('login-username').fill(username);
      await page.getByTestId('login-password').fill(password);
      await page.getByTestId('login-submit').click();
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
        `E2E global setup could not log in as ${username}. Set E2E_ADMIN_PASSWORD or seed the default admin account.`,
      );
    }
    await persistAuthTokenForStorageState(page);
    await page.context().storageState({ path: storageStatePath });
  } finally {
    await browser.close();
  }
}

export default globalSetup;
