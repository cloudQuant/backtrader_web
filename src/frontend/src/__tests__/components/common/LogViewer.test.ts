import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

vi.mock('@/api/simulation', () => ({
  simulationApi: {
    listLogs: vi.fn().mockResolvedValue({ files: [{ name: 'run.log', size: 100 }] }),
    getLog: vi.fn().mockResolvedValue('2024-01-01 INFO hello\n2024-01-01 ERROR boom'),
    downloadLog: vi.fn().mockResolvedValue(undefined),
    clearLog: vi.fn().mockResolvedValue(undefined),
    clearAllLogs: vi.fn().mockResolvedValue(undefined),
  },
}))

import LogViewer from '@/components/common/LogViewer.vue'
import { simulationApi } from '@/api/simulation'
import { elStubs } from '@/test/stubs'

const api = simulationApi as unknown as Record<string, ReturnType<typeof vi.fn>>

function doMount() {
  return mount(LogViewer, {
    props: { instanceId: 'inst-1' },
    global: { stubs: elStubs },
  })
}

describe('LogViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads log files on mount and auto-selects the first', async () => {
    const wrapper = doMount()
    await new Promise(r => setTimeout(r, 0))
    expect(api.listLogs).toHaveBeenCalledWith('inst-1')
    expect((wrapper.vm as any).selectedFile).toBe('run.log')
  })

  it('viewerHeight defaults to 400 and respects the prop', () => {
    expect((doMount().vm as any).viewerHeight).toBe(400)
    const tall = mount(LogViewer, {
      props: { instanceId: 'inst-1', contentHeight: 800 },
      global: { stubs: elStubs },
    })
    expect((tall.vm as any).viewerHeight).toBe(800)
  })

  it('displayLines splits content on newlines', async () => {
    const vm = doMount().vm as any
    await new Promise(r => setTimeout(r, 0))
    vm.logContent = 'a\nb\nc'
    expect(vm.displayLines).toEqual(['a', 'b', 'c'])
  })

  it('formattedEntries parses each line into a formatted entry', async () => {
    const vm = doMount().vm as any
    vm.logContent = 'plain line'
    const entries = vm.formattedEntries
    expect(Array.isArray(entries)).toBe(true)
    expect(entries.length).toBe(1)
  })

  it('onFileChange reloads the log', async () => {
    const vm = doMount().vm as any
    await new Promise(r => setTimeout(r, 0))
    api.getLog.mockClear()
    vm.selectedFile = 'run.log'
    vm.onFileChange()
    await new Promise(r => setTimeout(r, 0))
    expect(api.getLog).toHaveBeenCalled()
  })

  it('downloadLog invokes the download API when a file is selected', async () => {
    const vm = doMount().vm as any
    await new Promise(r => setTimeout(r, 0))
    vm.selectedFile = 'run.log'
    await vm.downloadLog()
    expect(api.downloadLog).toHaveBeenCalledWith('inst-1', 'run.log')
  })
})
