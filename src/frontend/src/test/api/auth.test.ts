import { describe, it, expect, vi, beforeEach } from 'vitest'
import { authApi } from '@/api/auth'
import api from '@/api/index'

vi.mock('@/api/index', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

describe('authApi', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('login calls POST /auth/login', async () => {
    const mockToken = { access_token: 'tok', token_type: 'bearer' }
    vi.mocked(api.post).mockResolvedValue(mockToken)
    const result = await authApi.login({ username: 'u', password: 'p' })
    expect(api.post).toHaveBeenCalledWith('/auth/login', { username: 'u', password: 'p' })
    expect(result).toEqual(mockToken)
  })

  it('register calls POST /auth/register', async () => {
    const mockUser = { id: '1', username: 'u', email: 'e@e.com' }
    vi.mocked(api.post).mockResolvedValue(mockUser)
    const result = await authApi.register({ username: 'u', email: 'e@e.com', password: 'p' })
    expect(api.post).toHaveBeenCalledWith('/auth/register', { username: 'u', email: 'e@e.com', password: 'p' })
    expect(result).toEqual(mockUser)
  })

  it('getMe calls GET /auth/me', async () => {
    const mockUser = { id: '1', username: 'u', email: 'e@e.com' }
    vi.mocked(api.get).mockResolvedValue(mockUser)
    const result = await authApi.getMe()
    expect(api.get).toHaveBeenCalledWith('/auth/me')
    expect(result).toEqual(mockUser)
  })
})
