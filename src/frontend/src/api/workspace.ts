import api from './index'
import type {
  BacktestDetailResponse,
  KlineWithSignalsResponse,
  MonthlyReturnsResponse,
} from '@/types/analytics'
import type {
  Workspace,
  WorkspaceCreate,
  WorkspaceUpdate,
  WorkspaceListResponse,
  StrategyUnit,
  StrategyUnitCreate,
  StrategyUnitUpdate,
  StrategyUnitListResponse,
  BulkDeleteRequest,
  SortRequest,
  GroupRenameRequest,
  UnitRenameRequest,
  RunUnitResult,
  UnitStatusResponse,
  UnitOptimizationRequest,
  ApplyBestParamsRequest,
  OptimizationSubmitResult,
  OptimizationArtifactResponse,
  WorkspaceType,
  TradingAutoConfig,
  TradingAutoScheduleItem,
  TradingPositionManagerResponse,
  TradingDailySummaryResponse,
  StrategyUnitRuntimeInfo,
} from '@/types/workspace'

export const workspaceApi = {
  // Workspace CRUD
  async create(data: WorkspaceCreate): Promise<Workspace> {
    return api.post('/workspace/', data)
  },

  async list(skip = 0, limit = 50, workspaceType?: WorkspaceType): Promise<WorkspaceListResponse> {
    return api.get('/workspace/', {
      params: {
        skip,
        limit,
        workspace_type: workspaceType,
      },
    })
  },

  async get(id: string): Promise<Workspace> {
    return api.get(`/workspace/${id}`)
  },

  async update(id: string, data: WorkspaceUpdate): Promise<Workspace> {
    return api.put(`/workspace/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    return api.delete(`/workspace/${id}`)
  },

  // Strategy Unit CRUD
  async listUnits(workspaceId: string): Promise<StrategyUnitListResponse> {
    return api.get(`/workspace/${workspaceId}/units`)
  },

  async createUnit(workspaceId: string, data: StrategyUnitCreate): Promise<StrategyUnit> {
    return api.post(`/workspace/${workspaceId}/units`, data)
  },

  async batchCreateUnits(workspaceId: string, units: StrategyUnitCreate[]): Promise<StrategyUnit[]> {
    return api.post(`/workspace/${workspaceId}/units/batch`, { units })
  },

  async getUnit(workspaceId: string, unitId: string): Promise<StrategyUnit> {
    return api.get(`/workspace/${workspaceId}/units/${unitId}`)
  },

  async getUnitRuntimeInfo(workspaceId: string, unitId: string): Promise<StrategyUnitRuntimeInfo> {
    return api.get(`/workspace/${workspaceId}/units/${unitId}/runtime`)
  },

  async getUnitRuntimeFile(
    workspaceId: string,
    unitId: string,
    relativePath: string,
    tail?: number | null,
  ): Promise<string> {
    const params = tail != null ? { tail } : {}
    const encodedPath = relativePath
      .split('/')
      .map(segment => encodeURIComponent(segment))
      .join('/')
    return api.get(
      `/workspace/${workspaceId}/units/${unitId}/runtime/files/${encodedPath}`,
      { params, responseType: 'text' },
    )
  },

  async openUnitRuntimeDir(
    workspaceId: string,
    unitId: string,
  ): Promise<{ unit_id: string; runtime_dir: string; message: string }> {
    return api.post(`/workspace/${workspaceId}/units/${unitId}/runtime/open`)
  },

  async updateUnit(workspaceId: string, unitId: string, data: StrategyUnitUpdate): Promise<StrategyUnit> {
    return api.put(`/workspace/${workspaceId}/units/${unitId}`, data)
  },

  async deleteUnit(workspaceId: string, unitId: string): Promise<void> {
    return api.delete(`/workspace/${workspaceId}/units/${unitId}`)
  },

  // Bulk operations
  async bulkDeleteUnits(workspaceId: string, data: BulkDeleteRequest): Promise<{ deleted: number }> {
    return api.post(`/workspace/${workspaceId}/units/bulk-delete`, data)
  },

  async reorderUnits(workspaceId: string, data: SortRequest): Promise<void> {
    return api.post(`/workspace/${workspaceId}/units/reorder`, data)
  },

  async renameGroup(workspaceId: string, data: GroupRenameRequest): Promise<void> {
    return api.post(`/workspace/${workspaceId}/units/rename-group`, data)
  },

  async renameUnit(workspaceId: string, data: UnitRenameRequest): Promise<void> {
    return api.post(`/workspace/${workspaceId}/units/rename-unit`, data)
  },

  // Run orchestration
  async runUnits(workspaceId: string, unitIds: string[], parallel = false): Promise<{ results: RunUnitResult[] }> {
    return api.post(`/workspace/${workspaceId}/run`, { unit_ids: unitIds, parallel })
  },

  async stopUnits(workspaceId: string, unitIds: string[]): Promise<{ results: { unit_id: string; cancelled: boolean }[] }> {
    return api.post(`/workspace/${workspaceId}/stop`, { unit_ids: unitIds })
  },

  async getUnitsStatus(workspaceId: string): Promise<UnitStatusResponse[]> {
    return api.get(`/workspace/${workspaceId}/status`)
  },

  async getTradingAutoConfig(workspaceId: string): Promise<TradingAutoConfig> {
    return api.get(`/workspace/${workspaceId}/trading/auto-config`)
  },

  async updateTradingAutoConfig(
    workspaceId: string,
    data: Partial<TradingAutoConfig>,
  ): Promise<TradingAutoConfig> {
    return api.put(`/workspace/${workspaceId}/trading/auto-config`, data)
  },

  async getTradingAutoSchedule(workspaceId: string): Promise<TradingAutoScheduleItem[]> {
    return api.get(`/workspace/${workspaceId}/trading/auto-schedule`)
  },

  async getTradingPositions(
    workspaceId: string,
    unitIds?: string[],
  ): Promise<TradingPositionManagerResponse> {
    return api.get(`/workspace/${workspaceId}/trading/positions`, {
      params: unitIds?.length ? { unit_ids: unitIds.join(',') } : {},
    })
  },

  async getTradingDailySummary(
    workspaceId: string,
    params?: {
      unit_id?: string
      start_date?: string
      end_date?: string
    },
  ): Promise<TradingDailySummaryResponse> {
    return api.get(`/workspace/${workspaceId}/trading/daily-summary`, { params })
  },

  // Optimization
  async submitOptimization(workspaceId: string, data: UnitOptimizationRequest): Promise<OptimizationSubmitResult> {
    return api.post(`/workspace/${workspaceId}/optimize`, data)
  },

  async getOptimizationProgress(workspaceId: string, unitId: string): Promise<Record<string, unknown>> {
    return api.get(`/workspace/${workspaceId}/optimize/${unitId}/progress`)
  },

  async getOptimizationResults(workspaceId: string, unitId: string): Promise<Record<string, unknown>> {
    return api.get(`/workspace/${workspaceId}/optimize/${unitId}/results`)
  },

  async getOptimizationResultDetail(
    workspaceId: string,
    unitId: string,
    resultIndex: number,
  ): Promise<BacktestDetailResponse> {
    return api.get(`/workspace/${workspaceId}/optimize/${unitId}/results/${resultIndex}/detail`)
  },

  async getOptimizationResultKline(
    workspaceId: string,
    unitId: string,
    resultIndex: number,
    startDate?: string,
    endDate?: string,
  ): Promise<KlineWithSignalsResponse> {
    const params: Record<string, string> = {}
    if (startDate) params.start_date = startDate
    if (endDate) params.end_date = endDate
    return api.get(`/workspace/${workspaceId}/optimize/${unitId}/results/${resultIndex}/kline`, { params })
  },

  async getOptimizationResultMonthlyReturns(
    workspaceId: string,
    unitId: string,
    resultIndex: number,
  ): Promise<MonthlyReturnsResponse> {
    return api.get(`/workspace/${workspaceId}/optimize/${unitId}/results/${resultIndex}/monthly-returns`)
  },

  async getOptimizationResultArtifact(
    workspaceId: string,
    unitId: string,
    resultIndex: number,
  ): Promise<OptimizationArtifactResponse> {
    return api.get(`/workspace/${workspaceId}/optimize/${unitId}/results/${resultIndex}/artifact`)
  },

  async downloadOptimizationResultArtifact(
    workspaceId: string,
    unitId: string,
    resultIndex: number,
  ): Promise<void> {
    const response = await api.get<Blob>(
      `/workspace/${workspaceId}/optimize/${unitId}/results/${resultIndex}/artifact/download`,
      { responseType: 'blob' }
    )
    const blob = response instanceof Blob ? response : new Blob([response as BlobPart])
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `optimization_artifact_${resultIndex + 1}.zip`
    link.click()
    URL.revokeObjectURL(url)
  },

  async cancelOptimization(workspaceId: string, unitId: string): Promise<Record<string, unknown>> {
    return api.post(`/workspace/${workspaceId}/optimize/${unitId}/cancel`)
  },

  async applyBestParams(workspaceId: string, data: ApplyBestParamsRequest): Promise<Record<string, unknown>> {
    return api.post(`/workspace/${workspaceId}/optimize/apply`, data)
  },

  // Report
  async getReport(workspaceId: string): Promise<Record<string, unknown>> {
    return api.get(`/workspace/${workspaceId}/report`)
  },

  async createReport(workspaceId: string, config: Record<string, unknown>): Promise<Record<string, unknown>> {
    return api.post(`/workspace/${workspaceId}/report`, config)
  },

  async deleteReport(workspaceId: string): Promise<Record<string, unknown>> {
    return api.delete(`/workspace/${workspaceId}/report`)
  },
}
