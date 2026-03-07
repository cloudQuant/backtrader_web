/**
 * 数据导出工具
 * 
 * 支持格式:
 * - CSV: 逗号分隔值，适合 Excel 导入
 * - JSON: 结构化数据，适合程序处理
 * - Excel: .xlsx 格式（已有）
 * - HTML: 可视化报告（已有）
 */

export type ExportFormat = 'csv' | 'json' | 'excel' | 'html'

export interface ExportOptions {
  format: ExportFormat
  filename?: string
  includeHeaders?: boolean
  dateFormat?: 'iso' | 'locale' | 'timestamp'
  numberFormat?: 'raw' | 'formatted'
}

/**
 * 将数据导出为 CSV
 */
export function exportToCSV(
  data: Record<string, any>[],
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
  const headers = Object.keys(data[0])
  
  // 构建CSV行
  const rows: string[] = []
  
  // 添加表头
  if (includeHeaders) {
    rows.push(headers.join(','))
  }
  
  // 添加数据行
  data.forEach(item => {
    const values = headers.map(header => {
      let value = item[header]
      
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
      
      // 处理字符串（转义逗号和引号）
      if (typeof value === 'string') {
        // 如果包含逗号、引号或换行，需要用引号包裹
        if (value.includes(',') || value.includes('"') || value.includes('\n')) {
          value = `"${value.replace(/"/g, '""')}"`
        }
      }
      
      // 处理 null/undefined
      if (value === null || value === undefined) {
        value = ''
      }
      
      // 处理对象和数组（转为JSON字符串）
      if (typeof value === 'object') {
        value = `"${JSON.stringify(value).replace(/"/g, '""')}"`
      }
      
      return value
    })
    rows.push(values.join(','))
  })
  
  return rows.join('\n')
}

/**
 * 将数据导出为 JSON
 */
export function exportToJSON(
  data: Record<string, any>[] | Record<string, any>,
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
  data: any,
  dateFormat: string,
  numberFormat: string
): any {
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
  if (typeof data === 'object') {
    const processed: Record<string, any> = {}
    Object.keys(data).forEach(key => {
      processed[key] = processDeepData(data[key], dateFormat, numberFormat)
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
  result: any,
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
function flattenBacktestResult(result: any): Record<string, any> {
  return {
    task_id: result.task_id,
    strategy_name: result.strategy_name,
    symbol: result.symbol,
    start_date: result.start_date,
    end_date: result.end_date,
    initial_cash: result.initial_cash,
    final_value: result.final_value,
    total_return: result.total_return,
    annual_return: result.annual_return,
    sharpe_ratio: result.sharpe_ratio,
    max_drawdown: result.max_drawdown,
    win_rate: result.win_rate,
    profit_factor: result.profit_factor,
    total_trades: result.total_trades,
    winning_trades: result.winning_trades,
    losing_trades: result.losing_trades,
    avg_holding_period: result.avg_holding_period,
    metrics_source: result.metrics_source,
    created_at: result.created_at
  }
}

/**
 * 导出交易记录
 */
export function exportTrades(
  trades: any[],
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

/**
 * 导出策略列表
 */
export function exportStrategies(
  strategies: any[],
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
export function exportMultipleFormats(
  data: any,
  formats: ExportFormat[],
  exporter: (data: any, format: ExportFormat) => void
): void {
  formats.forEach(format => {
    try {
      exporter(data, format)
    } catch (error) {
      console.error(`Failed to export as ${format}:`, error)
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
