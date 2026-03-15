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
      units.value = res.items
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
      for (const s of statuses) {
        const idx = units.value.findIndex(u => u.id === s.id)
        if (idx >= 0) {
          units.value[idx].run_status = s.run_status
          units.value[idx].last_task_id = s.last_task_id
          units.value[idx].metrics_snapshot = s.metrics_snapshot
          units.value[idx].run_count = s.run_count
          units.value[idx].last_run_time = s.last_run_time
        }
      }
    } catch {
      // Silently ignore poll failures
    }
  }

  function startPolling(workspaceId: string, intervalMs = 3000) {
    stopPolling()
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
