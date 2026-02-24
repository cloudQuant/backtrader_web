import { test, expect } from '@playwright/test';
import { join } from 'path';
import { promises as fs } from 'fs';

/**
 * 冒烟测试 - 验证基本环境配置
 *
 * 这些测试不依赖应用逻辑，只验证：
 * 1. Playwright 是否正确安装
 * 2. 测试配置是否正确
 * 3. 基本的选择器是否工作
 */
test.describe('冒烟测试', () => {

  test('Playwright 基本功能验证', async ({ page }) => {
    // 访问一个简单的页面来验证浏览器功能
    await page.goto('data:text/html,<html><head><title>Test Page</title></head><body><h1>Hello E2E</h1></body></html>');

    // 验证页面标题
    await expect(page).toHaveTitle('Test Page');

    // 验证基本操作
    await expect(page.locator('h1')).toHaveText('Hello E2E');
  });

  test('测试报告目录创建', async ({ page }) => {
    // 验证报告目录会被创建
    const resultsDir = join(process.cwd(), 'e2e-results');

    // 确保目录存在
    await fs.mkdir(resultsDir, { recursive: true });

    // 验证目录可写
    const testFile = join(resultsDir, 'test-write.txt');
    await fs.writeFile(testFile, 'E2E 测试目录可写');

    const content = await fs.readFile(testFile, 'utf-8');
    expect(content).toBe('E2E 测试目录可写');

    // 清理
    await fs.unlink(testFile);
  });
});
