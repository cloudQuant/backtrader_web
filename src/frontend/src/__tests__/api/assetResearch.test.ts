import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}))

describe('assetResearchApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses the versioned multi-asset API with idempotent task creation', async () => {
    const { assetResearchApi } = await import('@/api/assetResearch')
    const apiModule = (await import('@/api/index')).default
    const get = vi.mocked(apiModule.get).mockResolvedValue({} as never)
    const post = vi.mocked(apiModule.post).mockResolvedValue({} as never)

    await assetResearchApi.searchInstruments('futures', 'IF2609', 20, 'CONTRACT')
    expect(get).toHaveBeenCalledWith('/asset-research/instruments/search', {
      params: {
        asset_type: 'futures',
        query: 'IF2609',
        limit: 20,
        identity_level: 'CONTRACT',
      },
    })

    await assetResearchApi.resolveInstrument({
      asset_type: 'futures',
      query: 'IF2609',
      venue: 'CFFEX',
      canonical_id: 'futures:CFFEX:IF2609:CNY',
      identity_level: 'CONTRACT',
    })
    expect(post).toHaveBeenCalledWith('/asset-research/instruments/resolve', {
      asset_type: 'futures',
      query: 'IF2609',
      venue: 'CFFEX',
      canonical_id: 'futures:CFFEX:IF2609:CNY',
      identity_level: 'CONTRACT',
    })

    await assetResearchApi.createTask(
      { asset_type: 'futures', canonical_id: 'futures:CFFEX:IF2609:CNY', horizon_code: 'standard' },
      'task-key-1',
    )
    expect(post).toHaveBeenCalledWith(
      '/asset-research/tasks',
      { asset_type: 'futures', canonical_id: 'futures:CFFEX:IF2609:CNY', horizon_code: 'standard' },
      { headers: { 'Idempotency-Key': 'task-key-1' } },
    )

    await assetResearchApi.getSignalSummary('futures', 'futures:CFFEX:IF2609:CNY')
    expect(get).toHaveBeenCalledWith('/asset-research/signals/summary', {
      params: { asset_type: 'futures', canonical_id: 'futures:CFFEX:IF2609:CNY' },
    })

    await assetResearchApi.getSignalEvidence('prediction-1')
    expect(get).toHaveBeenCalledWith('/asset-research/signals/prediction-1/evidence')

    await assetResearchApi.getSignalSummary(
      'futures',
      'futures:CFFEX:IF2609:CNY',
      'a'.repeat(64),
    )
    expect(get).toHaveBeenCalledWith('/asset-research/signals/summary', {
      params: {
        asset_type: 'futures',
        canonical_id: 'futures:CFFEX:IF2609:CNY',
        head_spec_hash: 'a'.repeat(64),
      },
    })

    await assetResearchApi.createReportExport('report-1', 'PDF', 'export-key-1')
    expect(post).toHaveBeenCalledWith(
      '/asset-research/reports/report-1/exports',
      { format: 'PDF' },
      { headers: { 'Idempotency-Key': 'export-key-1' } },
    )

    await assetResearchApi.createReportPublication(
      'report-1',
      { target_type: 'KNOWLEDGE_BASE', target_ref: 'knowledge-base-1', title: '期货研究归档' },
      'publication-key-1',
    )
    expect(post).toHaveBeenCalledWith(
      '/asset-research/reports/report-1/publications',
      { target_type: 'KNOWLEDGE_BASE', target_ref: 'knowledge-base-1', title: '期货研究归档' },
      { headers: { 'Idempotency-Key': 'publication-key-1' } },
    )
  })
})
