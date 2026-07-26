import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import StockAnalysisReportCard from '@/components/aichat/StockAnalysisReportCard.vue'
import { elStubs } from '@/test/stubs'

vi.mock('@/api/stockAnalysis', () => ({
  stockAnalysisApi: {
    exportReport: vi.fn(),
    saveToKnowledgeBase: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const report = {
  report_id: 'report-1',
  symbol: '600519.SH',
  summary: '趋势较强，但估值和回撤风险需要控制。',
  decision_label: '谨慎持有',
  risk_level: '中等',
  confidence_score: 0.72,
  export_formats: ['markdown', 'html', 'docx', 'pdf'] as Array<'markdown' | 'html' | 'docx' | 'pdf'>,
}

describe('StockAnalysisReportCard', () => {
  it('emits strategy continuation prompts from a stock report', async () => {
    const wrapper = mount(StockAnalysisReportCard, {
      props: { report, knowledgeBaseId: 'kb-1' },
      global: { stubs: { ...elStubs } },
    })

    const ideaButton = wrapper.findAll('button').find(button => button.text().includes('生成策略构思'))
    expect(ideaButton).toBeTruthy()
    await ideaButton!.trigger('click')

    const backtraderButton = wrapper.findAll('button').find(button => button.text().includes('生成Backtrader策略'))
    expect(backtraderButton).toBeTruthy()
    await backtraderButton!.trigger('click')

    expect(wrapper.emitted('continueStrategyIdea')?.[0][0]).toContain('600519.SH 股票分析报告')
    expect(wrapper.emitted('continueStrategyIdea')?.[0][0]).toContain('交易假设')
    expect(wrapper.emitted('continueBacktraderStrategy')?.[0][0]).toContain('Backtrader 策略草案')
    expect(wrapper.emitted('continueBacktraderStrategy')?.[0][0]).toContain('谨慎持有')
  })
})
