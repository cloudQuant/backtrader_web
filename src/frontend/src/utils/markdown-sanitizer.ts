import DOMPurify from 'dompurify'
import { marked } from 'marked'

/**
 * Allowed HTML tags for Markdown rendering.
 * Restricted to safe formatting tags only — no script, iframe, object, embed, or form.
 */
const ALLOWED_TAGS = [
  'p', 'br', 'hr',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'pre', 'code', 'blockquote',
  'strong', 'em', 'del', 's', 'mark', 'sub', 'sup',
  'a', 'img',
  'span', 'div',
]

/**
 * Allowed HTML attributes for sanitized output.
 * Only safe attributes needed for Markdown rendering are permitted.
 */
const ALLOWED_ATTR = ['href', 'src', 'alt', 'class', 'id', 'title', 'target', 'rel']

const DANGEROUS_REMOTE_TAG_RE =
  /<(script|iframe|object|embed)\b[\s\S]*?<\/\1>|<(script|iframe|object|embed)\b[^>]*\/?>/gi
const EVENT_HANDLER_ATTR_RE = /\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi
const UNSAFE_URI_ATTR_RE =
  /\s+(href|src)\s*=\s*(?:"\s*(?:javascript|data):[^"]*"|'\s*(?:javascript|data):[^']*'|\s*(?:javascript|data):[^\s>]+)/gi
const SCRIPT_PROTOCOL_RE = /javascript\s*:/gi

export interface SanitizeOptions {
  /** Allow <img> tags in output. Defaults to true. */
  allowImages?: boolean
  /** Allow <a> tags in output. Defaults to true. */
  allowLinks?: boolean
}

/**
 * Render raw Markdown to sanitized HTML.
 *
 * Converts Markdown to HTML using `marked`, then sanitizes the output
 * with DOMPurify using an explicit whitelist of allowed tags and attributes.
 *
 * @param raw - Raw Markdown string. Returns empty string for null/undefined.
 * @param options - Optional configuration to restrict images or links.
 * @returns Sanitized HTML string safe for insertion via v-html.
 */
export function renderMarkdown(raw: string | null | undefined, options?: SanitizeOptions): string {
  if (raw == null || raw === '') {
    return ''
  }

  // Convert Markdown to HTML
  const html = marked.parse(raw, { async: false }) as string

  // Build tag whitelist based on options
  const tags = [...ALLOWED_TAGS]
  if (options?.allowImages === false) {
    const imgIndex = tags.indexOf('img')
    if (imgIndex !== -1) {
      tags.splice(imgIndex, 1)
    }
  }
  if (options?.allowLinks === false) {
    const aIndex = tags.indexOf('a')
    if (aIndex !== -1) {
      tags.splice(aIndex, 1)
    }
  }

  // Build attribute whitelist based on options
  const attrs = [...ALLOWED_ATTR]
  if (options?.allowImages === false) {
    const srcIndex = attrs.indexOf('src')
    if (srcIndex !== -1) {
      attrs.splice(srcIndex, 1)
    }
    const altIndex = attrs.indexOf('alt')
    if (altIndex !== -1) {
      attrs.splice(altIndex, 1)
    }
  }
  if (options?.allowLinks === false) {
    const hrefIndex = attrs.indexOf('href')
    if (hrefIndex !== -1) {
      attrs.splice(hrefIndex, 1)
    }
    const targetIndex = attrs.indexOf('target')
    if (targetIndex !== -1) {
      attrs.splice(targetIndex, 1)
    }
    const relIndex = attrs.indexOf('rel')
    if (relIndex !== -1) {
      attrs.splice(relIndex, 1)
    }
  }

  const precleaned = html
    .replace(DANGEROUS_REMOTE_TAG_RE, '')
    .replace(UNSAFE_URI_ATTR_RE, '')
    .replace(EVENT_HANDLER_ATTR_RE, '')
    .replace(SCRIPT_PROTOCOL_RE, '')

  // Sanitize HTML with DOMPurify
  const clean = DOMPurify.sanitize(precleaned, {
    ALLOWED_TAGS: tags,
    ALLOWED_ATTR: attrs,
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'onfocus', 'onblur'],
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|[^a-z]|[a-z+.-]+(?:[^a-z+.-:]|$))/i,
  })

  return clean
    .replace(UNSAFE_URI_ATTR_RE, '')
    .replace(EVENT_HANDLER_ATTR_RE, '')
    .replace(SCRIPT_PROTOCOL_RE, '')
}
