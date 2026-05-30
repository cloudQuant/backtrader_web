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
vi.mock('vue-router', () => ({
  useRoute: () => ({ meta: { workspaceType: 'research' }, path: '/workspace' }),
  useRouter: () => ({ push }),
}))

vi.mock('@/api/index', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getErrorMessage: (_e: unknown, fallback: string) => fallback,
}))

const fetchWorkspaces = vi.fn().mockResolvedValue(undefined)
const deleteWorkspace = vi.fn().mockResolvedValue(undefined)
vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({
    workspaces: [{ id: 'w-1', name: 'A' }],
    total: 1,
    loading: false,
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
  })

  it('fetches research workspaces on mount via the workspaceType watcher', async () => {
    doMount()
    await new Promise(r => setTimeout(r, 0))
    expect(fetchWorkspaces).toHaveBeenCalledWith(0, 50, 'research')
  })

  it('statusTagType maps known statuses', () => {
    const vm = doMount().vm as any
    expect(vm.statusTagType('running')).toBe('warning')
    expect(vm.statusTagType('completed')).toBe('success')
    expect(vm.statusTagType('error')).toBe('danger')
    expect(vm.statusTagType('???')).toBe('info')
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
    expect(push).toHaveBeenCalledWith('/workspace/w-9')
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
