/**
 * ErrorBoundary 组件单元测试
 * Validates: Requirements 3.10
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'

import ErrorBoundary from '@/components/common/ErrorBoundary.vue'

// el-result stub that renders both default and extra slots
const elResultStub = defineComponent({
  name: 'ElResultStub',
  props: ['icon', 'title', 'subTitle'],
  setup(props, { slots }) {
    return () =>
      h('div', { class: 'el-result' }, [
        h('div', { class: 'el-result__title' }, props.title),
        h('div', { class: 'el-result__subtitle' }, props.subTitle),
        slots.default?.(),
        slots.extra?.(),
      ])
  },
})

// el-button stub that emits click
const elButtonStub = defineComponent({
  name: 'ElButtonStub',
  props: ['type'],
  emits: ['click'],
  setup(_props, { slots, emit }) {
    return () =>
      h(
        'button',
        {
          class: 'el-button',
          onClick: () => emit('click'),
        },
        slots.default?.(),
      )
  },
})

// A child component that renders normally
const NormalChild = defineComponent({
  name: 'NormalChild',
  setup() {
    return () => h('div', { class: 'normal-child' }, 'Hello World')
  },
})

// A child component that throws an error during render
const ThrowingChild = defineComponent({
  name: 'ThrowingChild',
  setup() {
    return () => {
      throw new Error('Test render error')
    }
  },
})

// A child component that conditionally throws based on a prop
const ConditionalThrowChild = defineComponent({
  name: 'ConditionalThrowChild',
  props: { shouldThrow: { type: Boolean, default: true } },
  setup(props) {
    return () => {
      if (props.shouldThrow) {
        throw new Error('Conditional error')
      }
      return h('div', { class: 'recovered-child' }, 'Recovered!')
    }
  },
})

describe('ErrorBoundary', () => {
  const globalStubs = {
    'el-result': elResultStub,
    'el-button': elButtonStub,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    // Suppress console.error from ErrorBoundary
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  describe('正常渲染', () => {
    it('无错误时应正常渲染 slot 内容', () => {
      const wrapper = mount(ErrorBoundary, {
        slots: {
          default: () => h(NormalChild),
        },
        global: { stubs: globalStubs },
      })

      expect(wrapper.find('.normal-child').exists()).toBe(true)
      expect(wrapper.text()).toContain('Hello World')
      // Error UI should not be visible
      expect(wrapper.find('.error-boundary').exists()).toBe(false)
    })
  })

  describe('错误捕获', () => {
    it('子组件抛出错误后应显示错误 UI', async () => {
      const wrapper = mount(ErrorBoundary, {
        slots: {
          default: () => h(ThrowingChild),
        },
        global: { stubs: globalStubs },
      })

      await flushPromises()
      await nextTick()

      // Error boundary should show error UI
      expect(wrapper.find('.error-boundary').exists()).toBe(true)
      // Should display the error title
      expect(wrapper.find('.el-result__title').text()).toBe('页面出错了')
      // Should display the retry button
      expect(wrapper.find('.el-button').exists()).toBe(true)
      expect(wrapper.find('.el-button').text()).toBe('重试')
    })

    it('应显示自定义 fallbackTitle', async () => {
      const wrapper = mount(ErrorBoundary, {
        props: { fallbackTitle: '自定义错误标题' },
        slots: {
          default: () => h(ThrowingChild),
        },
        global: { stubs: globalStubs },
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.find('.el-result__title').text()).toBe('自定义错误标题')
    })

    it('应显示截断的错误消息（不超过 200 字符）', async () => {
      const LongErrorChild = defineComponent({
        name: 'LongErrorChild',
        setup() {
          return () => {
            throw new Error('A'.repeat(300))
          }
        },
      })

      const wrapper = mount(ErrorBoundary, {
        slots: {
          default: () => h(LongErrorChild),
        },
        global: { stubs: globalStubs },
      })

      await flushPromises()
      await nextTick()

      const subtitle = wrapper.find('.el-result__subtitle').text()
      // 200 chars + '...' = 203 chars max
      expect(subtitle.length).toBeLessThanOrEqual(203)
      expect(subtitle.endsWith('...')).toBe(true)
    })

    it('应触发 error 事件', async () => {
      const wrapper = mount(ErrorBoundary, {
        slots: {
          default: () => h(ThrowingChild),
        },
        global: { stubs: globalStubs },
      })

      await flushPromises()
      await nextTick()

      const errorEvents = wrapper.emitted('error')
      expect(errorEvents).toBeTruthy()
      expect(errorEvents!.length).toBeGreaterThanOrEqual(1)
      expect(errorEvents![0][0]).toBeInstanceOf(Error)
      expect((errorEvents![0][0] as Error).message).toBe('Test render error')
    })
  })

  describe('重试机制', () => {
    it('点击重试按钮后应恢复子组件渲染', async () => {
      // Use a counter to track renders - first render throws, after retry it succeeds
      let renderCount = 0
      const RetryableChild = defineComponent({
        name: 'RetryableChild',
        setup() {
          return () => {
            renderCount++
            if (renderCount === 1) {
              throw new Error('First render error')
            }
            return h('div', { class: 'retried-child' }, 'Success after retry')
          }
        },
      })

      const wrapper = mount(ErrorBoundary, {
        slots: {
          default: () => h(RetryableChild),
        },
        global: { stubs: globalStubs },
      })

      await flushPromises()
      await nextTick()

      // Should show error UI after first render
      expect(wrapper.find('.error-boundary').exists()).toBe(true)

      // Click retry button
      await wrapper.find('.el-button').trigger('click')
      await flushPromises()
      await nextTick()

      // After retry, the child should render successfully
      expect(wrapper.find('.error-boundary').exists()).toBe(false)
      expect(wrapper.find('.retried-child').exists()).toBe(true)
      expect(wrapper.text()).toContain('Success after retry')
    })

    it('点击重试后应触发 retry 事件', async () => {
      const wrapper = mount(ErrorBoundary, {
        slots: {
          default: () => h(ThrowingChild),
        },
        global: { stubs: globalStubs },
      })

      await flushPromises()
      await nextTick()

      // Click retry
      await wrapper.find('.el-button').trigger('click')

      const retryEvents = wrapper.emitted('retry')
      expect(retryEvents).toBeTruthy()
      expect(retryEvents!.length).toBe(1)
    })
  })
})
