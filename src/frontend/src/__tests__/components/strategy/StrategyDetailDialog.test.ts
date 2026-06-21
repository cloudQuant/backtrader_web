import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StrategyDetailDialog from '@/views/strategy-components/StrategyDetailDialog.vue'
import { elStubs } from '@/test/stubs'
import type { StrategyTemplate } from '@/types'

const template: StrategyTemplate = {
  id: 'demo',
  name: 'Demo',
  category: 'trend',
  description: 'Demo template',
  code: 'print("demo")',
  params: {},
}

function mountDialog(readmeContent: string) {
  return mount(StrategyDetailDialog, {
    props: {
      visible: true,
      template,
      detailTab: 'readme',
      paramTableData: [],
      readmeLoading: false,
      readmeContent,
      stripMeta: (value?: string) => value ?? '',
    },
    global: {
      stubs: {
        ...elStubs,
        MonacoEditor: { template: '<div class="monaco-editor" />' },
      },
    },
  })
}

describe('StrategyDetailDialog', () => {
  it('sanitizes markdown before rendering v-html content', () => {
    const wrapper = mountDialog(
      '# Title\n\n<script>alert(1)</script>[bad](javascript:alert(2))<img src=x onerror="alert(3)">',
    )

    const html = wrapper.html()
    expect(html).toContain('<h1>Title</h1>')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('javascript:')
    expect(html).not.toContain('onerror')
  })
})
