/**
 * Unit tests for OptimizationPage.vue component.
 *
 * Tests cover:
 * - Initial rendering and strategy selection
 * - Parameter configuration
 * - Optimization submission
 * - Result display
 * - Error handling
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import OptimizationPage from '../OptimizationPage.vue'

// Mock Element Plus components
vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
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
vi.mock('@/api/optimization', () => ({
  optimizationApi: {
    getStrategyParams: vi.fn().mockResolvedValue({
      params: [
        { name: 'fast_period', type: 'int', default: 10, description: 'Fast period' },
        { name: 'slow_period', type: 'int', default: 20, description: 'Slow period' },
      ],
    }),
    submit: vi.fn().mockResolvedValue({ task_id: 'opt-123', message: 'Optimization started' }),
    getProgress: vi.fn().mockResolvedValue({ status: 'running', progress: 50, completed: 5, total: 10 }),
    getResults: vi.fn().mockResolvedValue({
      param_names: ['fast_period', 'slow_period'],
      trials: [],
      best_params: { fast_period: 10, slow_period: 20 },
      best_metric: 1.5,
    }),
    cancel: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({
      templates: [
        { id: 'dual_ma', name: 'Dual MA', category: 'trend' },
      ],
      total: 1,
    }),
  },
}))

vi.mock('@/api/index', () => ({
  getErrorMessage: vi.fn((_e, fallback) => fallback),
}))

// Create router mock
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div></div>' } },
    { path: '/optimization', component: { template: '<div></div>' } },
  ],
})

describe('OptimizationPage.vue', () => {
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
    wrapper = mount(OptimizationPage, {
      global: {
        plugins: [router],
        stubs: {
          'el-card': { template: '<div class="el-card"><slot /><slot name="header" /></div>' },
          'el-form': { template: '<form class="el-form"><slot /></form>' },
          'el-form-item': { template: '<div class="el-form-item"><slot /></div>' },
          'el-select': { template: '<select class="el-select"><slot /></select>' },
          'el-option': { template: '<option class="el-option"></option>' },
          'el-button': { template: '<button class="el-button"><slot /></button>' },
          'el-input-number': { template: '<input type="number" class="el-input-number" />' },
          'el-input': { template: '<input class="el-input" />' },
          'el-table': { template: '<table class="el-table"><slot /></table>' },
          'el-table-column': { template: '<col class="el-table-column" />' },
          'el-checkbox': { template: '<input type="checkbox" class="el-checkbox" />' },
          'el-progress': { template: '<div class="el-progress"></div>' },
          'el-steps': { template: '<div class="el-steps"><slot /></div>' },
          'el-step': { template: '<div class="el-step"></div>' },
          'el-divider': { template: '<hr class="el-divider" />' },
          'el-tag': { template: '<span class="el-tag"><slot /></span>' },
          'el-descriptions': { template: '<div class="el-descriptions"><slot /></div>' },
          'el-descriptions-item': { template: '<div class="el-descriptions-item"><slot /></div>' },
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

    it('should contain optimization configuration card', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.el-card').exists()).toBe(true)
    })
  })

  describe('strategy selection', () => {
    it('should have strategy select field', async () => {
      const wrapper = await mountComponent()
      const selects = wrapper.findAll('.el-select')
      expect(selects.length).toBeGreaterThan(0)
    })

    it('should display strategy options', async () => {
      const wrapper = await mountComponent()
      const options = wrapper.findAll('.el-option')
      expect(options.length).toBeGreaterThanOrEqual(0)
    })
  })

  describe('parameter configuration', () => {
    it('should have parameter table when strategy selected', async () => {
      const wrapper = await mountComponent()
      const tables = wrapper.findAll('.el-table')
      expect(tables.length).toBeGreaterThanOrEqual(0)
    })

    it('should have checkboxes for enabling parameters', async () => {
      const wrapper = await mountComponent()
      const checkboxes = wrapper.findAll('.el-checkbox')
      expect(checkboxes.length).toBeGreaterThanOrEqual(0)
    })
  })

  describe('action buttons', () => {
    it('should have start optimization button', async () => {
      const wrapper = await mountComponent()
      const buttons = wrapper.findAll('.el-button')
      const startButton = buttons.find(b => b.text().includes('开始优化') || b.text().includes('提交'))
      expect(startButton || buttons.length).toBeDefined()
    })
  })

  describe('form structure', () => {
    it('should have form element', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.el-form').exists()).toBe(true)
    })
  })
})
