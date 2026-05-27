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
      expect(designSystem).toContain(`--theme-${theme}-danger-color`)
    }
  })

  it('maps runtime semantic variables from raw tokens', () => {
    expect(styleCss).toContain('--primary-color: var(--color-primary-500);')
    expect(styleCss).toContain('--info-surface: var(--color-primary-50);')
    expect(styleCss).toContain('--success-surface: var(--color-success-50);')
    expect(styleCss).toContain('--code-bg-color: var(--color-code-bg);')
  })
})
