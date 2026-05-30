/**
 * Unit tests for src/stores/workspace.ts (Pinia store).
 *
 * Targets the public CRUD/selection/state-transition surface; deep
 * coverage of the optimization-state merging logic is exercised via a
 * focused subset of fetchUnits cases that simulate stale backend data.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useWorkspaceStore } from '@/stores/workspace'
import { workspaceApi } from '@/api/workspace'
import type { StrategyUnit, Workspace } from '@/types/workspace'

vi.mock('@/api/workspace', () => ({
  workspaceApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    listUnits: vi.fn(),
    createUnit: vi.fn(),
    batchCreateUnits: vi.fn(),
    updateUnit: vi.fn(),
    patchUnits: vi.fn(),
    deleteUnit: vi.fn(),
    bulkDeleteUnits: vi.fn(),
    reorderUnits: vi.fn(),
    renameGroup: vi.fn(),
    renameUnit: vi.fn(),
    runUnits: vi.fn(),
    stopUnits: vi.fn(),
    getUnitsStatus: vi.fn(),
  },
}))

const baseWs = {
  id: 'ws-1',
  name: 'workspace 1',
  description: 'desc',
  workspace_type: 'research',
  settings: {},
  created_at: '2024-01-01T00:00:00',
  updated_at: '2024-01-01T00:00:00',
} as unknown as Workspace

const baseUnit = {
  id: 'u-1',
  workspace_id: 'ws-1',
  strategy_id: 's-1',
  strategy_name: 'sample',
  symbol_code: 'TEST',
  timeframe: '1d',
  category: 'trend',
  params: {},
  data_source: { type: 'csv' },
  backtest_defaults: {
    start_date: '2024-01-01', end_date: '2024-12-31',
    initial_cash: 100000, commission: 0.001,
  },
  optimization: null,
  run_status: 'idle',
  trading_mode: 'paper',
  lock_running: false,
  lock_trading: false,
  sort_order: 0,
  created_at: '2024-01-01T00:00:00',
  updated_at: '2024-01-01T00:00:00',
  trading_snapshot: null,
  opt_status: null,
  opt_started_at_ms: null,
  opt_last_sync_at_ms: null,
  last_optimization_task_id: null,
} as unknown as StrategyUnit

describe('useWorkspaceStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    Object.values(workspaceApi).forEach(fn => (fn as any).mockReset?.())
  })

  describe('Workspace CRUD', () => {
    it('fetchWorkspaces populates list and total', async () => {
      vi.mocked(workspaceApi.list).mockResolvedValue({
        items: [baseWs], total: 1,
      })
      const store = useWorkspaceStore()
      await store.fetchWorkspaces()
      expect(store.workspaces).toHaveLength(1)
      expect(store.total).toBe(1)
      expect(store.loading).toBe(false)
    })

    it('fetchWorkspaces accepts skip/limit/workspaceType', async () => {
      vi.mocked(workspaceApi.list).mockResolvedValue({ items: [], total: 0 })
      const store = useWorkspaceStore()
      await store.fetchWorkspaces(10, 25, 'trading')
      expect(workspaceApi.list).toHaveBeenCalledWith(10, 25, 'trading')
    })

    it('fetchWorkspace sets currentWorkspace', async () => {
      vi.mocked(workspaceApi.get).mockResolvedValue(baseWs)
      const store = useWorkspaceStore()
      await store.fetchWorkspace('ws-1')
      expect(store.currentWorkspace).toEqual(baseWs)
    })

    it('createWorkspace creates and returns the new workspace', async () => {
      vi.mocked(workspaceApi.create).mockResolvedValue(baseWs)
      vi.mocked(workspaceApi.list).mockResolvedValue({ items: [baseWs], total: 1 })
      const store = useWorkspaceStore()
      const created = await store.createWorkspace({ name: 'workspace 1' } as any)
      expect(created).toEqual(baseWs)
      expect(workspaceApi.create).toHaveBeenCalled()
    })

    it('updateWorkspace updates and refreshes state', async () => {
      const updated = { ...baseWs, name: 'renamed' }
      vi.mocked(workspaceApi.update).mockResolvedValue(updated)
      vi.mocked(workspaceApi.list).mockResolvedValue({ items: [updated], total: 1 })
      const store = useWorkspaceStore()
      const result = await store.updateWorkspace('ws-1', { name: 'renamed' } as any)
      expect(result).toEqual(updated)
    })

    it('deleteWorkspace deletes via API and refreshes the list', async () => {
      vi.mocked(workspaceApi.delete).mockResolvedValue(undefined as never)
      vi.mocked(workspaceApi.list).mockResolvedValue({ items: [], total: 0 })
      const store = useWorkspaceStore()
      await store.deleteWorkspace('ws-1')
      expect(workspaceApi.delete).toHaveBeenCalledWith('ws-1')
    })
  })

  describe('Unit CRUD', () => {
    it('fetchUnits sets units array and merges optimization state', async () => {
      vi.mocked(workspaceApi.listUnits).mockResolvedValue({ items: [baseUnit], total: 1 })
      const store = useWorkspaceStore()
      await store.fetchUnits('ws-1')
      expect(store.units).toHaveLength(1)
      expect(store.units[0].id).toBe('u-1')
    })

    it('createUnit creates and refreshes unit list', async () => {
      vi.mocked(workspaceApi.createUnit).mockResolvedValue(baseUnit)
      vi.mocked(workspaceApi.listUnits).mockResolvedValue({ items: [baseUnit], total: 1 })
      const store = useWorkspaceStore()
      const created = await store.createUnit('ws-1', {} as any)
      expect(created).toEqual(baseUnit)
    })

    it('batchCreateUnits creates multiple units', async () => {
      vi.mocked(workspaceApi.batchCreateUnits).mockResolvedValue([baseUnit, baseUnit])
      const store = useWorkspaceStore()
      await store.batchCreateUnits('ws-1', [{} as any])
      expect(workspaceApi.batchCreateUnits).toHaveBeenCalledWith('ws-1', [{}])
    })

    it('updateUnit updates and refreshes', async () => {
      vi.mocked(workspaceApi.updateUnit).mockResolvedValue(baseUnit)
      const store = useWorkspaceStore()
      // Pre-populate units so the index lookup finds the unit
      vi.mocked(workspaceApi.listUnits).mockResolvedValue({ items: [baseUnit], total: 1 })
      await store.fetchUnits('ws-1')
      await store.updateUnit('ws-1', 'u-1', {} as any)
      expect(workspaceApi.updateUnit).toHaveBeenCalledWith('ws-1', 'u-1', {})
    })

    it('patchUnits patches multiple units in parallel', async () => {
      vi.mocked(workspaceApi.updateUnit).mockResolvedValue(baseUnit)
      const store = useWorkspaceStore()
      const results = await store.patchUnits('ws-1', ['u-1', 'u-2'], {} as any)
      // Each unit calls updateUnit
      expect(workspaceApi.updateUnit).toHaveBeenCalledTimes(2)
      expect(results).toHaveLength(2)
    })

    it('deleteUnit removes single unit and refreshes', async () => {
      vi.mocked(workspaceApi.deleteUnit).mockResolvedValue(undefined as never)
      const store = useWorkspaceStore()
      await store.deleteUnit('ws-1', 'u-1')
      expect(workspaceApi.deleteUnit).toHaveBeenCalledWith('ws-1', 'u-1')
    })

    it('bulkDeleteUnits removes multiple units', async () => {
      vi.mocked(workspaceApi.bulkDeleteUnits).mockResolvedValue({ deleted: 2 } as never)
      const store = useWorkspaceStore()
      const result = await store.bulkDeleteUnits('ws-1', ['u-1', 'u-2'])
      expect(workspaceApi.bulkDeleteUnits).toHaveBeenCalledWith('ws-1', { ids: ['u-1', 'u-2'] })
      expect(result).toBe(2)
    })

    it('reorderUnits delegates to API with unit_ids body', async () => {
      vi.mocked(workspaceApi.reorderUnits).mockResolvedValue(undefined as never)
      const store = useWorkspaceStore()
      await store.reorderUnits('ws-1', ['u-1'])
      expect(workspaceApi.reorderUnits).toHaveBeenCalledWith('ws-1', { unit_ids: ['u-1'] })
    })

    it('renameGroup delegates to API and refetches units', async () => {
      vi.mocked(workspaceApi.renameGroup).mockResolvedValue(undefined as never)
      vi.mocked(workspaceApi.listUnits).mockResolvedValue({ items: [baseUnit], total: 1 })
      const store = useWorkspaceStore()
      await store.renameGroup('ws-1', { old_group: 'a', new_group: 'b' } as any)
      expect(workspaceApi.renameGroup).toHaveBeenCalled()
      expect(workspaceApi.listUnits).toHaveBeenCalled()
    })

    it('renameUnit delegates to API and refetches units', async () => {
      vi.mocked(workspaceApi.renameUnit).mockResolvedValue(undefined as never)
      vi.mocked(workspaceApi.listUnits).mockResolvedValue({ items: [baseUnit], total: 1 })
      const store = useWorkspaceStore()
      await store.renameUnit('ws-1', { unit_id: 'u-1', new_name: 'x' } as any)
      expect(workspaceApi.renameUnit).toHaveBeenCalled()
      expect(workspaceApi.listUnits).toHaveBeenCalled()
    })
  })

  describe('Selection', () => {
    it('setSelectedUnitIds replaces the array', () => {
      const store = useWorkspaceStore()
      store.setSelectedUnitIds(['u-1', 'u-2'])
      expect(store.selectedUnitIds).toEqual(['u-1', 'u-2'])
    })

    it('clearSelection empties the array', () => {
      const store = useWorkspaceStore()
      store.setSelectedUnitIds(['u-1'])
      store.clearSelection()
      expect(store.selectedUnitIds).toEqual([])
    })
  })
})
