import { beforeEach, describe, expect, it, vi } from 'vitest'

import api from '@/api/index'
import { workspaceApi } from '@/api/workspace'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('workspaceApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('covers workspace, unit, trading, optimization, and report endpoints', async () => {
    vi.mocked(api.post).mockResolvedValue({})
    vi.mocked(api.get).mockResolvedValue({})
    vi.mocked(api.put).mockResolvedValue({})
    vi.mocked(api.delete).mockResolvedValue({})

    await workspaceApi.create({ name: '研究工作台', workspace_type: 'research' })
    await workspaceApi.list(5, 20, 'research')
    await workspaceApi.get('ws-1')
    await workspaceApi.update('ws-1', { name: '已更新' })
    await workspaceApi.delete('ws-1')

    await workspaceApi.listUnits('ws-1')
    await workspaceApi.createUnit('ws-1', { strategy_name: '双均线', symbol: 'IF00' })
    await workspaceApi.batchCreateUnits('ws-1', [{ strategy_name: '均线1' }, { strategy_name: '均线2' }])
    await workspaceApi.getUnit('ws-1', 'unit-1')
    await workspaceApi.getUnitRuntimeInfo('ws-1', 'unit-1')
    await workspaceApi.getUnitRuntimeFile('ws-1', 'unit-1', 'logs/stdout.txt', 50)
    await workspaceApi.openUnitRuntimeDir('ws-1', 'unit-1')
    await workspaceApi.updateUnit('ws-1', 'unit-1', { symbol: 'IC00' })
    await workspaceApi.deleteUnit('ws-1', 'unit-1')
    await workspaceApi.bulkDeleteUnits('ws-1', { ids: ['unit-1', 'unit-2'] })
    await workspaceApi.reorderUnits('ws-1', { unit_ids: ['unit-2', 'unit-1'] })
    await workspaceApi.renameGroup('ws-1', { unit_ids: ['unit-1'], mode: 'custom', value: '新分组' })
    await workspaceApi.renameUnit('ws-1', { unit_id: 'unit-1', mode: 'custom', value: '新单元' })

    await workspaceApi.runUnits('ws-1', ['unit-1'], true)
    await workspaceApi.stopUnits('ws-1', ['unit-1'])
    await workspaceApi.getUnitsStatus('ws-1')
    await workspaceApi.getTradingAutoConfig('ws-1')
    await workspaceApi.updateTradingAutoConfig('ws-1', { enabled: true })
    await workspaceApi.getTradingAutoSchedule('ws-1')
    await workspaceApi.getTradingPositions('ws-1', ['unit-1', 'unit-2'])
    await workspaceApi.getTradingDailySummary('ws-1', { unit_id: 'unit-1', start_date: '2026-01-01', end_date: '2026-01-31' })

    await workspaceApi.submitOptimization('ws-1', { unit_id: 'unit-1', param_ranges: { fast: { start: 5, end: 10, step: 1 } } })
    await workspaceApi.getOptimizationProgress('ws-1', 'unit-1')
    await workspaceApi.getOptimizationResults('ws-1', 'unit-1')
    await workspaceApi.getOptimizationResultDetail('ws-1', 'unit-1', 0)
    await workspaceApi.getOptimizationResultKline('ws-1', 'unit-1', 0, '2026-01-01', '2026-01-31')
    await workspaceApi.getOptimizationResultMonthlyReturns('ws-1', 'unit-1', 0)
    await workspaceApi.getOptimizationResultArtifact('ws-1', 'unit-1', 0)
    await workspaceApi.cancelOptimization('ws-1', 'unit-1')
    await workspaceApi.applyBestParams('ws-1', { unit_id: 'unit-1', optimization_task_id: 'task-1', result_index: 0 })

    await workspaceApi.getReport('ws-1')
    await workspaceApi.createReport('ws-1', { start_date: '2026-01-01', end_date: '2026-01-31' })
    await workspaceApi.deleteReport('ws-1')

    expect(api.post).toHaveBeenCalledWith('/workspace/', { name: '研究工作台', workspace_type: 'research' })
    expect(api.get).toHaveBeenCalledWith('/workspace/', { params: { skip: 5, limit: 20, workspace_type: 'research' } })
    expect(api.get).toHaveBeenCalledWith('/workspace/ws-1/units/unit-1/runtime/files/logs/stdout.txt', {
      params: { tail: 50 },
      responseType: 'text',
    })
    expect(api.get).toHaveBeenCalledWith('/workspace/ws-1/trading/positions', {
      params: { unit_ids: 'unit-1,unit-2' },
    })
    expect(api.get).toHaveBeenCalledWith('/workspace/ws-1/optimize/unit-1/results/0/kline', {
      params: { start_date: '2026-01-01', end_date: '2026-01-31' },
    })
    expect(api.post).toHaveBeenCalledWith('/workspace/ws-1/run', { unit_ids: ['unit-1'], parallel: true })
    expect(api.post).toHaveBeenCalledWith('/workspace/ws-1/optimize/apply', {
      unit_id: 'unit-1',
      optimization_task_id: 'task-1',
      result_index: 0,
    })
    expect(api.delete).toHaveBeenCalledWith('/workspace/ws-1/report')
  })

  it('downloads optimization artifacts as zip files', async () => {
    const blob = new Blob(['zip'])
    vi.mocked(api.get).mockResolvedValue(blob)
    globalThis.URL.createObjectURL = vi.fn().mockReturnValue('blob:artifact')
    globalThis.URL.revokeObjectURL = vi.fn()
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    await workspaceApi.downloadOptimizationResultArtifact('ws-1', 'unit-1', 2)

    expect(api.get).toHaveBeenCalledWith('/workspace/ws-1/optimize/unit-1/results/2/artifact/download', {
      responseType: 'blob',
    })
    expect(globalThis.URL.createObjectURL).toHaveBeenCalled()
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalledWith('blob:artifact')
    clickSpy.mockRestore()
  })
})
