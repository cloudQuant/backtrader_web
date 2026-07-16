import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import DataTableSkeleton from '@/components/common/DataTableSkeleton.vue'

describe('DataTableSkeleton', () => {
  it('announces loading and renders the requested row and column density', () => {
    const wrapper = mount(DataTableSkeleton, {
      props: { label: 'Loading quotes', rows: 3, columns: 4 },
    })

    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.attributes('aria-label')).toBe('Loading quotes')
    expect(wrapper.findAll('.data-table-skeleton__row')).toHaveLength(3)
    expect(wrapper.findAll('.data-table-skeleton__row span:not(.sr-only)')).toHaveLength(12)
  })
})
