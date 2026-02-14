import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import MonacoEditor from './MonacoEditor.vue'

// Mock monaco-editor before imports
const mockEditor = {
  getValue: vi.fn(() => ''),
  setValue: vi.fn(),
  dispose: vi.fn(),
  onDidChangeModelContent: vi.fn(),
  updateOptions: vi.fn(),
}

vi.mock('monaco-editor', () => ({
  editor: {
    create: vi.fn(() => mockEditor),
    setTheme: vi.fn(),
  },
}))

describe('MonacoEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should render editor container', () => {
    const wrapper = mount(MonacoEditor, {
      props: {
        modelValue: 'print("hello")',
      },
    })
    expect(wrapper.find('.monaco-editor-container').exists()).toBe(true)
  })

  it('should use default height', () => {
    const wrapper = mount(MonacoEditor, {
      props: {
        modelValue: '',
      },
    })
    const container = wrapper.find('.monaco-editor-container')
    expect(container.attributes('style')).toContain('height: 400px')
  })

  it('should use custom height', () => {
    const wrapper = mount(MonacoEditor, {
      props: {
        modelValue: '',
        height: 600,
      },
    })
    const container = wrapper.find('.monaco-editor-container')
    expect(container.attributes('style')).toContain('height: 600px')
  })

  it('should use default language as python', () => {
    const wrapper = mount(MonacoEditor, {
      props: {
        modelValue: '',
      },
    })
    expect(wrapper.props('language')).toBe('python')
  })

  it('should accept custom language', () => {
    const wrapper = mount(MonacoEditor, {
      props: {
        modelValue: '',
        language: 'javascript',
      },
    })
    expect(wrapper.props('language')).toBe('javascript')
  })

  it('should use default theme', () => {
    const wrapper = mount(MonacoEditor, {
      props: {
        modelValue: '',
      },
    })
    expect(wrapper.props('theme')).toBe('vs')
  })

  it('should accept custom theme', () => {
    const wrapper = mount(MonacoEditor, {
      props: {
        modelValue: '',
        theme: 'vs-dark',
      },
    })
    expect(wrapper.props('theme')).toBe('vs-dark')
  })

  it('should be editable by default', () => {
    const wrapper = mount(MonacoEditor, {
      props: {
        modelValue: '',
      },
    })
    expect(wrapper.props('readOnly')).toBe(false)
  })

  it('should accept readOnly prop', () => {
    const wrapper = mount(MonacoEditor, {
      props: {
        modelValue: '',
        readOnly: true,
      },
    })
    expect(wrapper.props('readOnly')).toBe(true)
  })

  it('should emit update:modelValue on content change', async () => {
    const wrapper = mount(MonacoEditor, {
      props: {
        modelValue: 'initial code',
      },
      propsData: {
        modelValue: 'initial code',
      },
    })

    // The onDidChangeModelContent callback should be registered
    expect(mockEditor.onDidChangeModelContent).toHaveBeenCalled()

    // Simulate content change by getting the callback
    const changeCallback = mockEditor.onDidChangeModelContent.mock.calls[0]?.[0]
    if (changeCallback) {
      mockEditor.getValue.mockReturnValue('new code')
      changeCallback()

      // Check if v-model update was triggered
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    }
  })
})
