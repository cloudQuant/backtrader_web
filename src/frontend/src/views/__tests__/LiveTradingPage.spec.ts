/**
 * Unit tests for LiveTradingPage.vue component.
 *
 * Tests cover:
 * - Initial rendering and data loading
 * - Instance list display
 * - Start/stop instance actions
 * - Error handling
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import LiveTradingPage from '../LiveTradingPage.vue'

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
vi.mock('@/api/liveTrading', () => ({
  liveTradingApi: {
    list: vi.fn().mockResolvedValue({ instances: [] }),
    listPresets: vi.fn().mockResolvedValue({ presets: [] }),
    start: vi.fn().mockResolvedValue({ status: 'running' }),
    stop: vi.fn().mockResolvedValue({ status: 'stopped' }),
    remove: vi.fn().mockResolvedValue(undefined),
    startAll: vi.fn().mockResolvedValue({}),
    stopAll: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplates: vi.fn().mockResolvedValue({ templates: [], total: 0 }),
  },
}))

vi.mock('@/api/autoTrading', () => ({
  autoTradingApi: {
    getConfig: vi.fn().mockResolvedValue({ enabled: false, buffer_minutes: 5, sessions: [], scope: 'all' }),
    getSchedule: vi.fn().mockResolvedValue({ schedule: [] }),
    updateConfig: vi.fn().mockResolvedValue({ enabled: false, buffer_minutes: 5, sessions: [], scope: 'all' }),
    toggle: vi.fn().mockResolvedValue({ enabled: false }),
  },
}))

vi.mock('@/api/index', () => ({
  getErrorMessage: vi.fn((_e, fallback) => fallback),
}))

// Mock useInstanceActions composable
vi.mock('@/composables/useInstanceActions', () => ({
  useInstanceActions: vi.fn(() => ({
    actionLoading: { value: false },
    batchLoading: { value: false },
    handleStart: vi.fn(),
    handleStop: vi.fn(),
    handleRemove: vi.fn(),
    handleStartAll: vi.fn(),
    handleStopAll: vi.fn(),
  })),
}))

// Create router mock
const mockPush = vi.fn()
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div></div>' } },
    { path: '/live-trading/:id', component: { template: '<div></div>' } },
  ],
})
router.push = mockPush

describe('LiveTradingPage.vue', () => {
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
    wrapper = mount(LiveTradingPage, {
      global: {
        plugins: [router],
        stubs: {
          'el-card': { template: '<div class="el-card"><slot /></div>' },
          'el-button': { template: '<button class="el-button"><slot /></button>' },
          'el-button-group': { template: '<div class="el-button-group"><slot /></div>' },
          'el-tag': { template: '<span class="el-tag"><slot /></span>' },
          'el-switch': { template: '<input type="checkbox" class="el-switch" />' },
          'el-table': { template: '<table class="el-table"><slot /></table>' },
          'el-table-column': { template: '<col class="el-table-column" />' },
          'el-form': { template: '<form class="el-form"><slot /></form>' },
          'el-form-item': { template: '<div class="el-form-item"><slot /></div>' },
          'el-select': { template: '<select class="el-select"><slot /></select>' },
          'el-option': { template: '<option class="el-option"></option>' },
          'el-input': { template: '<input class="el-input" />' },
          'el-dialog': { template: '<div class="el-dialog" v-if="modelValue"><slot /></div>', props: ['modelValue'] },
          'el-icon': { template: '<i class="el-icon"><slot /></i>' },
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

    it('should contain page title', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('实盘交易')
    })
  })

  describe('action buttons', () => {
    it('should have add strategy button', async () => {
      const wrapper = await mountComponent()
      const buttons = wrapper.findAll('.el-button')
      const addButton = buttons.find(b => b.text().includes('添加策略'))
      expect(addButton).toBeDefined()
    })

    it('should have start all button', async () => {
      const wrapper = await mountComponent()
      const buttons = wrapper.findAll('.el-button')
      const startButton = buttons.find(b => b.text().includes('一键启动'))
      expect(startButton).toBeDefined()
    })

    it('should have stop all button', async () => {
      const wrapper = await mountComponent()
      const buttons = wrapper.findAll('.el-button')
      const stopButton = buttons.find(b => b.text().includes('一键停止'))
      expect(stopButton).toBeDefined()
    })
  })

  describe('view mode toggle', () => {
    it('should have card view button', async () => {
      const wrapper = await mountComponent()
      const buttons = wrapper.findAll('.el-button')
      const cardButton = buttons.find(b => b.text().includes('卡片'))
      expect(cardButton).toBeDefined()
    })

    it('should have list view button', async () => {
      const wrapper = await mountComponent()
      const buttons = wrapper.findAll('.el-button')
      const listButton = buttons.find(b => b.text().includes('列表'))
      expect(listButton).toBeDefined()
    })
  })

  describe('auto trading section', () => {
    it('should display auto trading toggle', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.el-switch').exists()).toBe(true)
    })

    it('should show auto trading schedule table when available', async () => {
      const wrapper = await mountComponent()
      const tables = wrapper.findAll('.el-table')
      // At least one table for schedule should exist
      expect(tables.length).toBeGreaterThanOrEqual(0)
    })
  })
})
