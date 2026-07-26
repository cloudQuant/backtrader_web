import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

const push = vi.fn()
const routeState = vi.hoisted(() => ({
  meta: { workspaceType: 'research' as 'research' | 'trading' },
  path: '/workspace',
}))
vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push }),
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

const fetchWorkspaces = vi.fn().mockResolvedValue(undefined)
const deleteWorkspace = vi.fn().mockResolvedValue(undefined)
const storeState = vi.hoisted(() => ({
  workspaces: [
    {
      id: 'w-1',
      user_id: 'u-1',
      name: 'A',
      description: 'Alpha workspace',
      workspace_type: 'research',
      settings: {},
      trading_config: {},
      unit_count: 3,
      completed_count: 2,
      status: 'running',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-02T00:00:00Z',
    },
    {
      id: 'w-2',
      user_id: 'u-1',
      name: 'B',
      description: 'Beta workspace',
      workspace_type: 'research',
      settings: {},
      trading_config: {},
      unit_count: 0,
      completed_count: 0,
      status: 'idle',
      created_at: '2024-01-03T00:00:00Z',
      updated_at: '2024-01-04T00:00:00Z',
    },
  ],
  total: 2,
  loading: false,
}))
vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({
    ...storeState,
    fetchWorkspaces,
    deleteWorkspace,
  }),
}))

import { ElMessage } from 'element-plus'

import WorkspaceListPage from '@/views/workspace/WorkspaceListPage.vue'
import { elStubs } from '@/test/stubs'

function doMount() {
  return mount(WorkspaceListPage, {
    global: {
      stubs: {
        ...elStubs,
        CreateWorkspaceDialog: true,
        WorkspaceCard: true,
      },
    },
  })
}

describe('WorkspaceListPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    routeState.meta.workspaceType = 'research'
    routeState.path = '/workspace'
    storeState.total = 2
    storeState.loading = false
    storeState.workspaces = storeState.workspaces.map(workspace => ({
      ...workspace,
      workspace_type: routeState.meta.workspaceType,
    }))
  })

  it('fetches research workspaces on mount via the workspaceType watcher', async () => {
    doMount()
    await new Promise(r => setTimeout(r, 0))
    expect(fetchWorkspaces).toHaveBeenCalledWith(0, 50, 'research')
  })

  it('statusTone maps known statuses', () => {
    const vm = doMount().vm as any
    expect(vm.statusTone('running')).toBe('running')
    expect(vm.statusTone('completed')).toBe('completed')
    expect(vm.statusTone('error')).toBe('error')
    expect(vm.statusTone('???')).toBe('idle')
  })

  it('statusLabel maps known statuses and falls back to the raw value', () => {
    const vm = doMount().vm as any
    expect(vm.statusLabel('idle')).toBe('workspace.statusIdle')
    expect(vm.statusLabel('mystery')).toBe('mystery')
  })

  it('formatTime returns empty for falsy and a string otherwise', () => {
    const vm = doMount().vm as any
    expect(vm.formatTime('')).toBe('')
    expect(typeof vm.formatTime('2024-01-01T00:00:00Z')).toBe('string')
  })

  it('workspaceType + emptyDescription reflect the route meta', () => {
    const vm = doMount().vm as any
    expect(vm.workspaceType).toBe('research')
    expect(vm.emptyDescription).toBe('workspace.emptyResearch')
  })

  it('shows the first-run research workflow and opens workspace creation from its action', async () => {
    storeState.workspaces = []
    storeState.total = 0
    const wrapper = doMount()

    expect(wrapper.find('[data-test="research-workflow-guide"]').exists()).toBe(true)
    await wrapper.find('[data-test="research-workflow-guide"] button').trigger('click')
    expect((wrapper.vm as any).showCreateDialog).toBe(true)
  })

  it('renders trading operations summary and fetches trading workspaces for trading routes', async () => {
    routeState.meta.workspaceType = 'trading'
    routeState.path = '/trading/workspaces'
    storeState.workspaces = [
      {
        ...storeState.workspaces[0],
        workspace_type: 'trading',
        status: 'running',
        unit_count: 4,
        completed_count: 3,
      },
      {
        ...storeState.workspaces[1],
        workspace_type: 'trading',
        status: 'error',
        unit_count: 2,
        completed_count: 0,
      },
    ]
    storeState.total = 2

    const wrapper = doMount()
    await new Promise(r => setTimeout(r, 0))
    const vm = wrapper.vm as any

    expect(fetchWorkspaces).toHaveBeenCalledWith(0, 50, 'trading')
    expect(vm.workspaceType).toBe('trading')
    expect(vm.emptyDescription).toBe('workspace.emptyTrading')
    expect(wrapper.find('[data-test="trading-ops-panel"]').exists()).toBe(true)
    expect(vm.tradingCompletionRate).toBe(50)
    expect(vm.workspaceReadinessLabel(storeState.workspaces[0])).toBe('workspace.tradingReadinessPartial')
    expect(vm.workspaceReadinessLabel(storeState.workspaces[1])).toBe('workspace.tradingReadinessReview')
  })

  it('toggleSelect adds then removes an id', () => {
    const vm = doMount().vm as any
    vm.toggleSelect('w-1')
    expect(vm.selectedIds).toContain('w-1')
    vm.toggleSelect('w-1')
    expect(vm.selectedIds).not.toContain('w-1')
  })

  it('onTableSelectionChange syncs selectedIds from rows', () => {
    const vm = doMount().vm as any
    vm.onTableSelectionChange([{ id: 'w-1' }, { id: 'w-2' }])
    expect(vm.selectedIds).toEqual(['w-1', 'w-2'])
  })

  it('goToDetail routes to the research workspace path', () => {
    const vm = doMount().vm as any
    vm.goToDetail('w-9')
    expect(push).toHaveBeenCalledWith('/research/workspaces/w-9')
  })

  it('goToDetail routes trading workspaces to trading detail paths', () => {
    routeState.meta.workspaceType = 'trading'
    routeState.path = '/trading/workspaces'
    const vm = doMount().vm as any
    vm.goToDetail('w-9')
    expect(push).toHaveBeenCalledWith('/trading/w-9')
  })

  it('handleEdit opens the dialog with the editing workspace', () => {
    const vm = doMount().vm as any
    vm.handleEdit({ id: 'w-1', name: 'A' })
    expect(vm.showCreateDialog).toBe(true)
    expect(vm.editingWorkspace?.id).toBe('w-1')
  })

  it('handleDelete confirms and deletes', async () => {
    const vm = doMount().vm as any
    await vm.handleDelete({ id: 'w-1', name: 'A' })
    expect(deleteWorkspace).toHaveBeenCalledWith('w-1')
    expect(ElMessage.success).toHaveBeenCalled()
  })

  it('onSaved closes dialog and refetches', () => {
    const vm = doMount().vm as any
    vm.showCreateDialog = true
    vm.onSaved()
    expect(vm.showCreateDialog).toBe(false)
    expect(fetchWorkspaces).toHaveBeenCalled()
  })
})
