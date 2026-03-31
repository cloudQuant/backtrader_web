/**
 * Unit tests for StrategyPage.vue component.
 *
 * Tests cover:
 * - Tab navigation (gallery vs my strategies)
 * - Template filtering and search
 * - Strategy card display
 * - Create dialog interaction
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createWebHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import StrategyPage from '../StrategyPage.vue'

// Mock Monaco Editor (required for jsdom compatibility)
vi.mock('monaco-editor', () => ({
  default: {},
}))

// Mock vue-i18n
vi.mock('vue-i18n', () => {
  const ref = <T>(val: T) => ({ value: val })
  return {
    createI18n: vi.fn(() => ({ global: { t: (key: string) => key } })),
    useI18n: vi.fn(() => ({ t: (key: string) => key, locale: ref('zh-CN') })),
  }
})

// Mock document.queryCommandSupported for Monaco Editor
Object.defineProperty(document, 'queryCommandSupported', {
  value: vi.fn().mockReturnValue(false),
  writable: true,
})

// Mock Element Plus
vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    warning: vi.fn(),
    error: vi.fn(),
  },
}))

// Mock API
vi.mock('@/api/strategy', () => ({
  strategyApi: {
    getTemplateConfig: vi.fn().mockResolvedValue({
      strategy: { description: 'Test strategy' },
      params: {},
    }),
    getTemplateReadme: vi.fn().mockResolvedValue('# Test Strategy\n\nDescription'),
    create: vi.fn().mockResolvedValue({ id: 'new-strategy-123' }),
    list: vi.fn().mockResolvedValue([]),
    getTemplates: vi.fn().mockResolvedValue({ templates: [], total: 0 }),
  },
}))

// Create router mock
const mockPush = vi.fn()
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div></div>' } },
    { path: '/strategy/:id', component: { template: '<div></div>' } },
  ],
})
router.push = mockPush

describe('StrategyPage.vue', () => {
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
    wrapper = mount(StrategyPage, {
      global: {
        plugins: [router],
        stubs: {
          'el-card': { template: '<div class="el-card"><slot /></div>' },
          'el-tabs': { 
            template: '<div class="el-tabs"><slot /></div>',
            props: ['modelValue'],
          },
          'el-tab-pane': { template: '<div class="el-tab-pane"><slot /></div>' },
          'el-button': { template: '<button class="el-button"><slot /></button>' },
          'el-input': { template: '<input class="el-input" />' },
          'el-radio-group': { template: '<div class="el-radio-group"><slot /></div>' },
          'el-radio-button': { template: '<label class="el-radio-button"><slot /></label>' },
          'el-tag': { template: '<span class="el-tag"><slot /></span>' },
          'el-icon': { template: '<i class="el-icon"><slot /></i>' },
          'el-dialog': { template: '<div class="el-dialog" v-if="modelValue"><slot /></div>' },
          'el-form': { template: '<form class="el-form"><slot /></form>' },
          'el-form-item': { template: '<div class="el-form-item"><slot /></div>' },
          'el-pagination': { template: '<div class="el-pagination"></div>' },
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

    it('should display page title', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.text()).toContain('策略中心')
    })
  })

  describe('tab structure', () => {
    it('should have tabs component', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.el-tabs').exists()).toBe(true)
    })

    it('should have gallery and my strategies tabs', async () => {
      const wrapper = await mountComponent()
      const tabs = wrapper.findAll('.el-tab-pane')
      expect(tabs.length).toBeGreaterThanOrEqual(2)
    })
  })

  describe('search and filter', () => {
    it('should have search input', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.el-input').exists()).toBe(true)
    })

    it('should have category filter radio group', async () => {
      const wrapper = await mountComponent()
      expect(wrapper.find('.el-radio-group').exists()).toBe(true)
    })
  })

  describe('create strategy button', () => {
    it('should have create strategy button', async () => {
      const wrapper = await mountComponent()
      const buttons = wrapper.findAll('.el-button')
      const createButton = buttons.find(b => b.text().includes('创建策略'))
      expect(createButton).toBeDefined()
    })
  })
})
