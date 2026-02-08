/**
 * 路由模块测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'

describe('Vue Router 配置', () => {
  it('应该能够创建路由实例', () => {
    const history = createMemoryHistory()
    const router = createRouter({
      history,
      routes: [
        { name: 'home', path: '/', component: { template: '<div>Home</div>' } },
        { name: 'login', path: '/login', component: { template: '<div>Login</div>' } },
      ],
    })

    expect(router).toBeDefined()
    // hasRoute 检查路由名称，不是路径
    expect(router.hasRoute('home')).toBe(true)
    expect(router.hasRoute('login')).toBe(true)
  })

  it('应该能够导航到不同路由', async () => {
    const history = createMemoryHistory()
    const router = createRouter({
      history,
      routes: [
        { path: '/', component: { template: '<div>Home</div>' } },
        { path: '/about', component: { template: '<div>About</div>' } },
      ],
    })

    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/')

    await router.push('/about')
    expect(router.currentRoute.value.path).toBe('/about')
  })

  it('应该处理404路由', async () => {
    const history = createMemoryHistory()
    const router = createRouter({
      history,
      routes: [
        { path: '/', component: { template: '<div>Home</div>' } },
        { path: '/:pathMatch(.*)*', component: { template: '<div>NotFound</div>' } },
      ],
    })

    await router.push('/non-existent')
    expect(router.currentRoute.value.path).toBe('/non-existent')
  })
})

describe('路由参数', () => {
  it('应该正确解析路由参数', async () => {
    const history = createMemoryHistory()
    const router = createRouter({
      history,
      routes: [
        { path: '/user/:id', component: { template: '<div>User</div>' }, props: true },
      ],
    })

    await router.push('/user/123')
    expect(router.currentRoute.value.params.id).toBe('123')
  })

  it('应该正确解析查询参数', async () => {
    const history = createMemoryHistory()
    const router = createRouter({
      history,
      routes: [
        { path: '/search', component: { template: '<div>Search</div>' } },
      ],
    })

    await router.push('/search?q=test&page=1')
    expect(router.currentRoute.value.query.q).toBe('test')
    expect(router.currentRoute.value.query.page).toBe('1')
  })
})
