import { describe, it, expect } from 'vitest'
import { renderMarkdown } from '@/utils/markdown-sanitizer'

describe('renderMarkdown', () => {
  describe('null/undefined handling', () => {
    it('returns empty string for null input', () => {
      expect(renderMarkdown(null)).toBe('')
    })

    it('returns empty string for undefined input', () => {
      expect(renderMarkdown(undefined)).toBe('')
    })

    it('returns empty string for empty string input', () => {
      expect(renderMarkdown('')).toBe('')
    })
  })

  describe('basic Markdown rendering', () => {
    it('renders paragraphs', () => {
      const result = renderMarkdown('Hello world')
      expect(result).toContain('<p>Hello world</p>')
    })

    it('renders headings', () => {
      const result = renderMarkdown('# Title')
      expect(result).toContain('<h1>Title</h1>')
    })

    it('renders lists', () => {
      const result = renderMarkdown('- item 1\n- item 2')
      expect(result).toContain('<ul>')
      expect(result).toContain('<li>item 1</li>')
      expect(result).toContain('<li>item 2</li>')
    })

    it('renders code blocks', () => {
      const result = renderMarkdown('```\nconst x = 1\n```')
      expect(result).toContain('<pre>')
      expect(result).toContain('<code>')
    })

    it('renders links', () => {
      const result = renderMarkdown('[link](https://example.com)')
      expect(result).toContain('<a href="https://example.com"')
      expect(result).toContain('link</a>')
    })

    it('renders images', () => {
      const result = renderMarkdown('![alt](https://example.com/img.png)')
      expect(result).toContain('<img src="https://example.com/img.png"')
      expect(result).toContain('alt="alt"')
    })
  })

  describe('XSS sanitization - script tag injection', () => {
    it('removes inline script tags', () => {
      const result = renderMarkdown('<script>alert("xss")</script>')
      expect(result).not.toContain('<script')
      expect(result).not.toContain('alert')
    })

    it('removes script tags with src attribute', () => {
      const result = renderMarkdown('<script src="https://evil.com/xss.js"></script>')
      expect(result).not.toContain('<script')
      expect(result).not.toContain('evil.com')
    })
  })

  describe('XSS sanitization - event handler injection', () => {
    it('removes onerror event handlers', () => {
      const result = renderMarkdown('<img src="x" onerror="alert(1)">')
      expect(result).not.toContain('onerror')
      expect(result).not.toContain('alert')
    })

    it('removes onload event handlers', () => {
      const result = renderMarkdown('<div onload="alert(1)">content</div>')
      expect(result).not.toContain('onload')
      expect(result).not.toContain('alert')
    })
  })

  describe('XSS sanitization - protocol XSS (javascript:/data:)', () => {
    it('removes javascript: protocol in links', () => {
      const result = renderMarkdown('<a href="javascript:alert(1)">click</a>')
      expect(result).not.toContain('javascript:')
    })

    it('removes data: protocol in image src', () => {
      const result = renderMarkdown('<img src="data:text/html,<script>alert(1)</script>">')
      expect(result).not.toContain('data:text/html')
      expect(result).not.toContain('<script')
    })
  })

  describe('XSS sanitization - iframe embedding', () => {
    it('removes iframe tags', () => {
      const result = renderMarkdown('<iframe src="https://evil.com"></iframe>')
      expect(result).not.toContain('<iframe')
      expect(result).not.toContain('evil.com')
    })

    it('removes iframe with srcdoc', () => {
      const result = renderMarkdown('<iframe srcdoc="<script>alert(1)</script>"></iframe>')
      expect(result).not.toContain('<iframe')
      expect(result).not.toContain('srcdoc')
    })
  })

  describe('XSS sanitization - other dangerous elements', () => {
    it('removes object tags', () => {
      const result = renderMarkdown('<object data="https://evil.com/flash.swf"></object>')
      expect(result).not.toContain('<object')
    })

    it('removes embed tags', () => {
      const result = renderMarkdown('<embed src="https://evil.com/flash.swf">')
      expect(result).not.toContain('<embed')
    })

    it('removes form tags', () => {
      const result = renderMarkdown('<form action="https://evil.com/steal"><p>content</p></form>')
      expect(result).not.toContain('<form')
      expect(result).not.toContain('evil.com')
      // Content inside form is preserved but form wrapper is stripped
      expect(result).toContain('content')
    })
  })

  describe('SanitizeOptions', () => {
    it('removes images when allowImages is false', () => {
      const result = renderMarkdown('![alt](https://example.com/img.png)', { allowImages: false })
      expect(result).not.toContain('<img')
    })

    it('removes links when allowLinks is false', () => {
      const result = renderMarkdown('[link](https://example.com)', { allowLinks: false })
      expect(result).not.toContain('<a')
      expect(result).not.toContain('href')
    })

    it('keeps images when allowImages is true', () => {
      const result = renderMarkdown('![alt](https://example.com/img.png)', { allowImages: true })
      expect(result).toContain('<img')
    })

    it('keeps links when allowLinks is true', () => {
      const result = renderMarkdown('[link](https://example.com)', { allowLinks: true })
      expect(result).toContain('<a')
    })
  })

  describe('Property-based tests (fast-check)', () => {
    // Property 4: XSS Sanitization Removes Dangerous Content
    // Feature: best-practices-improvement
    // Validates: Requirements 16.1, 16.2

    const dangerousPatterns = [
      '<script', '</script>', '<iframe', '</iframe>',
      '<object', '</object>', '<embed', '<form',
    ]

    // These patterns are only dangerous when they appear as actual HTML attributes,
    // not when they appear inside HTML-escaped text (e.g., &lt;img onerror=...)
    const dangerousAttrPatterns = [
      'javascript:',
    ]

    it('Property 4: never outputs dangerous elements from malicious input', async () => {
      const fc = await import('fast-check')
      fc.assert(
        fc.property(
          fc.oneof(
            fc.string({ minLength: 0, maxLength: 100 }).map(s => `<script>${s}</script>`),
            fc.string({ minLength: 0, maxLength: 100 }).map(s => `<iframe src="${s}"></iframe>`),
            fc.string({ minLength: 0, maxLength: 50 }).map(s => `<object data="${s}"></object>`),
            fc.string({ minLength: 0, maxLength: 50 }).map(s => `<embed src="${s}">`),
            fc.string({ minLength: 0, maxLength: 50 }).map(s => `<form action="${s}"><input></form>`),
          ),
          (maliciousHtml) => {
            const result = renderMarkdown(maliciousHtml)
            const lower = result.toLowerCase()
            for (const pattern of dangerousPatterns) {
              if (lower.includes(pattern.toLowerCase())) {
                throw new Error(`Output contains dangerous tag "${pattern}": ${result}`)
              }
            }
            for (const pattern of dangerousAttrPatterns) {
              if (lower.includes(pattern.toLowerCase())) {
                throw new Error(`Output contains dangerous pattern "${pattern}": ${result}`)
              }
            }
          }
        ),
        { numRuns: 100 }
      )
    })

    it('Property 4: event handlers and javascript: URIs are stripped from actual HTML attributes', async () => {
      const fc = await import('fast-check')
      fc.assert(
        fc.property(
          fc.oneof(
            fc.constant('<img onerror="alert(1)" src="x">'),
            fc.constant('<div onload="alert(1)">test</div>'),
            fc.constant('<a href="javascript:alert(1)">click</a>'),
            fc.constant('<img src="x" onclick="alert(1)">'),
            fc.constant('<body onload="alert(1)">'),
            fc.constant('<svg onload="alert(1)">'),
          ),
          (maliciousHtml) => {
            const result = renderMarkdown(maliciousHtml)
            // The output should not contain actual event handler attributes
            expect(result).not.toMatch(/\s(onerror|onload|onclick|onmouseover)=/i)
            expect(result).not.toContain('javascript:')
            expect(result).not.toContain('alert(')
          }
        ),
        { numRuns: 100 }
      )
    })

    it('Property 4: preserves safe Markdown content structure', async () => {
      const fc = await import('fast-check')
      fc.assert(
        fc.property(
          fc.oneof(
            fc.string({ minLength: 1, maxLength: 80 }).map(s => `# ${s.replace(/[#\n]/g, 'x')}`),
            fc.string({ minLength: 1, maxLength: 80 }).map(s => `**${s.replace(/[*\n]/g, 'x')}**`),
            fc.string({ minLength: 1, maxLength: 80 }).map(s => `- ${s.replace(/\n/g, ' ')}`),
            fc.string({ minLength: 1, maxLength: 80 }).map(s => `\`${s.replace(/[`\n]/g, 'x')}\``),
          ),
          (safeMarkdown) => {
            const result = renderMarkdown(safeMarkdown)
            if (result.length === 0) {
              throw new Error(`Safe Markdown produced empty output: "${safeMarkdown}"`)
            }
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})
