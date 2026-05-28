/**
 * Shared mounting helper for view tests.
 * Provides isolated Pinia and Router instances for each mount.
 */
import type { Component } from 'vue'
import { mount, type MountingOptions, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { vi } from 'vitest'

import { elStubs } from './stubs'

// Mock element-plus locale
vi.mock('element-plus/dist/locale/zh-cn.mjs', () => ({ default: {} }))

export interface MountOptions extends MountingOptions<Component> {
  customStubs?: Record<string, any>
}

export function mountWithPlugins(
  component: Component,
  options: MountOptions = {}
): VueWrapper<any> {
  const { customStubs, ...mountOptions } = options
  const pinia = createPinia()
  setActivePinia(pinia)
  const stubs: Record<string, any> = {
    ...elStubs,
    ...customStubs,
    ...mountOptions.global?.stubs,
  }

  const plugins: NonNullable<MountingOptions<Component>['global']>['plugins'] = [pinia]
  if (!mountOptions.global?.mocks?.['$router']) {
    plugins.push(
      createRouter({
        history: createMemoryHistory(),
        routes: [
          { path: '/', component: { template: '<div></div>' } },
          { path: '/login', component: { template: '<div></div>' } },
          { path: '/register', component: { template: '<div></div>' } },
          { path: '/dashboard', component: { template: '<div></div>' } },
        ],
      }),
    )
  }

  return mount(component, {
    ...mountOptions,
    global: {
      ...mountOptions.global,
      plugins,
      stubs,
    },
  })
}
