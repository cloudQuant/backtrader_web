/**
 * Frontend Audit Tracker — captures user interactions and reports them to the backend.
 *
 * Features:
 * - Captures clicks on interactive elements (button, a, input, select, [role])
 * - Captures page navigation events via Vue Router afterEach
 * - Batches events and flushes every 10s or when batch reaches 50
 * - Falls back to localStorage when API is unreachable (max 500 events, FIFO)
 * - Respects data-no-audit attribute on elements and ancestors
 */

import type { Router } from 'vue-router'
import { postAuditEvents } from '@/api/audit'
import type { OperationEvent } from '@/api/audit'

const FLUSH_INTERVAL_MS = 10_000
const MAX_BATCH_SIZE = 50
const MAX_LOCAL_STORAGE_EVENTS = 500
const STORAGE_KEY = 'audit_tracker_pending'

/** Interactive element selectors that should be tracked */
const INTERACTIVE_SELECTORS = ['button', 'a', 'input', 'select', '[role]']

/**
 * Check if an element or any ancestor has the data-no-audit attribute.
 */
function hasNoAuditAncestor(el: HTMLElement): boolean {
  let current: HTMLElement | null = el
  while (current) {
    if (current.hasAttribute('data-no-audit')) {
      return true
    }
    current = current.parentElement
  }
  return false
}

/**
 * Check if an element is an interactive element we should track.
 */
function isInteractiveElement(el: HTMLElement): boolean {
  const tag = el.tagName.toLowerCase()
  if (['button', 'a', 'input', 'select'].includes(tag)) {
    return true
  }
  if (el.getAttribute('role')) {
    return true
  }
  return false
}

/**
 * Generate an identifier for an element.
 * Priority: element id > nearest ancestor id + tagName + index
 */
function getElementIdentifier(el: HTMLElement): string {
  if (el.id) {
    return `#${el.id}`
  }

  // Walk up to find nearest ancestor with id
  let ancestor: HTMLElement | null = el.parentElement
  while (ancestor) {
    if (ancestor.id) {
      const tag = el.tagName.toLowerCase()
      const siblings = ancestor.querySelectorAll(tag)
      let index = 0
      for (let i = 0; i < siblings.length; i++) {
        if (siblings[i] === el) {
          index = i
          break
        }
      }
      return `#${ancestor.id} > ${tag}[${index}]`
    }
    ancestor = ancestor.parentElement
  }

  // Fallback: tag + text content snippet
  const tag = el.tagName.toLowerCase()
  const text = (el.textContent || '').trim().slice(0, 30)
  return text ? `${tag}:"${text}"` : tag
}

/**
 * Generate a simple session ID for tracking.
 */
function getOrCreateSessionId(): string {
  const key = 'audit_session_id'
  let sessionId = sessionStorage.getItem(key)
  if (!sessionId) {
    sessionId = `s_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
    sessionStorage.setItem(key, sessionId)
  }
  return sessionId
}

export class AuditTracker {
  private buffer: OperationEvent[] = []
  private timer: ReturnType<typeof setInterval> | null = null
  private clickHandler: ((e: MouseEvent) => void) | null = null
  private routerUnregister: (() => void) | null = null
  private getUserId: () => string | null
  private sessionId: string
  private active = false

  constructor(getUserId: () => string | null) {
    this.getUserId = getUserId
    this.sessionId = getOrCreateSessionId()
  }

  /**
   * Start tracking user interactions.
   */
  start(router?: Router): void {
    if (this.active) return
    this.active = true

    // Register click listener
    this.clickHandler = (e: MouseEvent) => this.handleClick(e)
    document.addEventListener('click', this.clickHandler, { capture: true, passive: true })

    // Register router navigation tracking
    if (router) {
      this.routerUnregister = router.afterEach((to, from) => {
        if (from.path !== to.path) {
          this.addEvent({
            event_type: 'navigation',
            event_target: null,
            page_path: to.path,
            event_data: { from_path: from.path, to_path: to.path },
            client_timestamp: new Date().toISOString(),
            session_id: this.sessionId,
          })
        }
      })
    }

    // Start flush timer
    this.timer = setInterval(() => {
      void this.flush()
    }, FLUSH_INTERVAL_MS)

    // Restore any pending events from localStorage
    this.restoreFromLocal()
  }

  /**
   * Stop tracking and flush remaining events.
   */
  stop(): void {
    if (!this.active) return
    this.active = false

    if (this.clickHandler) {
      document.removeEventListener('click', this.clickHandler, { capture: true } as EventListenerOptions)
      this.clickHandler = null
    }

    if (this.routerUnregister) {
      this.routerUnregister()
      this.routerUnregister = null
    }

    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
    }
  }

  /**
   * Flush buffered events to the API immediately.
   */
  async flush(): Promise<void> {
    if (this.buffer.length === 0) return

    const eventsToSend = this.buffer.splice(0, MAX_BATCH_SIZE)

    try {
      await postAuditEvents(eventsToSend)
      // On success, also try to send any stored events
      await this.sendStoredEvents()
    } catch {
      // API unreachable — store events in localStorage
      this.persistToLocal(eventsToSend)
    }
  }

  private handleClick(e: MouseEvent): void {
    const target = e.target as HTMLElement | null
    if (!target) return

    // Find the closest interactive element
    let el: HTMLElement | null = target
    if (!isInteractiveElement(target)) {
      el = target.closest(INTERACTIVE_SELECTORS.join(','))
    }
    if (!el) return

    // Check data-no-audit
    if (hasNoAuditAncestor(el)) return

    const userId = this.getUserId()
    if (!userId) return // Only track authenticated users

    this.addEvent({
      event_type: 'click',
      event_target: getElementIdentifier(el),
      page_path: window.location.pathname,
      event_data: {
        tag: el.tagName.toLowerCase(),
        text: (el.textContent || '').trim().slice(0, 50) || undefined,
      },
      client_timestamp: new Date().toISOString(),
      session_id: this.sessionId,
    })
  }

  private addEvent(event: OperationEvent): void {
    this.buffer.push(event)
    if (this.buffer.length >= MAX_BATCH_SIZE) {
      void this.flush()
    }
  }

  private persistToLocal(events: OperationEvent[]): void {
    try {
      const stored = this.getStoredEvents()
      const combined = [...stored, ...events]
      // FIFO: keep only the most recent MAX_LOCAL_STORAGE_EVENTS
      const trimmed = combined.slice(-MAX_LOCAL_STORAGE_EVENTS)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed))
    } catch {
      // localStorage might be full or unavailable
    }
  }

  private restoreFromLocal(): void {
    const stored = this.getStoredEvents()
    if (stored.length > 0) {
      this.buffer.push(...stored)
      localStorage.removeItem(STORAGE_KEY)
    }
  }

  private getStoredEvents(): OperationEvent[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        return JSON.parse(raw) as OperationEvent[]
      }
    } catch {
      // Ignore parse errors
    }
    return []
  }

  private async sendStoredEvents(): Promise<void> {
    const stored = this.getStoredEvents()
    if (stored.length === 0) return

    try {
      // Send in batches of MAX_BATCH_SIZE
      while (stored.length > 0) {
        const batch = stored.splice(0, MAX_BATCH_SIZE)
        await postAuditEvents(batch)
      }
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // Re-store remaining events
      if (stored.length > 0) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(stored))
      }
    }
  }
}
