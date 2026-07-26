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

  it('exposes a single primary action without making the whole card a nested button', () => {
    const wrapper = doMount()
    expect(wrapper.find('.strategy-card').attributes('role')).toBeUndefined()
    expect(wrapper.findAll('.strategy-card-actions > .el-button')).toHaveLength(1)
    expect(wrapper.find('summary').attributes('aria-label')).toBe('strategy.moreActions')
  })

  it('emits use as the primary action and detail/backtest from the overflow menu', async () => {
    const wrapper = doMount()
    await wrapper.find('.strategy-card-actions > .el-button').trigger('click')
    await wrapper.findAll('[role="menuitem"]')[0].trigger('click')
    await wrapper.findAll('[role="menuitem"]')[1].trigger('click')

    expect(wrapper.emitted('use')?.[0]?.[0]).toEqual(tpl)
    expect(wrapper.emitted('detail')?.[0]?.[0]).toEqual(tpl)
    expect(wrapper.emitted('backtest')?.[0]?.[0]).toEqual(tpl)
  })
})
