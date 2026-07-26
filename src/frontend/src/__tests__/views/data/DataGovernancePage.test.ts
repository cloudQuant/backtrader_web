import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import type {
  DataGovernanceEndpoint,
  DataGovernanceProvider,
  DataPreviewResponse,
} from '@/api/dataGovernance'
import { elStubs } from '@/test/stubs'

const fixtures = vi.hoisted(() => {
  const providers: DataGovernanceProvider[] = [
    {
      id: 'provider-1',
      provider_id: 'akshare',
      name: 'AkShare',
      category: 'market_data',
      auth_type: 'none',
      api_key_env: null,
      rate_limit: 120,
      is_active: true,
    },
    {
      id: 'provider-2',
      provider_id: 'eastmoney',
      name: 'EastMoney',
      category: 'market_data',
      auth_type: 'api_key',
      api_key_env: 'EASTMONEY_KEY',
      rate_limit: 60,
      is_active: false,
    },
  ]

  const endpoints: DataGovernanceEndpoint[] = [
    {
      id: 'endpoint-1',
      provider_id: 'akshare',
      endpoint_name: 'stock_zh_a_hist',
      display_name: 'A 股历史行情',
      category: 'stock',
      function_path: 'akshare.stock_zh_a_hist',
      params_schema: { symbol: { type: 'string', required: true } },
      auth_type: 'none',
      api_key_env: null,
      rate_limit: 100,
      cache_ttl_sec: 300,
      target_database: 'akshare_data',
      target_table: 'stock_zh_a_hist',
      normalization_profile: { mode: 'table' },
      quality_profile: { required_columns: ['date', 'close'] },
      incremental_sync_key: 'date',
      is_active: true,
    },
    {
      id: 'endpoint-2',
      provider_id: 'eastmoney',
      endpoint_name: 'fund_flow',
      display_name: '资金流向',
      category: 'capital_flow',
      function_path: 'eastmoney.fund_flow',
      params_schema: {},
      auth_type: 'api_key',
      api_key_env: 'EASTMONEY_KEY',
      rate_limit: 50,
      cache_ttl_sec: 0,
      target_database: 'market_data',
      target_table: null,
      normalization_profile: {},
      quality_profile: {},
      incremental_sync_key: '',
      is_active: false,
    },
  ]

  const preview: DataPreviewResponse = {
    columns: ['date', 'close'],
    rows: [{ date: '2026-07-01', close: 12.3 }],
    metadata: { source: 'mock' },
    source_timestamp: '2026-07-01T09:00:00Z',
    provider_latency_ms: 42,
    quality_warnings: [],
    provider_id: 'akshare',
    endpoint_name: 'stock_zh_a_hist',
  }

  return { providers, endpoints, preview }
})

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) => {
      if (params?.count !== undefined) return `${key}:${params.count}`
      if (params?.id !== undefined) return `${key}:${params.id}`
      return key
    },
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/api/dataGovernance', () => ({
  dataGovernanceApi: {
    bootstrap: vi.fn(),
    listProviders: vi.fn(),
    listEndpoints: vi.fn(),
    previewEndpoint: vi.fn(),
    createJob: vi.fn(),
  },
}))

vi.mock('@/api/index', () => ({
  getErrorMessage: (_error: unknown, fallback: string) => fallback,
}))

import { ElMessage } from 'element-plus'
import DataGovernancePage from '@/views/data/DataGovernancePage.vue'
import { dataGovernanceApi } from '@/api/dataGovernance'

const api = dataGovernanceApi as unknown as Record<string, ReturnType<typeof vi.fn>>

function doMount() {
  return mount(DataGovernancePage, { global: { stubs: elStubs } })
}

describe('DataGovernancePage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    api.bootstrap.mockResolvedValue({
      providers: 2,
      seed_endpoints: 1,
      akshare_migrated_endpoints: 1,
    })
    api.listProviders.mockResolvedValue({ items: fixtures.providers, total: fixtures.providers.length })
    api.listEndpoints.mockResolvedValue({ items: fixtures.endpoints, total: fixtures.endpoints.length })
    api.previewEndpoint.mockResolvedValue(fixtures.preview)
    api.createJob.mockResolvedValue({
      id: 'job-1',
      endpoint_id: 'endpoint-1',
      status: 'queued',
      row_count: 0,
      created_at: '2026-07-01T09:00:00Z',
    })
  })

  it('bootstraps and loads providers and endpoints on mount', async () => {
    doMount()
    await flushPromises()

    expect(api.bootstrap).toHaveBeenCalled()
    expect(api.listProviders).toHaveBeenCalled()
    expect(api.listEndpoints).toHaveBeenCalledWith(undefined)
  })

  it('renders the redesigned governance workbench', async () => {
    const wrapper = doMount()
    await flushPromises()

    expect(wrapper.find('[data-test="governance-hero"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="governance-metrics"]').findAll('.governance-metric')).toHaveLength(4)
    expect(wrapper.find('[data-test="governance-providers-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="governance-endpoints-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="governance-endpoints-table"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="governance-mobile-list"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('A 股历史行情')
    expect(wrapper.text()).toContain('AkShare')
    expect(wrapper.text()).toContain('governanceEndpointKicker')
  })

  it('loads endpoints for the selected provider', async () => {
    const vm = doMount().vm as unknown as {
      selectedProviderId: string | undefined
      handleProviderChange: () => Promise<void>
    }
    await flushPromises()

    vm.selectedProviderId = 'akshare'
    await vm.handleProviderChange()

    expect(api.listEndpoints).toHaveBeenLastCalledWith('akshare')
  })

  it('opens endpoint details and runs preview and job actions', async () => {
    const vm = doMount().vm as unknown as {
      openEndpoint: (endpoint: DataGovernanceEndpoint) => void
      previewParamsText: string
      previewEndpoint: () => Promise<void>
      createIngestionJob: () => Promise<void>
      previewResult: DataPreviewResponse | null
    }
    await flushPromises()

    vm.openEndpoint(fixtures.endpoints[0])
    vm.previewParamsText = '{"symbol":"000001"}'
    await vm.previewEndpoint()
    await vm.createIngestionJob()

    expect(api.previewEndpoint).toHaveBeenCalledWith('endpoint-1', { symbol: '000001' })
    expect(api.createJob).toHaveBeenCalledWith('endpoint-1', { symbol: '000001' })
    expect(vm.previewResult?.rows).toHaveLength(1)
    expect(ElMessage.success).toHaveBeenCalledWith('dataPages.governancePreviewLoaded')
    expect(ElMessage.success).toHaveBeenCalledWith('dataPages.governanceJobCreated:job-1')
  })
})
