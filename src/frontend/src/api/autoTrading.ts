/**
 * 自动交易调度 API
 */
import request from './index'

export interface AutoTradingSession {
  name: string
  open: string
  close: string
}

export interface AutoTradingConfig {
  enabled: boolean
  buffer_minutes: number
  sessions: AutoTradingSession[]
  scope: string
}

export interface ScheduleItem {
  session: string
  start: string
  stop: string
}

export interface AutoTradingScheduleResponse {
  schedule: ScheduleItem[]
  config: AutoTradingConfig
}

export const autoTradingApi = {
  getConfig(): Promise<AutoTradingConfig> {
    return request.get('/auto-trading/config')
  },

  updateConfig(data: Partial<AutoTradingConfig>): Promise<AutoTradingConfig> {
    return request.put('/auto-trading/config', data)
  },

  getSchedule(): Promise<AutoTradingScheduleResponse> {
    return request.get('/auto-trading/schedule')
  },
}
