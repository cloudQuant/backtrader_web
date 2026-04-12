import api from './index'
import type {
  DataInterface,
  DataInterfaceFormPayload,
  DataScript,
  DataScriptFormPayload,
  DataTable,
  DataTableRowsResponse,
  DataTableSchemaResponse,
  ExecutionStatsResponse,
  ExecutionTriggerResponse,
  InterfaceCategory,
  PaginatedResponse,
  PaginationQuery,
  ScheduledTask,
  ScheduledTaskFormPayload,
  ScheduleTemplateResponse,
  ScriptRunRequest,
  ScriptStatsResponse,
  TaskExecution,
} from '@/types'

export const akshareScriptsApi = {
  list(params?: PaginationQuery & { category?: string; keyword?: string; is_active?: boolean }) {
    return api.get<PaginatedResponse<DataScript>>('/data/scripts', { params })
  },
  getCategories() {
    return api.get<string[]>('/data/scripts/categories')
  },
  getStats() {
    return api.get<ScriptStatsResponse>('/data/scripts/stats')
  },
  getDetail(scriptId: string) {
    return api.get<DataScript>(`/data/scripts/${scriptId}`)
  },
  scan() {
    return api.post<{ registered: number; updated: number; errors: string[] }>('/data/scripts/scan')
  },
  run(scriptId: string, payload: ScriptRunRequest) {
    return api.post<ExecutionTriggerResponse, ScriptRunRequest>(`/data/scripts/${scriptId}/run`, payload)
  },
  toggle(scriptId: string) {
    return api.put<DataScript>(`/data/scripts/${scriptId}/toggle`)
  },
  create(payload: DataScriptFormPayload) {
    return api.post<DataScript, DataScriptFormPayload>('/data/scripts/admin/scripts', payload)
  },
  update(scriptId: string, payload: Partial<DataScriptFormPayload>) {
    return api.put<DataScript, Partial<DataScriptFormPayload>>(`/data/scripts/admin/scripts/${scriptId}`, payload)
  },
  delete(scriptId: string) {
    return api.delete<void>(`/data/scripts/admin/scripts/${scriptId}`)
  },
}

export const akshareTasksApi = {
  getScheduleTemplates() {
    return api.get<{ templates: ScheduleTemplateResponse[] }>('/data/tasks/schedule/templates')
  },
  list(params?: PaginationQuery & { is_active?: boolean }) {
    return api.get<PaginatedResponse<ScheduledTask>>('/data/tasks', { params })
  },
  getDetail(taskId: number) {
    return api.get<ScheduledTask>(`/data/tasks/${taskId}`)
  },
  create(payload: ScheduledTaskFormPayload) {
    return api.post<ScheduledTask, ScheduledTaskFormPayload>('/data/tasks', payload)
  },
  update(taskId: number, payload: Partial<ScheduledTaskFormPayload>) {
    return api.put<ScheduledTask, Partial<ScheduledTaskFormPayload>>(`/data/tasks/${taskId}`, payload)
  },
  delete(taskId: number) {
    return api.delete<void>(`/data/tasks/${taskId}`)
  },
  toggle(taskId: number) {
    return api.patch<ScheduledTask>(`/data/tasks/${taskId}/toggle`)
  },
  run(taskId: number) {
    return api.post<ExecutionTriggerResponse>(`/data/tasks/${taskId}/run`)
  },
  getExecutions(taskId: number, params?: PaginationQuery) {
    return api.get<PaginatedResponse<TaskExecution>>(`/data/tasks/${taskId}/executions`, { params })
  },
}

export const akshareExecutionsApi = {
  list(params?: PaginationQuery & {
    task_id?: number
    script_id?: string
    status?: string
    start_date?: string
    end_date?: string
  }) {
    return api.get<PaginatedResponse<TaskExecution>>('/data/executions', { params })
  },
  getStats() {
    return api.get<ExecutionStatsResponse>('/data/executions/stats')
  },
  getRecent(limit: number = 20) {
    return api.get<TaskExecution[]>('/data/executions/recent', { params: { limit } })
  },
  getRunning() {
    return api.get<TaskExecution[]>('/data/executions/running')
  },
  getDetail(executionId: string) {
    return api.get<TaskExecution>(`/data/executions/${executionId}`)
  },
  retry(executionId: string) {
    return api.post<ExecutionTriggerResponse>(`/data/executions/${executionId}/retry`)
  },
}

export const akshareTablesApi = {
  list(params?: PaginationQuery & { search?: string }) {
    return api.get<PaginatedResponse<DataTable>>('/data/tables', { params })
  },
  getDetail(tableId: number) {
    return api.get<DataTable>(`/data/tables/${tableId}`)
  },
  getSchema(tableId: number) {
    return api.get<DataTableSchemaResponse>(`/data/tables/${tableId}/schema`)
  },
  getRows(tableId: number, params?: PaginationQuery) {
    return api.get<DataTableRowsResponse>(`/data/tables/${tableId}/data`, { params })
  },
}

export const akshareInterfacesApi = {
  getCategories() {
    return api.get<InterfaceCategory[]>('/data/interfaces/categories')
  },
  list(params?: PaginationQuery & { category_id?: number; search?: string; is_active?: boolean }) {
    return api.get<PaginatedResponse<DataInterface>>('/data/interfaces', { params })
  },
  getDetail(interfaceId: number) {
    return api.get<DataInterface>(`/data/interfaces/${interfaceId}`)
  },
  bootstrap(refresh: boolean = false) {
    return api.post<{ created: number; updated: number }>('/data/interfaces/bootstrap', undefined, {
      params: { refresh },
    })
  },
  create(payload: DataInterfaceFormPayload) {
    return api.post<DataInterface, DataInterfaceFormPayload>('/data/interfaces', payload)
  },
  update(interfaceId: number, payload: Partial<DataInterfaceFormPayload>) {
    return api.put<DataInterface, Partial<DataInterfaceFormPayload>>(`/data/interfaces/${interfaceId}`, payload)
  },
  delete(interfaceId: number) {
    return api.delete<void>(`/data/interfaces/${interfaceId}`)
  },
}
