/**
 * MetricCard 组件测试
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MetricCard from '@/components/charts/MetricCard.vue'

// Element Plus 图标 mock
vi.mock('@element-plus/icons-vue', () => ({
  QuestionFilled: {
    template: '<span>?</span>',
  },
}))

describe('MetricCard', () => {
  describe('基础渲染', () => {
    it('应该正确渲染标题和值', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '测试指标',
          value: 12345.67,
        },
      })

      expect(wrapper.text()).toContain('测试指标')
      expect(wrapper.text()).toContain('12,345.67')
    })

    it('当值为 null 时应该显示 --', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '测试指标',
          value: null,
        },
      })

      expect(wrapper.text()).toContain('--')
    })

    it('当值为 undefined 时应该显示 --', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '测试指标',
          value: undefined,
        },
      })

      expect(wrapper.text()).toContain('--')
    })
  })

  describe('格式化', () => {
    it('应该正确格式化货币值', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '总资产',
          value: 12345.678,
          format: 'currency',
        },
      })

      expect(wrapper.text()).toContain('¥12,345.68')
    })

    it('应该正确格式化百分比值', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '收益率',
          value: 0.1234,
          format: 'percent',
          precision: 2,
        },
      })

      expect(wrapper.text()).toContain('12.34%')
    })

    it('应该正确格式化天数值', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '持仓天数',
          value: 15.5,
          format: 'days',
        },
      })

      expect(wrapper.text()).toContain('15.5天')
    })

    it('应该正确格式化数字值', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '交易次数',
          value: 12345,
          format: 'number',
        },
      })

      expect(wrapper.text()).toContain('12,345')
    })

    it('应该使用指定的精度', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '收益率',
          value: 0.123456,
          format: 'percent',
          precision: 4,
        },
      })

      expect(wrapper.text()).toContain('12.3456%')
    })

    it('应该使用默认精度 2', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '收益率',
          value: 0.123456,
          format: 'percent',
        },
      })

      expect(wrapper.text()).toContain('12.35%')
    })
  })

  describe('变化值', () => {
    it('应该显示正变化值', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '收益率',
          value: 0.05,
          format: 'percent',
          change: 0.023,
        },
      })

      expect(wrapper.text()).toContain('+2.30%')
    })

    it('应该显示负变化值', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '收益率',
          value: -0.05,
          format: 'percent',
          change: -0.023,
        },
      })

      expect(wrapper.text()).toContain('-2.30%')
    })

    it('不显示变化值时应该隐藏变化元素', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '总资产',
          value: 100000,
          format: 'currency',
        },
      })

      // 不应该包含额外的百分比变化
      const html = wrapper.html()
      const hasChangeSpan = html.includes('%') && html.includes('mb-1')
      expect(hasChangeSpan).toBe(false)
    })
  })

  describe('颜色', () => {
    it('正百分比值应该是绿色', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '收益率',
          value: 0.05,
          format: 'percent',
        },
      })

      expect(wrapper.find('.text-green-600').exists()).toBe(true)
    })

    it('负百分比值应该是红色', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '收益率',
          value: -0.05,
          format: 'percent',
        },
      })

      expect(wrapper.find('.text-red-600').exists()).toBe(true)
    })

    it('应该使用指定的成功颜色', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '状态',
          value: 100,
          color: 'success',
        },
      })

      expect(wrapper.find('.text-green-600').exists()).toBe(true)
    })

    it('应该使用指定的危险颜色', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '风险',
          value: 100,
          color: 'danger',
        },
      })

      expect(wrapper.find('.text-red-600').exists()).toBe(true)
    })

    it('应该使用指定的警告颜色', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '警告',
          value: 100,
          color: 'warning',
        },
      })

      expect(wrapper.find('.text-yellow-600').exists()).toBe(true)
    })

    it('正变化值应该是绿色', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '收益率',
          value: 0.05,
          format: 'percent',
          change: 0.023,
        },
      })

      expect(wrapper.find('.text-green-500').exists()).toBe(true)
    })

    it('负变化值应该是红色', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '收益率',
          value: -0.05,
          format: 'percent',
          change: -0.023,
        },
      })

      expect(wrapper.find('.text-red-500').exists()).toBe(true)
    })
  })

  describe('工具提示', () => {
    it('应该显示工具提示图标', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '夏普比率',
          value: 1.5,
          tooltip: '衡量风险调整后收益的指标',
        },
      })

      expect(wrapper.html()).toContain('?')
    })

    it('没有工具提示时不应该显示图标', () => {
      const wrapper = mount(MetricCard, {
        props: {
          title: '总资产',
          value: 100000,
        },
      })

      expect(wrapper.html()).not.toContain('?')
    })
  })
})
