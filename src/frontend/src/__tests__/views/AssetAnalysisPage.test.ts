import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { elStubs } from '@/test/stubs'
import AssetAnalysisPage from '@/views/investment/AssetAnalysisPage.vue'

const mocks = vi.hoisted(() => ({
  getCapabilities: vi.fn(),
  searchInstruments: vi.fn(),
  resolveInstrument: vi.fn(),
  createTask: vi.fn(),
  getTask: vi.fn(),
  getTaskResult: vi.fn(),
  cancelTask: vi.fn(),
  retryTask: vi.fn(),
  getSignalHistory: vi.fn(),
  getSignalSummary: vi.fn(),
  getSignalEvidence: vi.fn(),
  createReportExport: vi.fn(),
  createReportPublication: vi.fn(),
  downloadReportExport: vi.fn(),
}))

const knowledgeBaseMocks = vi.hoisted(() => ({
  list: vi.fn(),
}))

vi.mock('@/api/assetResearch', () => ({
  assetResearchApi: mocks,
}))

vi.mock('@/api/knowledgeBase', () => ({
  knowledgeBaseApi: knowledgeBaseMocks,
}))

function mountPage(assetType = 'futures') {
  return mount(AssetAnalysisPage, {
    props: { assetType },
    global: { stubs: elStubs },
  })
}

describe('AssetAnalysisPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getCapabilities.mockResolvedValue({
      execution_disabled: true,
      asset_types: [
        {
          asset_type: 'futures',
          research_enabled: true,
          short_open_research_allowed: false,
          reason_codes: [],
        },
      ],
    })
    mocks.resolveInstrument.mockResolvedValue({
      asset_type: 'futures',
      identity_level: 'CONTRACT',
      canonical_id: 'futures:CFFEX:IF2609:CNY',
      display_symbol: 'IF2609',
      name: '沪深300股指期货2609',
      timezone: 'Asia/Shanghai',
      identifier_type: 'CONTRACT',
      identifier_value: 'IF2609',
      metadata_version: 'v1',
      details: {},
    })
    mocks.searchInstruments.mockResolvedValue({
      asset_type: 'futures',
      items: [
        {
          asset_type: 'futures',
          identity_level: 'CONTRACT',
          symbol: 'IF2609',
          name: '沪深300股指期货2609',
          market: 'CFFEX',
          canonical_id: 'futures:CFFEX:IF2609:CNY',
          metadata_version: 'v1',
        },
      ],
    })
    mocks.createTask.mockResolvedValue({
      task_id: 'task-1',
      status: 'QUEUED',
      asset_type: 'futures',
      canonical_id: 'futures:CFFEX:IF2609:CNY',
      progress: 0,
      created_at: '2026-08-01T10:00:00Z',
    })
    mocks.getTask.mockResolvedValue({
      task_id: 'task-1',
      status: 'SUCCEEDED',
      asset_type: 'futures',
      canonical_id: 'futures:CFFEX:IF2609:CNY',
      progress: 100,
      report_id: 'report-1',
      prediction_id: 'prediction-1',
      created_at: '2026-08-01T10:00:00Z',
    })
    mocks.getTaskResult.mockResolvedValue({
      task_id: 'task-1',
      status: 'SUCCEEDED',
      report_id: 'report-1',
      prediction_id: 'prediction-1',
      published_decision: {
        asset_type: 'futures',
        market_view: 'NEUTRAL',
        normalized_direction: 'NEUTRAL',
        position_context: 'UNKNOWN',
        horizon_code: 'standard',
        quality_status: 'ELIGIBLE',
        recommendation: 'HOLD',
        actionability: 'RESEARCH_ONLY',
        trade_intent: 'NONE',
        reason_codes: ['MODEL_NOT_PROMOTED'],
        invalidation_conditions: ['合约流动性显著恶化'],
        execution_disabled: true,
      },
      report: {
        sections: [
          {
            section_id: 'futures',
            title: '合约研究',
            markdown: '结论：谨慎观察。',
            evidence_ids: ['source_snapshot', 'futures:contract_mapping'],
          },
        ],
        disclaimer: '仅用于研究。',
      },
    })
    mocks.getSignalHistory.mockResolvedValue({ items: [], next_cursor: null })
    mocks.getSignalEvidence.mockResolvedValue({
      prediction_id: 'prediction-1',
      canonical_id: 'futures:CFFEX:IF2609:CNY',
      asset_type: 'futures',
      source: {
        source_id: 'fixture-source',
        license_status: 'RESEARCH_APPROVED',
        capabilities: ['price', 'contract_calendar'],
      },
      source_snapshot_hash: 'a'.repeat(64),
      license_tags: ['research-only'],
      versions: {
        feature_version: 'fixture-feature-v1',
        model_version: 'fixture-model-v1',
      },
      reason_codes: ['COMMON.MODEL_NOT_PROMOTED'],
    })
    knowledgeBaseMocks.list.mockResolvedValue({
      total: 1,
      items: [
        {
          id: 'knowledge-base-1',
          owner_id: 'user-1',
          name: '我的投研知识库',
          document_count: 0,
          is_public: false,
          created_at: '2026-08-01T10:00:00Z',
          updated_at: '2026-08-01T10:00:00Z',
        },
      ],
      skip: 0,
      limit: 100,
    })
    mocks.createReportPublication.mockResolvedValue({
      publication_id: 'publication-1',
      report_id: 'report-1',
      target_type: 'KNOWLEDGE_BASE',
      target_ref: 'knowledge-base-1',
      status: 'SUCCEEDED',
      created_at: '2026-08-01T10:00:00Z',
      completed_at: '2026-08-01T10:00:01Z',
    })
    mocks.getSignalSummary.mockResolvedValue({
      asset_type: 'futures',
      canonical_id: 'futures:CFFEX:IF2609:CNY',
      head_spec_hash: null,
      available_head_spec_hashes: [],
      cohort_selection_required: false,
      total_generated_count: 0,
      excluded_prediction_count: 0,
      generated_count: 0,
      scorable_count: 0,
      actioned_generated_count: 0,
      actioned_scorable_count: 0,
      actioned_success_count: 0,
      actioned_success_rate: null,
      coverage_rate: null,
      maturity_rate: null,
      brier_score: null,
      brier_skill_score: null,
      average_net_return: null,
      max_drawdown: null,
      calibration_bins: [],
      action_breakdown: [],
    })
  })

  it('requires an explicit candidate confirmation before creating research, then displays only the published decision', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.instrument-input input').setValue('IF2609')
    const searchButton = wrapper.findAll('button').find((button) => button.text().includes('搜索候选'))
    expect(searchButton).toBeDefined()
    await searchButton!.trigger('click')
    await flushPromises()

    expect(mocks.searchInstruments).toHaveBeenCalledWith('futures', 'IF2609', 20)
    expect(mocks.resolveInstrument).not.toHaveBeenCalled()
    expect(mocks.createTask).not.toHaveBeenCalled()

    const candidateButton = wrapper.findAll('button').find((button) => button.text().includes('确认 IF2609'))
    expect(candidateButton).toBeDefined()
    await candidateButton!.trigger('click')
    await flushPromises()

    expect(mocks.resolveInstrument).toHaveBeenCalledWith({
      asset_type: 'futures',
      query: 'IF2609',
      venue: 'CFFEX',
      canonical_id: 'futures:CFFEX:IF2609:CNY',
      identity_level: 'CONTRACT',
    })
    expect(mocks.createTask).not.toHaveBeenCalled()

    const submitButton = wrapper.findAll('button').find((button) => button.text().includes('开始 期货研究'))
    expect(submitButton).toBeDefined()
    await submitButton!.trigger('click')
    await flushPromises()

    expect(mocks.createTask).toHaveBeenCalledWith(
      expect.objectContaining({
        asset_type: 'futures',
        canonical_id: 'futures:CFFEX:IF2609:CNY',
        position_context: 'UNKNOWN',
      }),
      expect.any(String),
    )
    expect(wrapper.text()).toContain('AI期货')
    expect(wrapper.text()).toContain('持有')
    expect(wrapper.text()).toContain('规范方向')
    expect(wrapper.text()).toContain('持仓上下文')
    expect(wrapper.text()).toContain('执行状态')
    expect(wrapper.text()).toContain('已禁用')
    expect(wrapper.text()).toContain('失效条件')
    expect(wrapper.text()).toContain('合约流动性显著恶化')
    expect(wrapper.text()).toContain('研究用途，不能直接下单')
    expect(wrapper.text()).toContain('预测成绩单')
    expect(wrapper.text()).toContain('Brier 分数')
    expect(wrapper.text()).toContain('平均净收益')
    expect(wrapper.text()).toContain('最大回撤')
    expect(wrapper.text()).toContain('历史预测')
    expect(mocks.getSignalEvidence).toHaveBeenCalledWith('prediction-1')
    expect(wrapper.text()).toContain('公开证据清单')
    expect(wrapper.text()).toContain('fixture-source')
    expect(wrapper.text()).toContain('source_snapshot')
    expect(wrapper.text()).toContain('候选决策始终不向前端公开')
    expect(wrapper.text()).not.toContain('prediction_heads')
  })

  it('uses the identity level declared by an approved fund candidate instead of a page default', async () => {
    mocks.getCapabilities.mockResolvedValue({
      execution_disabled: true,
      asset_types: [
        {
          asset_type: 'fund',
          research_enabled: true,
          short_open_research_allowed: false,
          reason_codes: [],
        },
      ],
    })
    mocks.searchInstruments.mockResolvedValue({
      asset_type: 'fund',
      items: [
        {
          asset_type: 'fund',
          symbol: '000001',
          name: '示例基金 A 类',
          canonical_id: 'fund:share_class:CN:000001:A:CNY',
          metadata_version: 'fund-v1',
          identity_level: 'PRODUCT',
        },
      ],
    })
    mocks.resolveInstrument.mockResolvedValue({
      asset_type: 'fund',
      identity_level: 'PRODUCT',
      canonical_id: 'fund:share_class:CN:000001:A:CNY',
      display_symbol: '000001',
      name: '示例基金 A 类',
      timezone: 'Asia/Shanghai',
      identifier_type: 'FUND_CODE',
      identifier_value: '000001',
      metadata_version: 'fund-v1',
      details: {},
    })

    const wrapper = mountPage('fund')
    await flushPromises()
    await wrapper.find('.instrument-input input').setValue('000001')
    const searchButton = wrapper.findAll('button').find((button) => button.text().includes('搜索候选'))
    expect(searchButton).toBeDefined()
    await searchButton!.trigger('click')
    await flushPromises()

    expect(mocks.searchInstruments).toHaveBeenCalledWith('fund', '000001', 20)

    const candidateButton = wrapper.findAll('button').find((button) => button.text().includes('确认 000001'))
    expect(candidateButton).toBeDefined()
    await candidateButton!.trigger('click')
    await flushPromises()

    expect(mocks.resolveInstrument).toHaveBeenCalledWith({
      asset_type: 'fund',
      query: '000001',
      venue: undefined,
      canonical_id: 'fund:share_class:CN:000001:A:CNY',
      identity_level: 'PRODUCT',
    })
  })

  it('clears a completed asset result before rendering another asset type', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.instrument-input input').setValue('IF2609')
    const searchButton = wrapper.findAll('button').find((button) => button.text().includes('搜索候选'))
    await searchButton!.trigger('click')
    await flushPromises()
    const candidateButton = wrapper.findAll('button').find((button) => button.text().includes('确认 IF2609'))
    await candidateButton!.trigger('click')
    await flushPromises()
    const submitButton = wrapper.findAll('button').find((button) => button.text().includes('开始 期货研究'))
    await submitButton!.trigger('click')
    await flushPromises()

    expect(wrapper.find('.decision-panel').exists()).toBe(true)
    expect(wrapper.find('.report-panel').exists()).toBe(true)
    await wrapper.setProps({ assetType: 'option' })
    await flushPromises()

    expect(wrapper.text()).toContain('AI期权')
    expect(wrapper.find('.decision-panel').exists()).toBe(false)
    expect(wrapper.find('.report-panel').exists()).toBe(false)
  })

  it('saves only a published report to a selected caller knowledge base', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.instrument-input input').setValue('IF2609')
    const searchButton = wrapper.findAll('button').find((button) => button.text().includes('搜索候选'))
    await searchButton!.trigger('click')
    await flushPromises()
    const candidateButton = wrapper.findAll('button').find((button) => button.text().includes('确认 IF2609'))
    await candidateButton!.trigger('click')
    await flushPromises()
    const submitButton = wrapper.findAll('button').find((button) => button.text().includes('开始 期货研究'))
    await submitButton!.trigger('click')
    await flushPromises()

    const saveButton = wrapper.findAll('button').find((button) => button.text().includes('保存到知识库'))
    expect(saveButton).toBeDefined()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(knowledgeBaseMocks.list).toHaveBeenCalledWith({ limit: 100 })
    expect(wrapper.text()).toContain('仅保存已发布研究结论')
    expect((wrapper.find('.knowledge-base-select').element as HTMLSelectElement).value).toBe('knowledge-base-1')
    await wrapper.find('.publication-title .el-input').setValue('期货研究归档')
    const confirmButton = wrapper.findAll('button').find((button) => button.text().includes('确认保存'))
    expect(confirmButton).toBeDefined()
    await confirmButton!.trigger('click')
    await flushPromises()

    expect(mocks.createReportPublication).toHaveBeenCalledWith(
      'report-1',
      {
        target_type: 'KNOWLEDGE_BASE',
        target_ref: 'knowledge-base-1',
        title: '期货研究归档',
      },
      expect.any(String),
    )
    expect(wrapper.text()).toContain('已保存到知识库；保存的是已发布研究结论。')
  })

  it('changes the requirements and copy for an option rather than reusing futures terminology', async () => {
    const wrapper = mountPage('option')
    await flushPromises()

    expect(wrapper.text()).toContain('AI期权')
    expect(wrapper.text()).toContain('完整期权链、合约条款与标的行情')
    expect(wrapper.text()).toContain('到期日、行权价与看涨/看跌')
    expect(wrapper.text()).not.toContain('展期与基差')
  })

  it('keeps the crypto research page free of trade, account, and marketing controls', async () => {
    const wrapper = mountPage('crypto')
    await flushPromises()

    expect(wrapper.text()).toContain('研究用途，不能直接下单')
    expect(wrapper.findAll('a')).toHaveLength(0)
    expect(wrapper.text()).not.toMatch(/交易链接|连接账户|开通账户|立即交易|去交易/)
    expect(wrapper.findAll('button').map((button) => button.text())).not.toEqual(
      expect.arrayContaining([
        expect.stringMatching(/下单|买入|卖出|交易|账户/),
      ]),
    )
  })

  it('labels public shadow history instead of presenting it as the caller\'s own research', async () => {
    mocks.getSignalHistory.mockResolvedValue({
      items: [
        {
          prediction_id: 'public-shadow-1',
          owner_scope: 'PUBLIC_SHADOW',
          asset_type: 'futures',
          canonical_id: 'futures:CFFEX:IF2609:CNY',
          as_of_at: '2026-08-01T10:00:00Z',
          horizon_code: 'standard',
          actionability: 'RESEARCH_ONLY',
          quality_status: 'ELIGIBLE',
          published_decision: { recommendation: 'HOLD' },
        },
      ],
      next_cursor: null,
    })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.instrument-input input').setValue('IF2609')
    const searchButton = wrapper.findAll('button').find((button) => button.text().includes('搜索候选'))
    await searchButton!.trigger('click')
    await flushPromises()
    const candidateButton = wrapper.findAll('button').find((button) => button.text().includes('确认 IF2609'))
    await candidateButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('公共影子')
    expect(wrapper.text()).not.toContain('我的研究')
  })

  it('shows independent failure states for history and scorecard instead of presenting failed requests as empty data', async () => {
    mocks.getSignalHistory.mockRejectedValue(new Error('历史接口超时'))
    mocks.getSignalSummary.mockRejectedValue(new Error('成绩单接口超时'))
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.instrument-input input').setValue('IF2609')
    const searchButton = wrapper.findAll('button').find((button) => button.text().includes('搜索候选'))
    await searchButton!.trigger('click')
    await flushPromises()
    const candidateButton = wrapper.findAll('button').find((button) => button.text().includes('确认 IF2609'))
    await candidateButton!.trigger('click')
    await flushPromises()

    expect(wrapper.find('.history-panel').text()).toContain('无法读取历史预测：历史接口超时')
    expect(wrapper.find('.history-panel').text()).not.toContain('尚无已发布的历史预测。')
    expect(wrapper.find('.scorecard-panel').text()).toContain('无法读取预测成绩单：成绩单接口超时')
    expect(wrapper.find('.scorecard-panel').text()).not.toContain('确认标的后，将显示这个资产的历史评分覆盖率与成熟度。')
  })

  it('keeps a published decision visible and explains when secondary report rendering failed', async () => {
    mocks.getTask.mockResolvedValue({
      task_id: 'task-1',
      status: 'SUCCEEDED',
      asset_type: 'futures',
      canonical_id: 'futures:CFFEX:IF2609:CNY',
      progress: 100,
      error_code: 'REPORT_RENDER_FAILED',
      prediction_id: 'prediction-1',
      created_at: '2026-08-01T10:00:00Z',
    })
    mocks.getTaskResult.mockResolvedValue({
      task_id: 'task-1',
      status: 'SUCCEEDED',
      prediction_id: 'prediction-1',
      published_decision: {
        asset_type: 'futures',
        market_view: 'NEUTRAL',
        normalized_direction: 'NEUTRAL',
        position_context: 'UNKNOWN',
        horizon_code: 'standard',
        quality_status: 'ELIGIBLE',
        recommendation: 'HOLD',
        actionability: 'RESEARCH_ONLY',
        trade_intent: 'NONE',
        reason_codes: ['MODEL_NOT_PROMOTED'],
        invalidation_conditions: [],
        execution_disabled: true,
      },
      report: null,
    })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.instrument-input input').setValue('IF2609')
    const searchButton = wrapper.findAll('button').find((button) => button.text().includes('搜索候选'))
    await searchButton!.trigger('click')
    await flushPromises()
    const candidateButton = wrapper.findAll('button').find((button) => button.text().includes('确认 IF2609'))
    await candidateButton!.trigger('click')
    await flushPromises()
    const submitButton = wrapper.findAll('button').find((button) => button.text().includes('开始 期货研究'))
    await submitButton!.trigger('click')
    await flushPromises()

    expect(wrapper.find('.decision-panel').exists()).toBe(true)
    expect(wrapper.find('.report-panel').text()).toContain('研报正文暂不可用')
    expect(wrapper.find('.report-panel').text()).toContain('已发布结构化结论仍可查看')
  })

  it('keeps task submission closed when the server has no approved source capability', async () => {
    mocks.getCapabilities.mockResolvedValue({
      execution_disabled: true,
      asset_types: [
        {
          asset_type: 'futures',
          research_enabled: false,
          availability_reason: 'SOURCE_CAPABILITY_UNAVAILABLE',
          short_open_research_allowed: false,
          reason_codes: [],
        },
      ],
    })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.instrument-input input').setValue('IF2609')
    const submitButton = wrapper.findAll('button').find((button) => button.text().includes('开始 期货研究'))

    expect(wrapper.text()).toContain('当前尚无获批的数据源')
    await submitButton?.trigger('click')
    expect(mocks.resolveInstrument).not.toHaveBeenCalled()
  })

  it('keeps task submission closed when a source is approved but no master identity is available', async () => {
    mocks.getCapabilities.mockResolvedValue({
      execution_disabled: true,
      asset_types: [
        {
          asset_type: 'futures',
          source_capability_enabled: true,
          instrument_catalog_ready: false,
          research_enabled: false,
          availability_reason: 'INSTRUMENT_CATALOG_UNAVAILABLE',
          short_open_research_allowed: false,
          reason_codes: [],
        },
      ],
    })
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.text()).toContain('尚无可解析的获批标的主数据')
    await wrapper.find('.instrument-input input').setValue('IF2609')
    const submitButton = wrapper.findAll('button').find((button) => button.text().includes('开始 期货研究'))
    await submitButton?.trigger('click')
    expect(mocks.resolveInstrument).not.toHaveBeenCalled()
  })

  it('requests an explicit scorecard cohort instead of aggregating mixed target definitions', async () => {
    const firstHeadSpecHash = 'a'.repeat(64)
    const secondHeadSpecHash = 'b'.repeat(64)
    mocks.getSignalSummary.mockImplementation((_: string, __: string, headSpecHash?: string) =>
      Promise.resolve({
        asset_type: 'futures',
        canonical_id: 'futures:CFFEX:IF2609:CNY',
        head_spec_hash: headSpecHash ?? null,
        available_head_spec_hashes: [firstHeadSpecHash, secondHeadSpecHash],
        cohort_selection_required: !headSpecHash,
        total_generated_count: 2,
        excluded_prediction_count: headSpecHash ? 1 : 2,
        generated_count: headSpecHash ? 1 : 0,
        scorable_count: 0,
        actioned_generated_count: 0,
        actioned_scorable_count: 0,
        actioned_success_count: 0,
        actioned_success_rate: null,
        coverage_rate: null,
        maturity_rate: null,
        brier_score: null,
        brier_skill_score: null,
        average_net_return: null,
        max_drawdown: null,
        calibration_bins: [],
        action_breakdown: [],
      }),
    )
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('.instrument-input input').setValue('IF2609')
    const searchButton = wrapper.findAll('button').find((button) => button.text().includes('搜索候选'))
    await searchButton!.trigger('click')
    await flushPromises()
    const candidateButton = wrapper.findAll('button').find((button) => button.text().includes('确认 IF2609'))
    await candidateButton!.trigger('click')
    await flushPromises()
    const submitButton = wrapper.findAll('button').find((button) => button.text().includes('开始 期货研究'))
    await submitButton!.trigger('click')
    await flushPromises()

    expect(mocks.getSignalSummary).toHaveBeenCalledWith(
      'futures',
      'futures:CFFEX:IF2609:CNY',
      firstHeadSpecHash,
    )
    expect(wrapper.find('.scorecard-panel').text()).toContain('样本不足')
    expect(wrapper.find('.scorecard-panel').text()).not.toContain('0.0%')
  })
})
