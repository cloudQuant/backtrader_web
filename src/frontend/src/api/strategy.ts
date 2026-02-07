import api from './index'
import type {
  Strategy,
  StrategyCreate,
  StrategyListResponse,
  StrategyTemplate,
  StrategyConfig,
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

  async getTemplates(category?: string): Promise<{ templates: StrategyTemplate[]; total: number }> {
    return api.get('/strategy/templates', { params: { category } })
  },

  async getTemplateDetail(id: string): Promise<StrategyTemplate> {
    return api.get(`/strategy/templates/${id}`)
  },

  async getTemplateReadme(id: string): Promise<{ template_id: string; content: string }> {
    return api.get(`/strategy/templates/${id}/readme`)
  },

  async getTemplateConfig(id: string): Promise<StrategyConfig> {
    return api.get(`/strategy/templates/${id}/config`)
  },
}
