/**
 * Composable for instance list actions (start, stop, remove, batch).
 * Shared between LiveTradingPage and SimulatePage.
 */

import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api'

/** Minimal shape required for instance actions (shared by LiveInstanceInfo, SimulationInstanceInfo). */
export interface InstanceInfo {
  id: string
  strategy_id: string
  strategy_name: string
  status: string
}

export interface InstanceActionsApi<T extends InstanceInfo = InstanceInfo> {
  start(instanceId: string): Promise<T>
  stop(instanceId: string): Promise<T>
  remove(instanceId: string): Promise<unknown>
  startAll(): Promise<{ success: number; failed: number }>
  stopAll(): Promise<{ success: number; failed: number }>
  loadData(): Promise<void>
}

const STATUS_LABELS: Record<string, string> = {
  running: '运行中',
  stopped: '已停止',
  error: '异常',
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

export function formatStrategyId(id?: string): string {
  if (!id) return ''
  const idx = id.indexOf('/')
  return idx !== -1 ? id.slice(idx + 1) : id
}

export function useInstanceActions<T extends InstanceInfo = InstanceInfo>(
  api: InstanceActionsApi<T>
) {
  const actionLoading = ref<Record<string, string>>({})
  const batchLoading = ref(false)

  async function handleStart(inst: T) {
    actionLoading.value[inst.id] = 'start'
    try {
      const updated = await api.start(inst.id)
      Object.assign(inst, updated)
      ElMessage.success(`${inst.strategy_name} 已启动`)
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, '启动失败'))
    } finally {
      delete actionLoading.value[inst.id]
    }
  }

  async function handleStop(inst: T) {
    actionLoading.value[inst.id] = 'stop'
    try {
      const updated = await api.stop(inst.id)
      Object.assign(inst, updated)
      ElMessage.success(`${inst.strategy_name} 已停止`)
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, '停止失败'))
    } finally {
      delete actionLoading.value[inst.id]
    }
  }

  async function handleRemove(inst: T) {
    actionLoading.value[inst.id] = 'remove'
    try {
      await api.remove(inst.id)
      ElMessage.success('已删除')
      await api.loadData()
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, '删除失败'))
    } finally {
      delete actionLoading.value[inst.id]
    }
  }

  async function handleStartAll() {
    batchLoading.value = true
    try {
      const res = await api.startAll()
      ElMessage.success(`启动完成: 成功 ${res.success}, 失败 ${res.failed}`)
      await api.loadData()
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, '批量启动失败'))
    } finally {
      batchLoading.value = false
    }
  }

  async function handleStopAll() {
    batchLoading.value = true
    try {
      const res = await api.stopAll()
      ElMessage.success(`停止完成: 成功 ${res.success}, 失败 ${res.failed}`)
      await api.loadData()
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, '批量停止失败'))
    } finally {
      batchLoading.value = false
    }
  }

  return {
    actionLoading,
    batchLoading,
    handleStart,
    handleStop,
    handleRemove,
    handleStartAll,
    handleStopAll,
  }
}
