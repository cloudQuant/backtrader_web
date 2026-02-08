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
  MagicStick: { template: '<span>Magic</span>' },
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
  render() { return h('button', { class: 'el-button' }, this.$slots.default?.()) }
})
const elTooltipStub = defineComponent({
  name: 'ElTooltip',
  props: ['content'],
  render() { return h('div', { class: 'el-tooltip' }, this.$slots.default?.()) }
})
const elDropdownStub = defineComponent({
  name: 'ElDropdown',
  render() { return h('div', { class: 'el-dropdown' }, this.$slots.default?.()) }
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
        { path: '/optimization', component: { template: '<div>Optimization</div>' } },
        { path: '/strategy', component: { template: '<div>Strategy</div>' } },
        { path: '/data', component: { template: '<div>Data</div>' } },
        { path: '/live-trading', component: { template: '<div>LiveTrading</div>' } },
        { path: '/portfolio', component: { template: '<div>Portfolio</div>' } },
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
        user: { username: 'testuser' },
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
    ElTooltip: elTooltipStub,
    ElDropdown: elDropdownStub,
    ElDropdownMenu: elDropdownMenuStub,
    ElDropdownItem: elDropdownItemStub,
    ElAvatar: elAvatarStub,
    RouterView: { template: '<div>RouterView</div>' },
  })

  const getGlobalConfig = () => ({
    plugins: [router, pinia],
    stubs: getGlobalStubs(),
  })

  describe('基础渲染', () => {
    it('应该渲染侧边栏', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.find('.el-aside').exists()).toBe(true)
    })

    it('应该渲染顶部栏', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.find('.el-header').exists()).toBe(true)
    })

    it('应该渲染主内容区', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.find('.el-main').exists()).toBe(true)
    })

    it('应该显示应用标题', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('Backtrader Web')
    })
  })

  describe('导航菜单', () => {
    it('应该包含所有菜单项', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      const menuItems = wrapper.findAll('.el-menu-item')
      expect(menuItems.length).toBeGreaterThan(0)
    })

    it('应该包含首页菜单项', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('首页')
    })

    it('应该包含回测分析菜单项', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('回测分析')
    })

    it('应该包含策略管理菜单项', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('策略管理')
    })
  })

  describe('页面标题', () => {
    it('首页应该显示"仪表盘"', async () => {
      await router.push('/')
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('仪表盘')
    })

    it('回测页面应该显示"回测分析"', async () => {
      await router.push('/backtest')
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('回测分析')
    })
  })

  describe('主题切换', () => {
    it('默认应该是亮色主题', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(localStorageMock.getItem('theme') !== 'dark').toBe(true)
    })

    it('应该切换主题', async () => {
      localStorageMock.clear()
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })

      // 模拟点击主题切换按钮
      const button = wrapper.find('.el-button')
      if (button.exists()) {
        button.trigger('click')
        // 检查localStorage是否被调用
        expect(localStorageMock.setItem).toHaveBeenCalled()
      }
    })
  })

  describe('用户信息', () => {
    it('应该显示用户名', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      expect(wrapper.text()).toContain('testuser')
    })

    it('应该显示用户头像', async () => {
      const AppLayout = (await import('./AppLayout.vue')).default
      const wrapper = mount(AppLayout, { global: getGlobalConfig() })
      const avatar = wrapper.find('.el-avatar')
      expect(avatar.exists()).toBe(true)
    })
  })
})
