/** Workspace-based paper runtime API client. */

import request from './index'

export interface PaperEquityPoint {
  id: string
  observed_at: string
  source: string
  total_equity: number
  cash: number
  position_value: number
  unrealized_pnl: number
  realized_pnl: number
}

export interface PaperRuntimeDetail {
  instance_id: string
  workspace_id: string
  unit_id: string
  workspace_name: string
  unit_name: string
  symbol: string
  status: string
  paused: boolean
  positions: Record<string, unknown>[]
  orders: Record<string, unknown>[]
  trades: Record<string, unknown>[]
  signals: Record<string, unknown>[]
  latest_equity: PaperEquityPoint | null
}

export interface PaperRuntimeAlert {
  id: string
  alert_type: string
  severity: string
  status: string
  title: string
  message: string
  instance_id?: string | null
  workspace_id?: string | null
  unit_id?: string | null
  created_at?: string | null
}

export interface RiskRule {
  id: string
  user_id: string
  name: string
  rule_type: string
  config: Record<string, unknown>
  severity: 'info' | 'warning' | 'error' | 'critical'
  workspace_id?: string | null
  unit_id?: string | null
  instance_id?: string | null
  paper_account_id?: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface RiskRuleCreate {
  name: string
  rule_type: string
  config?: Record<string, unknown>
  severity?: RiskRule['severity']
  workspace_id?: string
  unit_id?: string
  instance_id?: string
  paper_account_id?: string
}

const BASE = '/paper-runtimes'

export const paperRuntimeApi = {
  get(instanceId: string): Promise<PaperRuntimeDetail> {
    return request.get(`${BASE}/${instanceId}`)
  },

  getEquity(instanceId: string, maxPoints = 500): Promise<{ points: PaperEquityPoint[], sampled: boolean, sampling: string, next_cursor?: string | null }> {
    return request.get(`${BASE}/${instanceId}/equity`, { params: { max_points: maxPoints } })
  },

  getAlerts(instanceId: string): Promise<PaperRuntimeAlert[]> {
    return request.get(`${BASE}/${instanceId}/alerts`)
  },

  pause(instanceId: string): Promise<{ paused: boolean }> {
    return request.post(`${BASE}/${instanceId}/pause`)
  },

  decideHandoff(
    instanceId: string,
    data: { decision: 'approved' | 'rejected' | 'requested_changes', rationale?: string, checklist?: Record<string, unknown> },
  ): Promise<{ id: string, decision: string }> {
    return request.post(`${BASE}/${instanceId}/handoff-decisions`, data)
  },

  listRules(instanceId?: string): Promise<RiskRule[]> {
    return request.get(`${BASE}/risk-rules/`, { params: { instance_id: instanceId } })
  },

  createRule(data: RiskRuleCreate): Promise<RiskRule> {
    return request.post(`${BASE}/risk-rules/`, data)
  },

  updateRule(id: string, data: Partial<Pick<RiskRule, 'name' | 'config' | 'severity' | 'is_active'>>): Promise<RiskRule> {
    return request.patch(`${BASE}/risk-rules/${id}`, data)
  },
}
