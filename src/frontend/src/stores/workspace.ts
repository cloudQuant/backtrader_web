import { defineStore } from 'pinia'
import { ref } from 'vue'
import { workspaceApi } from '@/api/workspace'
import type {
  Workspace,
  WorkspaceCreate,
  WorkspaceUpdate,
  StrategyUnit,
  StrategyUnitCreate,
  StrategyUnitUpdate,
  GroupRenameRequest,
  UnitRenameRequest,
  UnitStatusResponse,
} from '@/types/workspace'

function isOptimizationActiveStatus(status: string | null | undefined): boolean {
  return status === 'pending' || status === 'queued' || status === 'running'
}

function isOptimizationTerminalStatus(status: string | null | undefined): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled'
}

function mergeOptimizationRuntimeState(incoming: StrategyUnit, existing?: StrategyUnit): StrategyUnit {
  if (!existing) {
    return incoming
  }

  // If existing has a recently-started active optimization and incoming
  // does NOT report an active status, the backend is still returning stale
  // data (old task or not-yet-committed new task).  Preserve local state.
  const existingActive = isOptimizationActiveStatus(existing.opt_status)
  if (existingActive) {
    const startedAt = existing.opt_started_at_ms ?? 0
    const recentlyStarted = Date.now() - startedAt < 15000
    const preserveQueuedLocalState =
      recentlyStarted &&
      (existing.opt_status === 'pending' || existing.opt_status === 'queued') &&
      !isOptimizationActiveStatus(incoming.opt_status)
    if (preserveQueuedLocalState) {
      return {
        ...incoming,
        last_optimization_task_id: existing.last_optimization_task_id ?? incoming.last_optimization_task_id,
        opt_status: existing.opt_status,
        opt_total: existing.opt_total,
        opt_completed: existing.opt_completed,
        opt_progress: existing.opt_progress,
        opt_elapsed_time: existing.opt_elapsed_time,
        opt_remaining_time: existing.opt_remaining_time,
        opt_started_at_ms: existing.opt_started_at_ms,
        opt_last_sync_at_ms: existing.opt_last_sync_at_ms,
      }
    }
  }

  const incomingActive = isOptimizationActiveStatus(incoming.opt_status)
  // Otherwise use incoming data but carry over local timing fields
  return {
    ...incoming,
    opt_started_at_ms: incomingActive
      ? (existing.opt_started_at_ms ?? incoming.opt_started_at_ms ?? null)
      : (incoming.opt_started_at_ms ?? null),
    opt_last_sync_at_ms: incomingActive
      ? (existing.opt_last_sync_at_ms ?? incoming.opt_last_sync_at_ms ?? null)
      : (incoming.opt_last_sync_at_ms ?? null),
  }
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspaces = ref<Workspace[]>([])
  const currentWorkspace = ref<Workspace | null>(null)
  const units = ref<StrategyUnit[]>([])
  const selectedUnitIds = ref<string[]>([])
  const loading = ref(false)
  const total = ref(0)

  // ------------------------------------------------------------------
  // Workspace CRUD
  // ------------------------------------------------------------------

  async function fetchWorkspaces(skip = 0, limit = 50) {
    loading.value = true
    try {
      const res = await workspaceApi.list(skip, limit)
      workspaces.value = res.items
      total.value = res.total
    } finally {
      loading.value = false
    }
  }

  async function fetchWorkspace(id: string) {
    loading.value = true
    try {
      currentWorkspace.value = await workspaceApi.get(id)
      return currentWorkspace.value
    } finally {
      loading.value = false
    }
  }

  async function createWorkspace(data: WorkspaceCreate) {
    const ws = await workspaceApi.create(data)
    workspaces.value.unshift(ws)
    total.value++
    return ws
  }

  async function updateWorkspace(id: string, data: WorkspaceUpdate) {
    const ws = await workspaceApi.update(id, data)
    const idx = workspaces.value.findIndex(w => w.id === id)
    if (idx >= 0) workspaces.value[idx] = ws
    if (currentWorkspace.value?.id === id) currentWorkspace.value = ws
    return ws
  }

  async function deleteWorkspace(id: string) {
    await workspaceApi.delete(id)
    workspaces.value = workspaces.value.filter(w => w.id !== id)
    total.value--
    if (currentWorkspace.value?.id === id) currentWorkspace.value = null
  }

  // ------------------------------------------------------------------
  // Strategy Unit CRUD
  // ------------------------------------------------------------------

  async function fetchUnits(workspaceId: string) {
    loading.value = true
    try {
      const res = await workspaceApi.listUnits(workspaceId)
      const existingMap = new Map(units.value.map(unit => [unit.id, unit]))
      units.value = res.items.map(unit => mergeOptimizationRuntimeState(unit, existingMap.get(unit.id)))
    } finally {
      loading.value = false
    }
  }

  async function createUnit(workspaceId: string, data: StrategyUnitCreate) {
    const unit = await workspaceApi.createUnit(workspaceId, data)
    units.value.push(unit)
    return unit
  }

  async function batchCreateUnits(workspaceId: string, data: StrategyUnitCreate[]) {
    const created = await workspaceApi.batchCreateUnits(workspaceId, data)
    units.value.push(...created)
    return created
  }

  async function updateUnit(workspaceId: string, unitId: string, data: StrategyUnitUpdate) {
    const unit = await workspaceApi.updateUnit(workspaceId, unitId, data)
    const idx = units.value.findIndex(u => u.id === unitId)
    if (idx >= 0) units.value[idx] = unit
    return unit
  }

  async function deleteUnit(workspaceId: string, unitId: string) {
    await workspaceApi.deleteUnit(workspaceId, unitId)
    units.value = units.value.filter(u => u.id !== unitId)
  }

  async function bulkDeleteUnits(workspaceId: string, ids: string[]) {
    const res = await workspaceApi.bulkDeleteUnits(workspaceId, { ids })
    units.value = units.value.filter(u => !ids.includes(u.id))
    selectedUnitIds.value = selectedUnitIds.value.filter(id => !ids.includes(id))
    return res.deleted
  }

  async function reorderUnits(workspaceId: string, unitIds: string[]) {
    await workspaceApi.reorderUnits(workspaceId, { unit_ids: unitIds })
    // Re-sort local array to match new order
    const orderMap = new Map(unitIds.map((id, i) => [id, i]))
    units.value.sort((a, b) => (orderMap.get(a.id) ?? 0) - (orderMap.get(b.id) ?? 0))
  }

  async function renameGroup(workspaceId: string, data: GroupRenameRequest) {
    await workspaceApi.renameGroup(workspaceId, data)
    await fetchUnits(workspaceId)
  }

  async function renameUnit(workspaceId: string, data: UnitRenameRequest) {
    await workspaceApi.renameUnit(workspaceId, data)
    await fetchUnits(workspaceId)
  }

  // ------------------------------------------------------------------
  // Selection helpers
  // ------------------------------------------------------------------

  function setSelectedUnitIds(ids: string[]) {
    selectedUnitIds.value = ids
  }

  function clearSelection() {
    selectedUnitIds.value = []
  }

  // ------------------------------------------------------------------
  // Run orchestration (Phase 3)
  // ------------------------------------------------------------------

  const running = ref(false)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  async function runSelectedUnits(workspaceId: string, parallel = false) {
    if (!selectedUnitIds.value.length) return
    running.value = true
    try {
      // Optimistically mark selected as queued
      for (const u of units.value) {
        if (selectedUnitIds.value.includes(u.id)) {
          u.run_status = 'queued'
        }
      }
      const res = await workspaceApi.runUnits(workspaceId, [...selectedUnitIds.value], parallel)
      // Update local state from results
      for (const r of res.results) {
        const idx = units.value.findIndex(u => u.id === r.unit_id)
        if (idx >= 0) {
          units.value[idx].run_status = r.status as StrategyUnit['run_status']
          if (r.task_id) units.value[idx].last_task_id = r.task_id
        }
      }
      return res.results
    } finally {
      running.value = false
    }
  }

  async function stopSelectedUnits(workspaceId: string) {
    if (!selectedUnitIds.value.length) return
    await workspaceApi.stopUnits(workspaceId, [...selectedUnitIds.value])
    // Refresh
    await fetchUnits(workspaceId)
  }

  async function pollStatus(workspaceId: string) {
    try {
      const statuses: UnitStatusResponse[] = await workspaceApi.getUnitsStatus(workspaceId)
      const now = Date.now()
      for (const s of statuses) {
        const idx = units.value.findIndex(u => u.id === s.id)
        if (idx >= 0) {
          const unit = units.value[idx]

          // Always update non-optimization fields
          unit.run_status = s.run_status
          unit.last_task_id = s.last_task_id
          unit.metrics_snapshot = s.metrics_snapshot
          unit.run_count = s.run_count
          unit.last_run_time = s.last_run_time
          unit.bar_count = s.bar_count

          // Bug8 protection: if local has a recently-started active optimization
          // but backend returns stale/terminal/null (e.g. because the submission
          // hasn't been committed to the DB yet or the unit is still waiting in
          // a batch queue), preserve the locally-initialized pending state so the
          // UI doesn't flip back to "已完成".  For units still waiting in the batch
          // queue, refresh opt_started_at_ms to "now" so the elapsed clock stays
          // at zero until the unit actually starts running.
          const localActive = isOptimizationActiveStatus(unit.opt_status)
          const incomingTotal = Math.max(0, Number(s.opt_total ?? 0))
          const incomingCompleted = Math.max(0, Number(s.opt_completed ?? 0))
          const prematureCompleted =
            s.opt_status === 'completed' &&
            incomingTotal > 0 &&
            incomingCompleted < incomingTotal

          if (localActive && prematureCompleted) {
            continue
          }

          const preserveQueuedLocalState =
            localActive &&
            (unit.opt_status === 'pending' || unit.opt_status === 'queued') &&
            !isOptimizationActiveStatus(s.opt_status)
          if (preserveQueuedLocalState) {
            const startedAt = unit.opt_started_at_ms ?? 0
            if (now - startedAt < 15000) {
              unit.opt_started_at_ms = now
              unit.opt_elapsed_time = 0
              unit.opt_remaining_time = 0
              continue
            }
          }

          const preserveRunningLocalState =
            unit.opt_status === 'running' &&
            !isOptimizationTerminalStatus(s.opt_status) &&
            !isOptimizationActiveStatus(s.opt_status)
          if (preserveRunningLocalState) {
            const lastSyncAt = unit.opt_last_sync_at_ms ?? unit.opt_started_at_ms ?? 0
            if (now - lastSyncAt < 10000) {
              continue
            }
          }

          unit.opt_status = s.opt_status
          unit.opt_total = s.opt_total
          unit.opt_completed = s.opt_completed
          unit.opt_progress = s.opt_progress
          unit.opt_elapsed_time = s.opt_elapsed_time
          unit.opt_remaining_time = s.opt_remaining_time
          unit.opt_last_sync_at_ms = now
          if (s.opt_status === 'running') {
            // Backend reports running: trust its elapsed as ground truth and
            // recompute opt_started_at_ms so the frontend live clock is aligned.
            const baseElapsed = Math.max(0, s.opt_elapsed_time ?? 0)
            unit.opt_started_at_ms = now - Math.round(baseElapsed * 1000)
          } else if (s.opt_status === 'pending' || s.opt_status === 'queued') {
            // Backend reports pending/queued: keep the clock at zero.
            unit.opt_started_at_ms = now
            unit.opt_elapsed_time = 0
            unit.opt_remaining_time = 0
          } else if (s.opt_status) {
            unit.opt_started_at_ms = null
            unit.opt_last_sync_at_ms = null
            unit.opt_remaining_time = 0
          } else if (s.opt_status == null) {
            unit.opt_started_at_ms = null
            unit.opt_last_sync_at_ms = null
          }
        }
      }
    } catch {
      // Silently ignore poll failures
    }
  }

  function startPolling(workspaceId: string, intervalMs = 3000) {
    stopPolling()
    void pollStatus(workspaceId)
    pollTimer = setInterval(() => pollStatus(workspaceId), intervalMs)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  return {
    workspaces,
    currentWorkspace,
    units,
    selectedUnitIds,
    loading,
    total,
    running,
    fetchWorkspaces,
    fetchWorkspace,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
    fetchUnits,
    createUnit,
    batchCreateUnits,
    updateUnit,
    deleteUnit,
    bulkDeleteUnits,
    reorderUnits,
    renameGroup,
    renameUnit,
    setSelectedUnitIds,
    clearSelection,
    runSelectedUnits,
    stopSelectedUnits,
    pollStatus,
    startPolling,
    stopPolling,
  }
})
