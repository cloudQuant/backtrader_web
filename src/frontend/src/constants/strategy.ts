/**
 * Shared constants for strategy/backtest status and category display.
 */

import i18n from '@/i18n'

function tt(key: string): string {
  return i18n.global.t(key)
}

/** Element Plus component type union. */
export type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

/** Map backtest/task status to Element Plus tag type. */
export const STATUS_TYPE_MAP: Record<string, TagType> = {
  completed: 'success',
  running: 'warning',
  pending: 'info',
  failed: 'danger',
  cancelled: 'warning',
}

/** Map strategy category to Element Plus tag type. */
export const CATEGORY_TYPE_MAP: Record<string, TagType> = {
  trend: 'info',
  mean_reversion: 'success',
  volatility: 'warning',
  indicator: 'info',
  arbitrage: 'danger',
  custom: 'info',
}

export function getStatusType(status: string): TagType {
  return STATUS_TYPE_MAP[status] || 'info'
}

export function getStatusText(status: string): string {
  switch (status) {
    case 'completed':
      return tt('strategyConst.statusCompleted')
    case 'running':
      return tt('strategyConst.statusRunning')
    case 'pending':
      return tt('strategyConst.statusPending')
    case 'failed':
      return tt('strategyConst.statusFailed')
    case 'cancelled':
      return tt('strategyConst.statusCancelled')
    default:
      return status
  }
}

export function getCategoryType(category: string): TagType {
  return CATEGORY_TYPE_MAP[category] || 'info'
}

export function getCategoryLabel(category: string): string {
  switch (category) {
    case 'trend':
      return tt('strategyConst.catTrend')
    case 'mean_reversion':
      return tt('strategyConst.catMeanReversion')
    case 'volatility':
      return tt('strategyConst.catVolatility')
    case 'indicator':
      return tt('strategyConst.catIndicator')
    case 'arbitrage':
      return tt('strategyConst.catArbitrage')
    case 'custom':
      return tt('strategyConst.catCustom')
    default:
      return category
  }
}
