/**
 * Shared mounting helper for view tests.
 * Provides isolated Pinia and Router instances for each mount.
 */
import { mount, MountingOptions, VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { elStubs } from './stubs'

export interface MountOptions extends Omit<MountingOptions<any>, 'global'> {
  customStubs?: Record<string, any>
}

export function mountWithPlugins(
  component: any,
  options: MountOptions = {}
): VueWrapper {
  const { customStubs, ...mountOptions } = options
  const pinia = createPinia()
  setActivePinia(pinia)

  const plugins = [pinia]
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
      stubs: {
        ...elStubs,
        ...customStubs,
        ...mountOptions.global?.stubs,
      },
    },
  })
}
