/**
 * Global keyboard shortcuts.
 *
 * Features:
 * - Run backtest: Ctrl/Cmd + Enter
 * - Save strategy: Ctrl/Cmd + S
 * - Toggle dark mode: Ctrl/Cmd + D
 * - Navigation: number keys 1-9
 * - Help: ?
 * - Search: Ctrl/Cmd + K
 * - Close dialog: Escape
 */

import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import i18n from '@/i18n'

function tt(key: string): string {
  return i18n.global.t(key)
}

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

  /** Register a shortcut. */
  function registerShortcut(shortcut: KeyboardShortcut) {
    shortcuts.push(shortcut)
  }

  /** Unregister a shortcut by key. */
  function unregisterShortcut(key: string) {
    const index = shortcuts.findIndex(s => s.key === key)
    if (index !== -1) {
      shortcuts.splice(index, 1)
    }
  }

  /** Handle keyboard events. */
  function handleKeyDown(event: KeyboardEvent) {
    // Ignore shortcuts in input fields (except Escape)
    const target = event.target as HTMLElement
    const isInputFocused = target.tagName === 'INPUT' ||
                          target.tagName === 'TEXTAREA' ||
                          target.isContentEditable

    // Find matching shortcut
    const matchedShortcut = shortcuts.find(shortcut => {
      const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase()
      const ctrlMatch = shortcut.ctrlKey ? (event.ctrlKey || event.metaKey) : !event.ctrlKey
      const metaMatch = shortcut.metaKey ? event.metaKey : true
      const shiftMatch = shortcut.shiftKey ? event.shiftKey : !event.shiftKey
      const altMatch = shortcut.altKey ? event.altKey : !event.altKey

      return keyMatch && ctrlMatch && metaMatch && shiftMatch && altMatch
    })

    if (matchedShortcut) {
      // When in an input, only respond to Escape
      if (isInputFocused && event.key !== 'Escape') {
        return
      }

      if (matchedShortcut.preventDefault !== false) {
        event.preventDefault()
      }
      matchedShortcut.action()
    }
  }

  /** Set up the global shortcuts. */
  function setupGlobalShortcuts() {
    // Run backtest: Ctrl/Cmd + Enter
    registerShortcut({
      key: 'Enter',
      ctrlKey: true,
      description: tt('kbShortcuts.descRunBacktest'),
      action: () => {
        const runButton = document.querySelector('[data-shortcut="run-backtest"]') as HTMLButtonElement
        if (runButton && !runButton.disabled) {
          runButton.click()
          ElMessage.success(tt('kbShortcuts.msgRunningBacktest'))
        }
      }
    })

    // Save strategy: Ctrl/Cmd + S
    registerShortcut({
      key: 's',
      ctrlKey: true,
      description: tt('kbShortcuts.descSaveStrategy'),
      action: () => {
        const saveButton = document.querySelector('[data-shortcut="save-strategy"]') as HTMLButtonElement
        if (saveButton && !saveButton.disabled) {
          saveButton.click()
          ElMessage.success(tt('kbShortcuts.msgStrategySaved'))
        }
      }
    })

    // Toggle dark mode: Ctrl/Cmd + D
    registerShortcut({
      key: 'd',
      ctrlKey: true,
      description: tt('kbShortcuts.descToggleDarkMode'),
      action: () => {
        const darkModeToggle = document.querySelector('[data-shortcut="toggle-dark-mode"]') as HTMLButtonElement
        if (darkModeToggle) {
          darkModeToggle.click()
        }
      }
    })

    // Navigate to dashboard: 1
    registerShortcut({
      key: '1',
      description: tt('kbShortcuts.descNavDashboard'),
      action: () => router.push('/')
    })

    // Navigate to strategy management: 2
    registerShortcut({
      key: '2',
      description: tt('kbShortcuts.descNavStrategy'),
      action: () => router.push('/strategy')
    })

    // Navigate to backtest: 3
    registerShortcut({
      key: '3',
      description: tt('kbShortcuts.descNavBacktest'),
      action: () => router.push('/workspace')
    })

    // Navigate to live trading: 5
    registerShortcut({
      key: '5',
      description: tt('kbShortcuts.descNavLiveTrading'),
      action: () => router.push('/live-trading')
    })

    // Show help: ?
    registerShortcut({
      key: '?',
      shiftKey: true,
      description: tt('kbShortcuts.descHelpKey'),
      action: () => showHelp()
    })

    // Global search: Ctrl/Cmd + K
    registerShortcut({
      key: 'k',
      ctrlKey: true,
      description: tt('kbShortcuts.descGlobalSearch'),
      action: () => {
        const searchInput = document.querySelector('[data-shortcut="global-search"]') as HTMLInputElement
        if (searchInput) {
          searchInput.focus()
        }
      }
    })

    // Close dialog / back: Escape
    registerShortcut({
      key: 'Escape',
      description: tt('kbShortcuts.descCloseDialog'),
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

  /** Display the keyboard shortcuts help message. */
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
          <h4 style="margin-bottom: 10px;">${tt('kbShortcuts.helpHeading')}</h4>
          ${shortcutsList}
        </div>
      `,
      duration: 5000,
      type: 'info'
    })
  }

  /** Get the registered shortcuts list (for UI display). */
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
 * Usage example:
 *
 * In App.vue or main.ts:
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
 * Add a data-shortcut attribute to a button:
 *
 * ```html
 * <el-button data-shortcut="run-backtest" @click="runBacktest">
 *   Run backtest (Ctrl+Enter)
 * </el-button>
 * ```
 */
