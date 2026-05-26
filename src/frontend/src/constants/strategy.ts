/**
 * Shared constants for strategy/backtest status and category display.
 */

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

/** Map backtest/task status to Chinese label. */
export const STATUS_TEXT_MAP: Record<string, string> = {
  completed: '完成',
  running: '运行中',
  pending: '等待中',
  failed: '失败',
  cancelled: '已取消',
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

/** Map strategy category to Chinese label. */
export const CATEGORY_LABEL_MAP: Record<string, string> = {
  trend: '趋势',
  mean_reversion: '均值回归',
  volatility: '波动率',
  indicator: '指标',
  arbitrage: '套利',
  custom: '其他',
}

export function getStatusType(status: string): TagType {
  return STATUS_TYPE_MAP[status] || 'info'
}

export function getStatusText(status: string): string {
  return STATUS_TEXT_MAP[status] || status
}

export function getCategoryType(category: string): TagType {
  return CATEGORY_TYPE_MAP[category] || 'info'
}

export function getCategoryLabel(category: string): string {
  return CATEGORY_LABEL_MAP[category] || category
}
