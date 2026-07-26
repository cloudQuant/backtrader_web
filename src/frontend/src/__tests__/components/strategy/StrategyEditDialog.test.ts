import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StrategyEditDialog from '@/views/strategy-components/StrategyEditDialog.vue'
import { elStubs } from '@/test/stubs'

const form = {
  name: '',
  description: '',
  code: '',
  category: 'custom',
}

function mountDialog() {
  return mount(StrategyEditDialog, {
    props: {
      visible: true,
      isEdit: false,
      saving: false,
      form,
    },
    global: {
      stubs: {
        ...elStubs,
        MonacoEditor: { template: '<div class="monaco-editor" />' },
      },
    },
  })
}

describe('StrategyEditDialog', () => {
  it('renders a directly editable code textarea', async () => {
    const wrapper = mountDialog()
    const codeInput = wrapper.get('textarea.strategy-code-input')

    await codeInput.setValue('print("ok")')

    expect(wrapper.emitted('update:form')).toEqual([[
      { ...form, code: 'print("ok")' },
    ]])
  })
})
