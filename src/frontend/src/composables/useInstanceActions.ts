/**
 * Composable for instance list actions (start, stop, remove, batch).
 * Shared between LiveTradingPage and SimulatePage.
 */

import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getErrorMessage } from '@/api'
import i18n from '@/i18n'

function tt(key: string, named?: Record<string, unknown>): string {
  return named ? i18n.global.t(key, named) : i18n.global.t(key)
}

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

export function statusLabel(status: string): string {
  switch (status) {
    case 'running':
      return tt('instanceActions.statusRunning')
    case 'stopped':
      return tt('instanceActions.statusStopped')
    case 'error':
      return tt('instanceActions.statusError')
    default:
      return status
  }
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
      ElMessage.success(tt('instanceActions.msgStarted', { name: inst.strategy_name }))
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, tt('instanceActions.msgStartFailed')))
    } finally {
      delete actionLoading.value[inst.id]
    }
  }

  async function handleStop(inst: T) {
    actionLoading.value[inst.id] = 'stop'
    try {
      const updated = await api.stop(inst.id)
      Object.assign(inst, updated)
      ElMessage.success(tt('instanceActions.msgStopped', { name: inst.strategy_name }))
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, tt('instanceActions.msgStopFailed')))
    } finally {
      delete actionLoading.value[inst.id]
    }
  }

  async function handleRemove(inst: T) {
    actionLoading.value[inst.id] = 'remove'
    try {
      await api.remove(inst.id)
      ElMessage.success(tt('instanceActions.msgRemoved'))
      await api.loadData()
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, tt('instanceActions.msgRemoveFailed')))
    } finally {
      delete actionLoading.value[inst.id]
    }
  }

  async function handleStartAll() {
    batchLoading.value = true
    try {
      const res = await api.startAll()
      ElMessage.success(
        tt('instanceActions.msgStartAllResult', { success: res.success, failed: res.failed })
      )
      await api.loadData()
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, tt('instanceActions.msgBatchStartFail')))
    } finally {
      batchLoading.value = false
    }
  }

  async function handleStopAll() {
    batchLoading.value = true
    try {
      const res = await api.stopAll()
      ElMessage.success(
        tt('instanceActions.msgStopAllResult', { success: res.success, failed: res.failed })
      )
      await api.loadData()
    } catch (e: unknown) {
      ElMessage.error(getErrorMessage(e, tt('instanceActions.msgBatchStopFail')))
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
