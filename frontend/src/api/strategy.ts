import api from './index'
import type {
  Strategy,
  StrategyCreate,
  StrategyListResponse,
  StrategyTemplate,
} from '@/types'

export const strategyApi = {
  async create(data: StrategyCreate): Promise<Strategy> {
    return api.post('/strategy/', data)
  },

  async get(id: string): Promise<Strategy> {
    return api.get(`/strategy/${id}`)
  },

  async update(id: string, data: Partial<StrategyCreate>): Promise<Strategy> {
    return api.put(`/strategy/${id}`, data)
  },

  async delete(id: string): Promise<void> {
    return api.delete(`/strategy/${id}`)
  },

  async list(limit = 20, offset = 0, category?: string): Promise<StrategyListResponse> {
    return api.get('/strategy/', { params: { limit, offset, category } })
  },

  async getTemplates(): Promise<{ templates: StrategyTemplate[] }> {
    return api.get('/strategy/templates')
  },
}
