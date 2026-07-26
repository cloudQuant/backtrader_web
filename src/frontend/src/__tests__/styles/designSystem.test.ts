import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const currentDir = path.dirname(fileURLToPath(import.meta.url))
const srcRoot = path.resolve(currentDir, '..', '..')
const designSystem = readFileSync(path.join(srcRoot, 'styles', 'design-system.scss'), 'utf8')
const styleCss = readFileSync(path.join(srcRoot, 'style.css'), 'utf8')

describe('design system contract', () => {
  it('defines theme palette sources for all supported themes', () => {
    for (const theme of ['aurora', 'obsidian', 'nebula', 'solaris', 'glacier', 'meridian', 'verdant']) {
      expect(designSystem).toContain(`--theme-${theme}-bg-color`)
      expect(designSystem).toContain(`--theme-${theme}-accent-color`)
      expect(designSystem).toContain(`--theme-${theme}-primary-on-color`)
      expect(designSystem).toContain(`--theme-${theme}-warning-color`)
      expect(designSystem).toContain(`--theme-${theme}-danger-color`)
    }
  })

  it('maps runtime semantic variables from raw tokens', () => {
    expect(styleCss).toContain('--primary-color: var(--color-primary-500);')
    expect(styleCss).toContain('--info-surface: color-mix(in srgb, var(--bg-color) 86%, var(--primary-color) 14%);')
    expect(styleCss).toContain('--success-surface: color-mix(in srgb, var(--bg-color) 86%, var(--success-color) 14%);')
    expect(styleCss).toContain('--warning-surface: color-mix(in srgb, var(--bg-color) 86%, var(--warning-color) 14%);')
    expect(styleCss).toContain('--el-color-warning: var(--warning-color);')
    expect(styleCss).toContain('--primary-on-color: #FFFFFF;')
    expect(styleCss).toContain('--el-text-color-secondary: var(--text-color-secondary);')
    expect(styleCss).toContain('--el-bg-color-overlay: var(--bg-color-overlay);')
    expect(styleCss).toContain('--code-bg-color: var(--color-code-bg);')
  })
})
