import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ResponsiveDataGrid from '@/components/common/ResponsiveDataGrid.vue'

describe('ResponsiveDataGrid', () => {
  it('renders desktop and mobile slots with an accessible mobile region', () => {
    const wrapper = mount(ResponsiveDataGrid, {
      props: { mobileLabel: 'Quote rows' },
      slots: {
        desktop: '<table><tbody><tr><td>desktop row</td></tr></tbody></table>',
        mobile: '<ol><li>mobile row</li></ol>',
      },
    })

    expect(wrapper.find('.responsive-data-grid__desktop table').exists()).toBe(true)
    expect(wrapper.find('.responsive-data-grid__mobile').attributes('aria-label')).toBe('Quote rows')
    expect(wrapper.find('.responsive-data-grid__mobile li').text()).toBe('mobile row')
  })
})
