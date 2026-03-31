import api from './index'
import type { UserInfo, LoginRequest, RegisterRequest, Token } from '@/types'

export const authApi = {
  async login(data: LoginRequest): Promise<Token> {
    return api.post<Token, LoginRequest>('/auth/login', data)
  },

  async register(data: RegisterRequest): Promise<UserInfo> {
    return api.post<UserInfo, RegisterRequest>('/auth/register', data)
  },

  async getMe(): Promise<UserInfo> {
    return api.get<UserInfo>('/auth/me')
  },
}
