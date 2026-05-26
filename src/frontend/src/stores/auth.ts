import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import { setToken } from '@/utils/tokenRef'
import type { UserInfo, LoginRequest, RegisterRequest } from '@/types'
import { clearAccessToken, getAccessToken } from '@/utils/session'
import { useStrategyStore } from '@/stores/strategy'
import { useBacktestStore } from '@/stores/backtest'
import { useSimulationStore } from '@/stores/simulation'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const refreshToken = ref<string | null>(null)
  const user = ref<UserInfo | null>(null)
  const initialized = ref(false)
  let initializePromise: Promise<void> | null = null

  const isAuthenticated = computed(() => !!token.value)

  async function login(data: LoginRequest) {
    const response = await authApi.login(data)
    token.value = response.access_token
    // Set token in interceptor immediately (no async storage race condition)
    setToken(response.access_token)
    initialized.value = false
    await fetchUser()
    initialized.value = true
  }

  async function register(data: RegisterRequest) {
    await authApi.register(data)
  }

  async function fetchUser() {
    if (!token.value) return
    try {
      user.value = await authApi.getMe()
    } catch {
      logout()
    }
  }

  async function initialize() {
    if (initialized.value) {
      return
    }
    if (initializePromise) {
      await initializePromise
      return
    }

    initializePromise = (async () => {
      // Migrate token from localStorage (old approach) to sessionStorage (new persistence)
      if (!token.value) {
        const legacyToken = getAccessToken()
        if (legacyToken) {
          token.value = legacyToken
          clearAccessToken() // Remove from localStorage after migration
        }
      }
      if (token.value) {
        setToken(token.value)
        await fetchUser()
      }
      initialized.value = true
    })()

    try {
      await initializePromise
    } finally {
      initializePromise = null
    }
  }

  function logout() {
    token.value = null
    refreshToken.value = null
    user.value = null
    initialized.value = true
    setToken(null)
    clearAccessToken() // Clear legacy localStorage token if present
    // Clear business store state so stale data doesn't persist after logout
    try {
      const strategyStore = useStrategyStore()
      strategyStore.strategies = []
      strategyStore.templates = []
      strategyStore.currentStrategy = null
      strategyStore.total = 0
      const backtestStore = useBacktestStore()
      backtestStore.results = []
      backtestStore.currentResult = null
      backtestStore.total = 0
      const simulationStore = useSimulationStore()
      simulationStore.instances = []
      simulationStore.total = 0
    } catch {
      // Store cleanup is best-effort; auth state is already cleared
    }
  }

  // 初始化时获取用户信息
  if (token.value) {
    void initialize()
  }

  return {
    token,
    refreshToken,
    user,
    initialized,
    isAuthenticated,
    login,
    register,
    fetchUser,
    initialize,
    logout,
  }
}, {
  persist: {
    storage: sessionStorage,
    paths: ['token', 'refreshToken'],
  },
})
