/**
 * Vitest 测试设置文件
 * 在所有测试运行前执行
 */
import { vi } from 'vitest'

// Mock echarts
vi.mock('echarts', () => {
  const mockChart = {
    setOption: vi.fn(),
    dispose: vi.fn(),
    resize: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    getOption: vi.fn(),
    clear: vi.fn(),
  }

  return {
    default: {
      init: vi.fn(() => mockChart),
      connect: vi.fn(),
      disconnect: vi.fn(),
      dispose: vi.fn(),
    },
    graphic: {
      LinearGradient: vi.fn(() => ({
        color: vi.fn(),
        x: vi.fn(),
        y: vi.fn(),
        x2: vi.fn(),
        y2: vi.fn(),
      })),
    },
  }
})

// Mock Element Plus icons
vi.mock('@element-plus/icons-vue', () => ({
  Download: { name: 'Download', template: '<span>download</span>' },
  Upload: { name: 'Upload', template: '<span>upload</span>' },
  Plus: { name: 'Plus', template: '<span>plus</span>' },
  Delete: { name: 'Delete', template: '<span>delete</span>' },
  Edit: { name: 'Edit', template: '<span>edit</span>' },
  Search: { name: 'Search', template: '<span>search</span>' },
  Refresh: { name: 'Refresh', template: '<span>refresh</span>' },
}))
