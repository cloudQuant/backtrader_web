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
    getDataURL: vi.fn(() => 'data:image/png;base64,mock'),
  }

  return {
    default: {
      init: vi.fn(() => mockChart),
      connect: vi.fn(),
      disconnect: vi.fn(),
      dispose: vi.fn(),
    },
    init: vi.fn(() => mockChart),
    connect: vi.fn(),
    disconnect: vi.fn(),
    dispose: vi.fn(),
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

// Mock Element Plus icons - comprehensive list
vi.mock('@element-plus/icons-vue', () => {
  const names = [
    'Download', 'Upload', 'Plus', 'Delete', 'Edit', 'Search', 'Refresh',
    'DataLine', 'Document', 'Grid', 'TrendCharts', 'Trophy', 'Loading',
    'VideoPlay', 'VideoPause', 'Close', 'Check', 'Warning', 'InfoFilled',
    'SuccessFilled', 'CircleCloseFilled', 'ArrowDown', 'ArrowUp', 'ArrowLeft',
    'ArrowRight', 'Setting', 'User', 'Lock', 'View', 'Hide', 'More',
    'Menu', 'Star', 'StarFilled', 'Timer', 'Clock', 'Calendar',
    'Connection', 'Promotion', 'List', 'Histogram', 'PieChart',
    'Monitor', 'Stopwatch', 'Switch', 'SwitchButton', 'Tickets',
    'CircleCheck', 'CirclePlus', 'Remove', 'ZoomIn', 'ZoomOut',
    'FullScreen', 'CopyDocument', 'DocumentCopy', 'Sort', 'SortDown', 'SortUp',
    'Folder', 'FolderOpened', 'Picture', 'Link', 'Position', 'Odometer',
    'ChatDotRound', 'Bell', 'QuestionFilled', 'Back', 'Right', 'Top', 'Bottom',
  ]
  const result: Record<string, any> = {}
  for (const n of names) {
    result[n] = { name: n, render: () => null }
  }
  return result
})
