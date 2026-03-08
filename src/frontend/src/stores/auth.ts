import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { UserInfo, LoginRequest, RegisterRequest } from '@/types'
import { clearAccessToken, getAccessToken, setAccessToken } from '@/utils/session'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(getAccessToken())
  const user = ref<UserInfo | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  async function login(data: LoginRequest) {
    const response = await authApi.login(data)
    token.value = response.access_token
    setAccessToken(response.access_token)
    await fetchUser()
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

  function logout() {
    token.value = null
    user.value = null
    clearAccessToken()
  }

  // 初始化时获取用户信息
  if (token.value) {
    fetchUser()
  }

  return {
    token,
    user,
    isAuthenticated,
    login,
    register,
    fetchUser,
    logout,
  }
})
