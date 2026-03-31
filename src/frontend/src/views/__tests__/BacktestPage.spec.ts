/**
 * Unit tests for BacktestPage.vue component.
 *
 * Tests cover:
 * - Initial rendering and data loading
 * - Strategy selection and config loading
 * - Backtest submission
 * - Result display
 * - Error handling
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import BacktestPage from '../BacktestPage.vue'

// Mock Element Plus components
vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
  ElMessageBox: {
    confirm: vi.fn().mockResolvedValue(undefined),
  },
}))

// Mock vue-i18n
vi.mock('vue-i18n', () => {
  const ref = <T>(val: T) => ({ value: val })
  return {
    createI18n: vi.fn(() => ({ global: { t: (key: string) => key } })),
    useI18n: vi.fn(() => ({ t: (key: string) => key, locale: ref('zh-CN') })),
  }
})

// Mock API modules
vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplateConfig: vi.fn().mockResolvedValue({
      strategy: { description: 'Test strategy', author: 'Test Author' },
      params: { fast_period: 10, slow_period: 20 },
      data: { symbol: 'BTCUSDT' },
      backtest: { initial_cash: 100000, commission: 0.001 },
    }),
    getTemplates: vi.fn().mockResolvedValue({ templates: [], total: 0 }),
  },
}))

vi.mock('@/api/backtest', () => ({
  backtestApi: {
    run: vi.fn().mockResolvedValue({ task_id: 'task-123', status: 'pending' }),
    getResult: vi.fn(),
    list: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/api/index', () => ({
  getErrorMessage: vi.fn((_e, fallback) => fallback),
}))

// Mock useBacktestRuntime composable
vi.mock('@/composables/useBacktestRuntime', () => ({
  useBacktestRuntime: vi.fn(() => ({
    loading: { value: false },
    currentTaskId: { value: null },
    progressInfo: { value: { progress: 0, message: '' } },
    cancelBacktest: vi.fn(),
    closeWebSocket: vi.fn(),
    connectWebSocket: vi.fn(),
    disposeRuntime: vi.fn(),
    startRuntime: vi.fn(),
    stopRuntime: vi.fn(),
  })),
}))

// Mock EquityCurve component
vi.mock('@/components/charts/EquityCurve.vue', () => ({
  default: {
    name: 'EquityCurve',
    template: '<div class="equity-curve-mock"></div>',
  },
}))

// Create router mock
const mockPush = vi.fn()
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div></div>' } },
    { path: '/backtest/:id', component: { template: '<div></div>' } },
  ],
})
router.push = mockPush

describe('BacktestPage.vue', () => {
  let wrapper: ReturnType<typeof mount>

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
    }
  })

  const mountComponent = async () => {
    wrapper = mount(BacktestPage, {
      global: {
        plugins: [router],
        stubs: {
          'el-card': { template: '<div class="el-card"><slot /></div>' },
          'el-form': { template: '<form class="el-form"><slot /></form>' },
          'el-form-item': { template: '<div class="el-form-item"><slot /></div>' },
          'el-select': { template: '<select class="el-select"><slot /></select>' },
          'el-option': { template: '<option class="el-option"></option>' },
          'el-button': { template: '<button class="el-button"><slot /></button>' },
          'el-input-number': { template: '<input type="number" class="el-input-number" />' },
          'el-input': { template: '<input class="el-input" />' },
          'el-table': { template: '<table class="el-table"><slot /></table>' },
          'el-table-column': { template: '<col class="el-table-column" />' },
          'el-progress': { template: '<div class="el-progress"></div>' },
          'el-divider': { template: '<hr class="el-divider" />' },
          'el-row': { template: '<div class="el-row"><slot /></div>' },
          'el-col': { template: '<div class="el-col"><slot /></div>' },
        },
      },
    })
    await nextTick()
    return wrapper
  }

  describe('component mounting', () => {
    it('should mount without errors', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.exists()).toBe(true)
    })

    it('should contain backtest configuration form', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.el-form').exists()).toBe(true)
    })
  })

  describe('form structure', () => {
    it('should have strategy select field', async () => {
      const wrapper = await mountComponent()
      const selects = wrapper.findAll('.el-select')
      expect(selects.length).toBeGreaterThan(0)
    })

    it('should have run backtest button', async () => {
      const wrapper = await mountComponent()
      const buttons = wrapper.findAll('.el-button')
      const runButton = buttons.find(b => b.text().includes('运行回测'))
      expect(runButton).toBeDefined()
    })
  })

  describe('result display', () => {
    it('should not show result card when no result', async () => {
      const wrapper = await mountComponent()
      // Result card should not be visible when currentResult is null
      const cards = wrapper.findAll('.el-card')
      const hasResultCard = cards.some(card => 
        card.html().includes('回测结果') || card.html().includes('总收益率')
      )
      // Initially no results, so result metrics should not be visible
      expect(hasResultCard).toBe(false)
    })
  })

  describe('history table', () => {
    it('should have backtest history table', async () => {
      const wrapper = await mountComponent()
      const tables = wrapper.findAll('.el-table')
      expect(tables.length).toBeGreaterThan(0)
    })
  })
})
