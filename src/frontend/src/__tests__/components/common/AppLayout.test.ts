/**
 * AppLayout 组件测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'

// Mock localStorage before importing anything else
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value }),
    removeItem: vi.fn((key: string) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
  }
})()
Object.defineProperty(global, 'localStorage', { value: localStorageMock })

// Element Plus 图标 mock
vi.mock('@element-plus/icons-vue', () => ({
  Aim: { template: '<span>Aim</span>' },
  ChatDotRound: { template: '<span>Chat</span>' },
  Collection: { template: '<span>Collection</span>' },
  HomeFilled: { template: '<span>Home</span>' },
  DataLine: { template: '<span>Data</span>' },
  Document: { template: '<span>Doc</span>' },
  Grid: { template: '<span>Grid</span>' },
  Setting: { template: '<span>Setting</span>' },
  ArrowDown: { template: '<span>Arrow</span>' },
  TrendCharts: { template: '<span>Trend</span>' },
  Sunny: { template: '<span>Sunny</span>' },
  Moon: { template: '<span>Moon</span>' },
  VideoPlay: { template: '<span>Video</span>' },
  Monitor: { template: '<span>Monitor</span>' },
  Stopwatch: { template: '<span>Stopwatch</span>' },
  Refresh: { template: '<span>Refresh</span>' },
  Plus: { template: '<span>Plus</span>' },
  Delete: { template: '<span>Delete</span>' },
  Edit: { template: '<span>Edit</span>' },
  Search: { template: '<span>Search</span>' },
  Fold: { template: '<span>Fold</span>' },
  Close: { template: '<span>Close</span>' },
  Check: { template: '<span>Check</span>' },
  Promotion: { template: '<span>Promotion</span>' },
}))

// Mock Element Plus ElMessage
vi.mock('element-plus', () => ({
  ElMessage: {
    error: vi.fn(),
  },
}))

// Element Plus 组件 stub
const elContainerStub = defineComponent({
  name: 'ElContainer',
  render() { return h('div', { class: 'el-container' }, this.$slots.default?.()) }
})
const elAsideStub = defineComponent({
  name: 'ElAside',
  render() { return h('div', { class: 'el-aside' }, this.$slots.default?.()) }
})
const elHeaderStub = defineComponent({
  name: 'ElHeader',
  render() { return h('div', { class: 'el-header' }, this.$slots.default?.()) }
})
const elMainStub = defineComponent({
  name: 'ElMain',
  render() { return h('div', { class: 'el-main' }, this.$slots.default?.()) }
})
const elMenuStub = defineComponent({
  name: 'ElMenu',
  props: ['defaultActive', 'router'],
  render() { return h('div', { class: 'el-menu' }, this.$slots.default?.()) }
})
const elMenuItemStub = defineComponent({
  name: 'ElMenuItem',
  props: ['index'],
  render() { return h('div', { class: 'el-menu-item' }, this.$slots.default?.()) }
})
const elIconStub = defineComponent({
  name: 'ElIcon',
  render() { return h('span', { class: 'el-icon' }, this.$slots.default?.()) }
})
const elButtonStub = defineComponent({
  name: 'ElButton',
  props: ['circle'],
  emits: ['click'],
  render() { return h('button', { class: 'el-button', onClick: () => this.$emit('click') }, this.$slots.default?.()) }
})
const elTooltipStub = defineComponent({
  name: 'ElTooltip',
  props: ['content'],
  render() { return h('div', { class: 'el-tooltip' }, this.$slots.default?.()) }
})
const elDropdownStub = defineComponent({
  name: 'ElDropdown',
  emits: ['command'],
  render() { return h('div', { class: 'el-dropdown', onClick: () => this.$emit('command', 'obsidian') }, this.$slots.default?.()) }
})
const elDropdownMenuStub = defineComponent({
  name: 'ElDropdownMenu',
  render() { return h('div', { class: 'el-dropdown-menu' }, this.$slots.default?.()) }
})
const elDropdownItemStub = defineComponent({
  name: 'ElDropdownItem',
  props: ['divided'],
  render() { return h('div', { class: 'el-dropdown-item' }, this.$slots.default?.()) }
})
const elAvatarStub = defineComponent({
  name: 'ElAvatar',
  props: ['size'],
  render() { return h('div', { class: 'el-avatar' }, this.$slots.default?.()) }
})
const elDrawerStub = defineComponent({
  name: 'ElDrawer',
  props: ['modelValue', 'direction', 'size', 'showClose', 'zIndex'],
  render() { return h('div', { class: 'el-drawer' }, [this.$slots.header?.(), this.$slots.default?.()]) }
})

describe('AppLayout', () => {
  let router: any
  let pinia: any

  beforeEach(async () => {
    // 清除 localStorage mock
    localStorageMock.clear()
    vi.clearAllMocks()

    // 创建路由
    const history = createMemoryHistory()
    history.push('/')  // 设置初始路由
    router = createRouter({
      history,
      routes: [
        { path: '/', component: { template: '<div>Home</div>' } },
        { path: '/backtest', component: { template: '<div>Backtest</div>' } },
        { path: '/strategy', component: { template: '<div>Strategy</div>' } },
        { path: '/investment/strategies', component: { template: '<div>InvestmentStrategy</div>' } },
        { path: '/investment/stock-analysis', component: { template: '<div>StockAnalysis</div>' } },
        { path: '/research/strategies', component: { template: '<div>Strategy</div>' } },
        { path: '/data', component: { template: '<div>Data</div>' } },
        { path: '/trading', component: { template: '<div>Trading</div>' } },
        { path: '/portfolio', component: { template: '<div>Portfolio</div>' } },
        { path: '/brokers', component: { template: '<div>Brokers</div>' } },
        { path: '/ai-chat', component: { template: '<div>AIChat</div>' } },
        { path: '/ai/knowledge-base', component: { template: '<div>KnowledgeBase</div>' } },
        { path: '/config/ai/observability', component: { template: '<div>AIObservability</div>' } },
        { path: '/config/ai/prompt-governance', component: { template: '<div>PromptTemplates</div>' } },
        { path: '/admin/ai-observability', component: { template: '<div>AIObservability</div>' } },
        { path: '/admin/prompt-templates', component: { template: '<div>PromptTemplates</div>' } },
        { path: '/knowledge-base', component: { template: '<div>KnowledgeBase</div>' } },
        { path: '/settings', component: { template: '<div>Settings</div>' } },
        { path: '/login', component: { template: '<div>Login</div>' } },
      ],
    })
    await router.push('/')  // 确保路由被正确初始化
    await router.isReady()

    // 创建 Pinia
    pinia = createPinia()
    setActivePinia(pinia)

    // Mock auth store
    vi.doMock('@/stores/auth', () => ({
      useAuthStore: () => ({
        user: { username: 'testuser', is_admin: true },
        logout: vi.fn(),
      }),
    }))
  })

  // 全局 stubs 配置
  const getGlobalStubs = () => ({
    ElContainer: elContainerStub,
    ElAside: elAsideStub,
    ElHeader: elHeaderStub,
    ElMain: elMainStub,
    ElMenu: elMenuStub,
    ElMenuItem: elMenuItemStub,
    ElIcon: elIconStub,
    ElButton: elButtonStub,
    'el-button': elButtonStub,
    ElTooltip: elTooltipStub,
    ElDropdown: elDropdownStub,
    'el-dropdown': elDropdownStub,
    ElDropdownMenu: elDropdownMenuStub,
    ElDropdownItem: elDropdownItemStub,
    ElAvatar: elAvatarStub,
    ElDrawer: elDrawerStub,
    'el-drawer': elDrawerStub,
    RouterView: { template: '<div>RouterView</div>' },
  })

  const getGlobalConfig = () => ({
    plugins: [router, pinia],
    stubs: getGlobalStubs(),
  })

  describe('基础渲染', () => {
    it('应该渲染侧边栏', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.find('.el-aside').exists()).toBe(true)
    })

    it('应该渲染顶部栏', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.find('.el-header').exists()).toBe(true)
    })

    it('应该渲染主内容区', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.find('.el-main').exists()).toBe(true)
    })

    it('应该显示应用标题', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('AI for Investor')
    })
  })

  describe('导航菜单', () => {
    it('应该包含主导航菜单项且不展示平台治理', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('首页')
      expect(wrapper.text()).toContain('市场数据')
      expect(wrapper.text()).toContain('策略研究')
      expect(wrapper.text()).toContain('交易运营')
      expect(wrapper.text()).toContain('组合风控')
      expect(wrapper.text()).toContain('知识库')
      expect(wrapper.text()).not.toContain('AI知识')
      expect(wrapper.text()).not.toContain('平台治理')
    })

    it('应该包含首页菜单项', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('首页')
    })

    it('应该包含策略研究菜单项', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('策略研究')
    })

    it('应该包含策略管理菜单项', async () => {
      await router.push('/research/strategies')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('策略管理')
    })

    it('投资研究中的策略入口应该显示AI投研', async () => {
      await router.push('/investment/strategies')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('投资研究')
      expect(wrapper.text()).toContain('AI投研')
    })

    it('应该包含知识库与知识问答菜单项', async () => {
      await router.push('/ai-chat')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('知识库')
      expect(wrapper.text()).toContain('知识问答')
      expect(wrapper.text()).not.toContain('AI成本')
      expect(wrapper.text()).not.toContain('Prompt治理')
    })

    it('管理员应该在配置中心看到AI成本菜单项', async () => {
      await router.push('/config/ai/observability')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('配置中心')
      expect(wrapper.text()).toContain('AI成本')
    })

    it('管理员应该在配置中心看到Prompt治理菜单项', async () => {
      await router.push('/config/ai/prompt-governance')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('配置中心')
      expect(wrapper.text()).toContain('Prompt治理')
    })

    it('应该包含知识库菜单项', async () => {
      await router.push('/ai/knowledge-base')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('知识库')
    })
  })

  describe('页面标题', () => {
    it('首页应该显示"仪表盘"', async () => {
      await router.push('/')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('仪表盘')
    })

    it('回测页面应该显示"策略研究"', async () => {
      await router.push('/backtest')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('策略研究')
    })

    it('AI问答页面应该显示"知识问答"', async () => {
      await router.push('/ai-chat')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('知识问答')
    })

    it('AI成本页面应该显示"AI成本"', async () => {
      await router.push('/config/ai/observability')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('AI成本')
    })

    it('Prompt治理页面应该显示"Prompt治理"', async () => {
      await router.push('/config/ai/prompt-governance')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('Prompt治理')
    })

    it('知识库页面应该显示"知识库"', async () => {
      await router.push('/knowledge-base')
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('知识库')
    })
  })

  describe('主题切换', () => {
    it('默认应该是亮色主题', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      mount(AppLayout, { global: getGlobalConfig() })
      expect(localStorageMock.getItem('theme') !== 'dark').toBe(true)
    })

    it('应该切换主题', async () => {
      localStorageMock.clear()
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })

      // 模拟下拉菜单选择主题
      for (const dropdown of wrapper.findAll('.el-dropdown')) {
        await dropdown.trigger('click')
      }
      // 检查主题是否实际应用
      expect(document.documentElement.dataset.theme).toBe('obsidian')
    })
  })

  describe('用户信息', () => {
    it('应该显示用户名', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('testuser')
    })

    it('应该显示用户头像', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      const avatar = wrapper.find('.el-avatar')
      expect(avatar.exists()).toBe(true)
    })
  })

  describe('语言切换控件', () => {
    it('应该在 header 渲染语言切换控件', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.find('.el-header button.language-switcher').exists()).toBe(true)
    })

    it('header 右侧顺序应为 主题切换 → 语言切换 → 用户菜单', async () => {
      const AppLayout = (await import('@/components/common/AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      const html = wrapper.find('.el-header').html()
      const themeIdx = html.indexOf('theme-icon')
      const langIdx = html.indexOf('language-switcher')
      const userIdx = html.indexOf('el-avatar')
      expect(themeIdx).toBeGreaterThan(-1)
      expect(langIdx).toBeGreaterThan(themeIdx)
      expect(userIdx).toBeGreaterThan(langIdx)
    })
  })
})
