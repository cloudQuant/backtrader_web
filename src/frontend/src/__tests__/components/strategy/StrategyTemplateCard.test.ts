import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string, p?: Record<string, unknown>) => (p ? `${k}:${JSON.stringify(p)}` : k) }),
}))

import StrategyTemplateCard from '@/views/strategy-components/StrategyTemplateCard.vue'
import { elStubs } from '@/test/stubs'

// el-button stub that forwards the native event so `@click.stop` works.
const elButtonForwarding = {
  name: 'ElButtonStub',
  template: '<button class="el-button" @click="$emit(\'click\', $event)"><slot /></button>',
}

const tpl = {
  id: 'tpl-1',
  name: 'Dual MA',
  category: 'trend',
  description: 'A trend strategy | meta-junk',
  params: { fast: 1, slow: 2 },
} as never

function doMount() {
  return mount(StrategyTemplateCard, {
    props: { tpl },
    global: { stubs: { ...elStubs, 'el-button': elButtonForwarding } },
  })
}

describe('StrategyTemplateCard', () => {
  it('renders the template name, id and stripped description', () => {
    const wrapper = doMount()
    const html = wrapper.html()
    expect(html).toContain('Dual MA')
    expect(html).toContain('tpl-1')
    expect(html).toContain('A trend strategy')
    expect(html).not.toContain('meta-junk')
  })

  it('emits detail when the card body is activated', async () => {
    const wrapper = doMount()
    await wrapper.find('.strategy-card').trigger('click')
    expect(wrapper.emitted('detail')?.[0]?.[0]).toEqual(tpl)
  })

  it('emits use and backtest from the action buttons', async () => {
    const wrapper = doMount()
    const buttons = wrapper.findAll('button')
    // detail / use / backtest order in template
    expect(buttons.length).toBeGreaterThanOrEqual(3)
    await buttons[1].trigger('click')
    await buttons[2].trigger('click')
    expect(wrapper.emitted('use')?.[0]?.[0]).toEqual(tpl)
    expect(wrapper.emitted('backtest')?.[0]?.[0]).toEqual(tpl)
  })
})
