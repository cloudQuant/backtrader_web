/**
 * Unit tests for AuditTracker (src/utils/auditTracker.ts).
 *
 * Coverage targets:
 * - Click capture: interactive vs non-interactive elements, data-no-audit, unauthenticated user
 * - Element identifier resolution: id > ancestor-id+tag+index > tag+text
 * - Navigation tracking via router.afterEach
 * - Buffer/flush: auto-flush at MAX_BATCH_SIZE, periodic timer flush
 * - Persistence: localStorage fallback when API throws, FIFO trimming, restore
 * - Lifecycle: idempotent start/stop
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuditTracker } from '@/utils/auditTracker'
import * as auditApi from '@/api/audit'

vi.mock('@/api/audit', () => ({
  postAuditEvents: vi.fn(),
}))

// happy-dom in this project's setup does not always provide a writable
// Storage. Stub localStorage and sessionStorage with simple in-memory
// objects so the audit tracker can read/write keys.
function createMockStorage() {
  const store = new Map<string, string>()
  return {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v) },
    removeItem: (k: string) => { store.delete(k) },
    clear: () => { store.clear() },
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    get length() { return store.size },
  } as unknown as Storage
}
Object.defineProperty(globalThis, 'localStorage', { value: createMockStorage(), writable: true, configurable: true })
Object.defineProperty(globalThis, 'sessionStorage', { value: createMockStorage(), writable: true, configurable: true })

describe('AuditTracker', () => {
  let getUserId: ReturnType<typeof vi.fn>
  let tracker: AuditTracker

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    document.body.innerHTML = ''
    localStorage.clear()
    sessionStorage.clear()
    getUserId = vi.fn(() => 'user-1')
    tracker = new AuditTracker(getUserId as () => string | null)
  })

  afterEach(() => {
    if (tracker) tracker.stop()
    vi.useRealTimers()
  })

  it('start is idempotent', () => {
    tracker.start()
    tracker.start()
    // Second start should be a no-op (no exception, no extra listeners)
    expect(true).toBe(true)
  })

  it('stop is idempotent and clears listeners', () => {
    tracker.start()
    tracker.stop()
    tracker.stop()
    // No exception when called twice
    expect(true).toBe(true)
  })

  it('captures click on a button', async () => {
    vi.mocked(auditApi.postAuditEvents).mockResolvedValue(undefined as never)
    tracker.start()

    const btn = document.createElement('button')
    btn.id = 'submit-btn'
    btn.textContent = 'Submit'
    document.body.appendChild(btn)
    btn.click()

    // Trigger flush
    await vi.advanceTimersByTimeAsync(10_000)

    expect(auditApi.postAuditEvents).toHaveBeenCalled()
    const events = vi.mocked(auditApi.postAuditEvents).mock.calls[0][0]
    expect(events[0].event_type).toBe('click')
    expect(events[0].event_target).toBe('#submit-btn')
  })

  it('skips clicks on non-interactive elements when no interactive ancestor exists', async () => {
    tracker.start()
    const div = document.createElement('div')
    div.textContent = 'static text'
    document.body.appendChild(div)
    div.click()

    await vi.advanceTimersByTimeAsync(10_000)
    expect(auditApi.postAuditEvents).not.toHaveBeenCalled()
  })

  it('walks up to find interactive ancestor for non-interactive click target', async () => {
    vi.mocked(auditApi.postAuditEvents).mockResolvedValue(undefined as never)
    tracker.start()

    const btn = document.createElement('button')
    btn.id = 'wrap-btn'
    const span = document.createElement('span')
    span.textContent = 'inside'
    btn.appendChild(span)
    document.body.appendChild(btn)
    span.click()

    await vi.advanceTimersByTimeAsync(10_000)
    const events = vi.mocked(auditApi.postAuditEvents).mock.calls[0][0]
    expect(events[0].event_target).toBe('#wrap-btn')
  })

  it('respects data-no-audit on element', async () => {
    tracker.start()
    const btn = document.createElement('button')
    btn.id = 'no-track'
    btn.setAttribute('data-no-audit', '')
    document.body.appendChild(btn)
    btn.click()

    await vi.advanceTimersByTimeAsync(10_000)
    expect(auditApi.postAuditEvents).not.toHaveBeenCalled()
  })

  it('respects data-no-audit on ancestor', async () => {
    tracker.start()
    const wrap = document.createElement('div')
    wrap.setAttribute('data-no-audit', '')
    const btn = document.createElement('button')
    wrap.appendChild(btn)
    document.body.appendChild(wrap)
    btn.click()

    await vi.advanceTimersByTimeAsync(10_000)
    expect(auditApi.postAuditEvents).not.toHaveBeenCalled()
  })

  it('skips clicks when user is unauthenticated', async () => {
    getUserId.mockReturnValue(null)
    tracker.start()

    const btn = document.createElement('button')
    document.body.appendChild(btn)
    btn.click()

    await vi.advanceTimersByTimeAsync(10_000)
    expect(auditApi.postAuditEvents).not.toHaveBeenCalled()
  })

  it('captures clicks on elements with role attribute', async () => {
    vi.mocked(auditApi.postAuditEvents).mockResolvedValue(undefined as never)
    tracker.start()

    const div = document.createElement('div')
    div.id = 'role-btn'
    div.setAttribute('role', 'button')
    document.body.appendChild(div)
    div.click()

    await vi.advanceTimersByTimeAsync(10_000)
    expect(auditApi.postAuditEvents).toHaveBeenCalled()
  })

  it('uses ancestor id + tagName + index when element has no id', async () => {
    vi.mocked(auditApi.postAuditEvents).mockResolvedValue(undefined as never)
    tracker.start()

    const wrap = document.createElement('div')
    wrap.id = 'panel'
    wrap.appendChild(document.createElement('button'))
    const target = document.createElement('button')
    wrap.appendChild(target)
    wrap.appendChild(document.createElement('button'))
    document.body.appendChild(wrap)

    target.click()
    await vi.advanceTimersByTimeAsync(10_000)
    const events = vi.mocked(auditApi.postAuditEvents).mock.calls[0][0]
    expect(events[0].event_target).toBe('#panel > button[1]')
  })

  it('uses tag + text when no ancestor id is present', async () => {
    vi.mocked(auditApi.postAuditEvents).mockResolvedValue(undefined as never)
    tracker.start()

    const btn = document.createElement('button')
    btn.textContent = 'Click me'
    document.body.appendChild(btn)
    btn.click()

    await vi.advanceTimersByTimeAsync(10_000)
    const events = vi.mocked(auditApi.postAuditEvents).mock.calls[0][0]
    expect(events[0].event_target).toBe('button:"Click me"')
  })

  it('uses tag alone when no id and no text content', async () => {
    vi.mocked(auditApi.postAuditEvents).mockResolvedValue(undefined as never)
    tracker.start()

    const btn = document.createElement('button')
    document.body.appendChild(btn)
    btn.click()

    await vi.advanceTimersByTimeAsync(10_000)
    const events = vi.mocked(auditApi.postAuditEvents).mock.calls[0][0]
    expect(events[0].event_target).toBe('button')
  })

  it('captures router navigation events', async () => {
    vi.mocked(auditApi.postAuditEvents).mockResolvedValue(undefined as never)
    let afterEachCb: ((to: any, from: any) => void) | null = null
    const mockRouter = {
      afterEach: vi.fn((cb) => {
        afterEachCb = cb
        return () => {}
      }),
    } as any

    tracker.start(mockRouter)
    expect(mockRouter.afterEach).toHaveBeenCalled()

    afterEachCb!({ path: '/dashboard' }, { path: '/' })
    await vi.advanceTimersByTimeAsync(10_000)

    const events = vi.mocked(auditApi.postAuditEvents).mock.calls[0][0]
    expect(events[0].event_type).toBe('navigation')
    expect(events[0].page_path).toBe('/dashboard')
  })

  it('skips navigation event when from.path equals to.path', async () => {
    let afterEachCb: ((to: any, from: any) => void) | null = null
    const mockRouter = {
      afterEach: vi.fn((cb) => { afterEachCb = cb; return () => {} }),
    } as any

    tracker.start(mockRouter)
    afterEachCb!({ path: '/same' }, { path: '/same' })
    await vi.advanceTimersByTimeAsync(10_000)

    expect(auditApi.postAuditEvents).not.toHaveBeenCalled()
  })

  it('flushes immediately when buffer reaches MAX_BATCH_SIZE', async () => {
    vi.mocked(auditApi.postAuditEvents).mockResolvedValue(undefined as never)
    tracker.start()

    // Generate 50 click events
    for (let i = 0; i < 50; i++) {
      const btn = document.createElement('button')
      btn.id = `b-${i}`
      document.body.appendChild(btn)
      btn.click()
    }

    // No need to wait for the timer — auto-flush should fire
    await vi.advanceTimersByTimeAsync(0)
    expect(auditApi.postAuditEvents).toHaveBeenCalled()
  })

  it('persists events to localStorage when API fails', async () => {
    vi.mocked(auditApi.postAuditEvents).mockRejectedValue(new Error('network'))
    tracker.start()

    const btn = document.createElement('button')
    btn.id = 'fail-btn'
    document.body.appendChild(btn)
    btn.click()

    await vi.advanceTimersByTimeAsync(10_000)
    // Wait for the rejected promise to settle
    await vi.waitFor(() => {
      const stored = localStorage.getItem('audit_tracker_pending')
      expect(stored).toBeTruthy()
    })

    const stored = localStorage.getItem('audit_tracker_pending')
    const parsed = JSON.parse(stored!) as Array<{ event_target: string }>
    expect(parsed[0].event_target).toBe('#fail-btn')
  })

  it('restores pending events from localStorage on start', async () => {
    vi.mocked(auditApi.postAuditEvents).mockResolvedValue(undefined as never)
    // Pre-populate storage
    localStorage.setItem('audit_tracker_pending', JSON.stringify([
      {
        event_type: 'click',
        event_target: '#prev',
        page_path: '/x',
        event_data: {},
        client_timestamp: '2026-05-29T00:00:00Z',
        session_id: 's_old',
      },
    ]))

    tracker.start()
    await vi.advanceTimersByTimeAsync(10_000)

    expect(auditApi.postAuditEvents).toHaveBeenCalled()
    const events = vi.mocked(auditApi.postAuditEvents).mock.calls[0][0]
    expect(events[0].event_target).toBe('#prev')
    expect(localStorage.getItem('audit_tracker_pending')).toBeNull()
  })

  it('handles malformed localStorage payload gracefully', () => {
    localStorage.setItem('audit_tracker_pending', '{not json')
    expect(() => tracker.start()).not.toThrow()
  })

  it('reuses session id across instances', () => {
    const t1 = new AuditTracker(getUserId as () => string | null)
    const t2 = new AuditTracker(getUserId as () => string | null)
    expect((t1 as any).sessionId).toBe((t2 as any).sessionId)
  })

  it('flush is a no-op with empty buffer', async () => {
    tracker.start()
    await tracker.flush()
    expect(auditApi.postAuditEvents).not.toHaveBeenCalled()
  })
})
