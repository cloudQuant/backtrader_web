/**
 * 全局快捷键支持
 * 
 * 功能:
 * - 运行回测: Ctrl/Cmd + Enter
 * - 保存策略: Ctrl/Cmd + S
 * - 切换暗色模式: Ctrl/Cmd + D
 * - 导航: 数字键 1-9
 * - 帮助: ?
 * - 搜索: Ctrl/Cmd + K
 * - 关闭对话框: Escape
 */

import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

export interface KeyboardShortcut {
  key: string
  ctrlKey?: boolean
  metaKey?: boolean
  shiftKey?: boolean
  altKey?: boolean
  description: string
  action: () => void
  preventDefault?: boolean
}

export function useKeyboardShortcuts() {
  const router = useRouter()
  const shortcuts: KeyboardShortcut[] = []

  /**
   * 注册快捷键
   */
  function registerShortcut(shortcut: KeyboardShortcut) {
    shortcuts.push(shortcut)
  }

  /**
   * 注销快捷键
   */
  function unregisterShortcut(key: string) {
    const index = shortcuts.findIndex(s => s.key === key)
    if (index !== -1) {
      shortcuts.splice(index, 1)
    }
  }

  /**
   * 处理键盘事件
   */
  function handleKeyDown(event: KeyboardEvent) {
    // 忽略在输入框中的快捷键（除了 Escape）
    const target = event.target as HTMLElement
    const isInputFocused = target.tagName === 'INPUT' || 
                          target.tagName === 'TEXTAREA' || 
                          target.isContentEditable

    // 查找匹配的快捷键
    const matchedShortcut = shortcuts.find(shortcut => {
      const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase()
      const ctrlMatch = shortcut.ctrlKey ? (event.ctrlKey || event.metaKey) : !event.ctrlKey
      const metaMatch = shortcut.metaKey ? event.metaKey : true
      const shiftMatch = shortcut.shiftKey ? event.shiftKey : !event.shiftKey
      const altMatch = shortcut.altKey ? event.altKey : !event.altKey

      return keyMatch && ctrlMatch && metaMatch && shiftMatch && altMatch
    })

    if (matchedShortcut) {
      // 在输入框中时，只响应 Escape
      if (isInputFocused && event.key !== 'Escape') {
        return
      }

      if (matchedShortcut.preventDefault !== false) {
        event.preventDefault()
      }
      matchedShortcut.action()
    }
  }

  /**
   * 设置全局快捷键
   */
  function setupGlobalShortcuts() {
    // 运行回测: Ctrl/Cmd + Enter
    registerShortcut({
      key: 'Enter',
      ctrlKey: true,
      description: '运行回测',
      action: () => {
        const runButton = document.querySelector('[data-shortcut="run-backtest"]') as HTMLButtonElement
        if (runButton && !runButton.disabled) {
          runButton.click()
          ElMessage.success('正在提交回测任务...')
        }
      }
    })

    // 保存策略: Ctrl/Cmd + S
    registerShortcut({
      key: 's',
      ctrlKey: true,
      description: '保存策略',
      action: () => {
        const saveButton = document.querySelector('[data-shortcut="save-strategy"]') as HTMLButtonElement
        if (saveButton && !saveButton.disabled) {
          saveButton.click()
          ElMessage.success('策略已保存')
        }
      }
    })

    // 切换暗色模式: Ctrl/Cmd + D
    registerShortcut({
      key: 'd',
      ctrlKey: true,
      description: '切换暗色模式',
      action: () => {
        const darkModeToggle = document.querySelector('[data-shortcut="toggle-dark-mode"]') as HTMLButtonElement
        if (darkModeToggle) {
          darkModeToggle.click()
        }
      }
    })

    // 导航 - 仪表盘: 1
    registerShortcut({
      key: '1',
      description: '导航到仪表盘',
      action: () => router.push('/')
    })

    // 导航 - 策略管理: 2
    registerShortcut({
      key: '2',
      description: '导航到策略管理',
      action: () => router.push('/strategy')
    })

    // 导航 - 回测: 3
    registerShortcut({
      key: '3',
      description: '导航到回测',
      action: () => router.push('/workspace')
    })

    // 导航 - 优化: 4
    registerShortcut({
      key: '4',
      description: '导航到参数优化',
      action: () => router.push('/optimization')
    })

    // 导航 - 实盘交易: 5
    registerShortcut({
      key: '5',
      description: '导航到实盘交易',
      action: () => router.push('/live-trading')
    })

    // 显示帮助: ?
    registerShortcut({
      key: '?',
      shiftKey: true,
      description: '显示快捷键帮助',
      action: () => showHelp()
    })

    // 全局搜索: Ctrl/Cmd + K
    registerShortcut({
      key: 'k',
      ctrlKey: true,
      description: '打开全局搜索',
      action: () => {
        const searchInput = document.querySelector('[data-shortcut="global-search"]') as HTMLInputElement
        if (searchInput) {
          searchInput.focus()
        }
      }
    })

    // 关闭对话框/返回: Escape
    registerShortcut({
      key: 'Escape',
      description: '关闭对话框或返回',
      action: () => {
        const closeButton = document.querySelector('.el-dialog__headerbtn') as HTMLButtonElement
        if (closeButton) {
          closeButton.click()
        } else {
          router.back()
        }
      }
    })
  }

  /**
   * 显示快捷键帮助
   */
  function showHelp() {
    const shortcutsList = shortcuts
      .filter(s => s.description)
      .map(s => {
        const keys = []
        if (s.ctrlKey) keys.push('Ctrl/Cmd')
        if (s.shiftKey) keys.push('Shift')
        if (s.altKey) keys.push('Alt')
        keys.push(s.key.toUpperCase())
        return `<div><kbd>${keys.join(' + ')}</kbd> - ${s.description}</div>`
      })
      .join('')

    ElMessage({
      dangerouslyUseHTMLString: true,
      message: `
        <div style="max-height: 400px; overflow-y: auto;">
          <h4 style="margin-bottom: 10px;">⌨️ 快捷键列表</h4>
          ${shortcutsList}
        </div>
      `,
      duration: 5000,
      type: 'info'
    })
  }

  /**
   * 获取所有快捷键列表（用于UI显示）
   */
  function getShortcutsList() {
    return shortcuts.filter(s => s.description)
  }

  onMounted(() => {
    setupGlobalShortcuts()
    window.addEventListener('keydown', handleKeyDown)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', handleKeyDown)
    shortcuts.length = 0
  })

  return {
    registerShortcut,
    unregisterShortcut,
    getShortcutsList,
    showHelp
  }
}

/**
 * 使用示例:
 * 
 * 在 App.vue 或 main.ts 中引入:
 * 
 * ```typescript
 * import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
 * 
 * export default {
 *   setup() {
 *     const { showHelp } = useKeyboardShortcuts()
 *     return { showHelp }
 *   }
 * }
 * ```
 * 
 * 在按钮上添加 data-shortcut 属性:
 * 
 * ```html
 * <el-button data-shortcut="run-backtest" @click="runBacktest">
 *   运行回测 (Ctrl+Enter)
 * </el-button>
 * ```
 */
