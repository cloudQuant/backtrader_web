/**
 * 数据导出工具
 *
 * 支持格式:
 * - CSV: 逗号分隔值，适合 Excel 导入
 * - JSON: 结构化数据，适合程序处理
 * - Excel: .xlsx 格式（已有）
 * - HTML: 可视化报告（已有）
 */

import type { BacktestResult, Strategy, TradeRecord } from '@/types'

/** Backtest-like record for export (API may include extra fields). */
type BacktestExportInput = Partial<BacktestResult> & Record<string, unknown>

export type ExportFormat = 'csv' | 'json' | 'excel' | 'html'

export interface ExportOptions {
  format?: ExportFormat
  filename?: string
  includeHeaders?: boolean
  dateFormat?: 'iso' | 'locale' | 'timestamp'
  numberFormat?: 'raw' | 'formatted'
}

/** Generic row type for CSV/JSON export (allow primitives and nested objects). */
export type ExportRow = Record<string, string | number | boolean | null | undefined | Date | unknown>

function protectCsvFormula(value: string): string {
  return /^[=+\-@\t\r]/.test(value) ? `'${value}` : value
}

function serializeCsvValue(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }

  const normalized = typeof value === 'string' ? protectCsvFormula(value) : String(value)
  if (normalized.includes(',') || normalized.includes('"') || normalized.includes('\n')) {
    return `"${normalized.replace(/"/g, '""')}"`
  }
  return normalized
}

/**
 * 将数据导出为 CSV
 */
export function exportToCSV<T extends object>(
  data: T[],
  options: ExportOptions = {}
): string {
  const {
    includeHeaders = true,
    dateFormat = 'iso',
    numberFormat = 'raw'
  } = options

  if (!data || data.length === 0) {
    return ''
  }

  // 获取所有列名
  const headers = Object.keys(data[0] as Record<string, unknown>)
  
  // 构建CSV行
  const rows: string[] = []
  
  // 添加表头
  if (includeHeaders) {
    rows.push(headers.join(','))
  }
  
  // 添加数据行
  data.forEach(item => {
    const itemRecord = item as Record<string, unknown>
    const values = headers.map(header => {
      let value = itemRecord[header]
      
      // 格式化日期
      if (value instanceof Date) {
        value = formatDate(value, dateFormat)
      }
      
      // 格式化数字
      if (typeof value === 'number') {
        value = numberFormat === 'formatted' 
          ? value.toLocaleString() 
          : value.toString()
      }
      
      // 处理对象和数组（转为JSON字符串）
      if (typeof value === 'object') {
        return serializeCsvValue(JSON.stringify(value))
      }

      return serializeCsvValue(value)
    })
    rows.push(values.join(','))
  })
  
  return rows.join('\n')
}

/**
 * 将数据导出为 JSON
 */
export function exportToJSON(
  data: unknown,
  options: ExportOptions = {}
): string {
  const {
    dateFormat = 'iso',
    numberFormat = 'raw'
  } = options

  // 深度处理数据
  const processedData = processDeepData(data, dateFormat, numberFormat)
  
  return JSON.stringify(processedData, null, 2)
}

/**
 * 深度处理数据（格式化日期和数字）
 */
function processDeepData(
  data: unknown,
  dateFormat: string,
  numberFormat: string
): unknown {
  if (data === null || data === undefined) {
    return data
  }
  
  // 处理数组
  if (Array.isArray(data)) {
    return data.map(item => processDeepData(item, dateFormat, numberFormat))
  }
  
  // 处理日期
  if (data instanceof Date) {
    return formatDate(data, dateFormat)
  }
  
  // 处理数字
  if (typeof data === 'number' && numberFormat === 'formatted') {
    return data.toLocaleString()
  }
  
  // 处理对象
  if (typeof data === 'object' && data !== null) {
    const dataRecord = data as Record<string, unknown>
    const processed: Record<string, unknown> = {}
    Object.keys(dataRecord).forEach(key => {
      processed[key] = processDeepData(dataRecord[key], dateFormat, numberFormat)
    })
    return processed
  }
  
  return data
}

/**
 * 格式化日期
 */
function formatDate(date: Date, format: string): string {
  switch (format) {
    case 'iso':
      return date.toISOString()
    case 'locale':
      return date.toLocaleString()
    case 'timestamp':
      return date.getTime().toString()
    default:
      return date.toISOString()
  }
}

/**
 * 下载文件
 */
export function downloadFile(
  content: string | Blob,
  filename: string,
  mimeType: string = 'text/plain'
): void {
  // 创建 Blob
  const blob = content instanceof Blob 
    ? content 
    : new Blob([content], { type: mimeType })
  
  // 创建下载链接
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  
  // 触发下载
  document.body.appendChild(link)
  link.click()
  
  // 清理
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * 导出回测结果
 */
export function exportBacktestResult(
  result: BacktestResult | BacktestExportInput,
  format: ExportFormat = 'json'
): void {
  const timestamp = new Date().toISOString().split('T')[0]
  const baseFilename = `backtest_result_${timestamp}`
  
  let content: string
  let filename: string
  let mimeType: string
  
  switch (format) {
    case 'csv': {
      // 扁平化数据用于 CSV
      const flatData = flattenBacktestResult(result)
      content = exportToCSV([flatData])
      filename = `${baseFilename}.csv`
      mimeType = 'text/csv'
      break
    }
    case 'json':
      content = exportToJSON(result)
      filename = `${baseFilename}.json`
      mimeType = 'application/json'
      break
      
    case 'excel':
      // Excel 导出需要使用专门的库（如 xlsx）
      throw new Error('Excel export requires xlsx library')
      
    case 'html':
      // HTML 导出已在其他模块实现
      throw new Error('HTML export is implemented separately')
      
    default:
      throw new Error(`Unsupported format: ${format}`)
  }
  
  downloadFile(content, filename, mimeType)
}

/**
 * 扁平化回测结果（用于 CSV 导出）
 */
function flattenBacktestResult(result: BacktestResult | BacktestExportInput): ExportRow {
  const resultRecord = result as Record<string, unknown>

  return {
    task_id: result.task_id,
    strategy_name: resultRecord.strategy_name,
    strategy_id: result.strategy_id,
    symbol: result.symbol,
    start_date: result.start_date,
    end_date: result.end_date,
    initial_cash: resultRecord.initial_cash,
    final_value: resultRecord.final_value,
    total_return: result.total_return,
    annual_return: result.annual_return,
    sharpe_ratio: result.sharpe_ratio,
    max_drawdown: result.max_drawdown,
    win_rate: result.win_rate,
    profit_factor: resultRecord.profit_factor,
    total_trades: result.total_trades,
    winning_trades: resultRecord.winning_trades ?? result.profitable_trades,
    losing_trades: result.losing_trades,
    avg_holding_period: resultRecord.avg_holding_period,
    metrics_source: resultRecord.metrics_source,
    created_at: result.created_at
  }
}

/**
 * 导出交易记录
 */
export function exportTrades(
  trades: TradeRecord[],
  format: ExportFormat = 'csv'
): void {
  const timestamp = new Date().toISOString().split('T')[0]
  const baseFilename = `trades_${timestamp}`
  
  let content: string
  let filename: string
  let mimeType: string
  
  switch (format) {
    case 'csv':
      content = exportToCSV(trades)
      filename = `${baseFilename}.csv`
      mimeType = 'text/csv'
      break
      
    case 'json':
      content = exportToJSON(trades)
      filename = `${baseFilename}.json`
      mimeType = 'application/json'
      break
      
    default:
      throw new Error(`Unsupported format: ${format}`)
  }
  
  downloadFile(content, filename, mimeType)
}

/** Strategy-like record for export (id and name required). */
type StrategyExportInput = (Strategy | Record<string, unknown>) & { id: string; name: string }

/**
 * 导出策略列表
 */
export function exportStrategies(
  strategies: StrategyExportInput[],
  format: ExportFormat = 'json'
): void {
  const timestamp = new Date().toISOString().split('T')[0]
  const baseFilename = `strategies_${timestamp}`
  
  let content: string
  let filename: string
  let mimeType: string
  
  // 移除代码字段（可选）
  const exportData = strategies.map(s => ({
    id: s.id,
    name: s.name,
    description: s.description,
    category: s.category,
    created_at: s.created_at,
    updated_at: s.updated_at
    // code: s.code  // 如果需要包含代码，取消注释
  }))
  
  switch (format) {
    case 'csv':
      content = exportToCSV(exportData)
      filename = `${baseFilename}.csv`
      mimeType = 'text/csv'
      break
      
    case 'json':
      content = exportToJSON(exportData)
      filename = `${baseFilename}.json`
      mimeType = 'application/json'
      break
      
    default:
      throw new Error(`Unsupported format: ${format}`)
  }
  
  downloadFile(content, filename, mimeType)
}

/**
 * 导出权益曲线数据
 */
export function exportEquityCurve(
  data: Array<{ date: string; value: number }>,
  format: ExportFormat = 'csv'
): void {
  const timestamp = new Date().toISOString().split('T')[0]
  const baseFilename = `equity_curve_${timestamp}`
  
  let content: string
  let filename: string
  let mimeType: string
  
  switch (format) {
    case 'csv':
      content = exportToCSV(data)
      filename = `${baseFilename}.csv`
      mimeType = 'text/csv'
      break
      
    case 'json':
      content = exportToJSON(data)
      filename = `${baseFilename}.json`
      mimeType = 'application/json'
      break
      
    default:
      throw new Error(`Unsupported format: ${format}`)
  }
  
  downloadFile(content, filename, mimeType)
}

/**
 * 批量导出（多格式）
 */
export function exportMultipleFormats<T>(
  data: T,
  formats: ExportFormat[],
  exporter: (data: T, format: ExportFormat) => void
): void {
  formats.forEach(format => {
    try {
      exporter(data, format)
    } catch {
      // Export failed for this format, continue with other formats
    }
  })
}

/**
 * 使用示例:
 * 
 * ```typescript
 * import { exportBacktestResult, exportToCSV, downloadFile } from '@/utils/exportUtils'
 * 
 * // 1. 导出回测结果为 JSON
 * exportBacktestResult(backtestResult, 'json')
 * 
 * // 2. 导出回测结果为 CSV
 * exportBacktestResult(backtestResult, 'csv')
 * 
 * // 3. 自定义数据导出
 * const customData = [
 *   { name: 'Strategy A', return: 0.25 },
 *   { name: 'Strategy B', return: 0.18 }
 * ]
 * const csvContent = exportToCSV(customData)
 * downloadFile(csvContent, 'custom_data.csv', 'text/csv')
 * 
 * // 4. 导出交易记录
 * exportTrades(trades, 'json')
 * 
 * // 5. 导出策略列表
 * exportStrategies(strategies, 'csv')
 * ```
 */
