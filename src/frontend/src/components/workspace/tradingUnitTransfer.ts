import type { GatewayConfig, StrategyUnit, StrategyUnitCreate, TradingMode, TradingSnapshot } from '@/types/workspace'

type TransferableUnit = {
  group_name?: string | null
  strategy_id?: string | null
  strategy_name?: string | null
  symbol?: string | null
  symbol_name?: string | null
  timeframe?: string | null
  timeframe_n?: number | null
  category?: string | null
  data_config?: Record<string, unknown> | null
  unit_settings?: Record<string, unknown> | null
  params?: Record<string, unknown> | null
  optimization_config?: Record<string, unknown> | null
  trading_mode?: TradingMode | null
  gateway_config?: GatewayConfig | Record<string, unknown> | null
  lock_trading?: boolean | null
  lock_running?: boolean | null
  trading_snapshot?: Partial<TradingSnapshot> | null
} | Partial<StrategyUnitCreate> | Partial<StrategyUnit>

interface NormalizeOptions {
  includeTradingFields?: boolean
  defaultTradingMode?: TradingMode
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? { ...(value as Record<string, unknown>) } : {}
}

export function buildTransferUnitPayload(
  unit: TransferableUnit,
  options: NormalizeOptions = {},
): StrategyUnitCreate {
  const includeTradingFields = options.includeTradingFields !== false
  const defaultTradingMode = options.defaultTradingMode ?? 'paper'

  const payload: StrategyUnitCreate = {
    group_name: unit.group_name || '',
    strategy_id: unit.strategy_id || '',
    strategy_name: unit.strategy_name || '',
    symbol: unit.symbol || '',
    symbol_name: unit.symbol_name || '',
    timeframe: unit.timeframe || '1d',
    timeframe_n: Number(unit.timeframe_n || 1),
    category: unit.category || '',
    data_config: asObject(unit.data_config),
    unit_settings: asObject(unit.unit_settings),
    params: asObject(unit.params),
    optimization_config: asObject(unit.optimization_config),
  }

  if (includeTradingFields) {
    payload.trading_mode = unit.trading_mode || defaultTradingMode
    payload.gateway_config = asObject(unit.gateway_config)
    payload.lock_trading = Boolean(unit.lock_trading)
    payload.lock_running = Boolean(unit.lock_running)
  }

  return payload
}

export function normalizeTransferUnits(
  units: unknown[],
  options: NormalizeOptions = {},
): StrategyUnitCreate[] {
  return units
    .filter(unit => unit && typeof unit === 'object')
    .map(unit => buildTransferUnitPayload(unit as TransferableUnit, options))
    .filter(unit => Boolean(unit.strategy_id || unit.strategy_name || unit.symbol))
}

export function downloadTransferUnits(units: StrategyUnitCreate[], filenamePrefix: string): void {
  const blob = new Blob([JSON.stringify(units, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${filenamePrefix}_${new Date().toISOString().slice(0, 10)}.json`
  link.click()
  URL.revokeObjectURL(url)
}
