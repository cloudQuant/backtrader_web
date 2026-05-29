import i18n from '@/i18n'

function t(key: string, named?: Record<string, unknown>): string {
  return named ? i18n.global.t(key, named) : i18n.global.t(key)
}

export interface FormattedEntry {
  raw: string
  text?: string
  time?: string
  badge?: string
  badgeClass?: string
  levelClass?: string
}

export function formatLogLine(line: string): FormattedEntry {
  const raw = line
  if (!line) return { raw, text: ' ', levelClass: 'border-transparent' }

  // Try to parse a JSON line
  if (line.startsWith('{')) {
    try {
      const obj = JSON.parse(line) as Record<string, unknown>
      // Prefer event_time (typically local), else log_time (ISO needs local conversion)
      const eventTime = obj.event_time as string
      const logTime = obj.log_time as string
      const datetime = obj.datetime as string
      const time = formatLogTime(
        eventTime && !eventTime.startsWith('1970-') ? eventTime : logTime || datetime
      )
      const level = String(obj.level || '').toUpperCase()
      const eventType = String(obj.event_type || '')
      const status = String(obj.status || '')
      const dataName = obj.data_name != null && obj.data_name !== '' ? String(obj.data_name) : ''
      const strategyName = String(obj.strategy_name || '')
      const accountMasked = obj.account_id_masked ? String(obj.account_id_masked) : ''
      const provider = obj.provider ? String(obj.provider) : ''
      const errorCode = obj.error_code ? String(obj.error_code) : ''
      const errorMsg = obj.error_msg ? String(obj.error_msg) : ''

      // Tick log (tick.log)
      if (eventType === 'tick') {
        const symbol = String(obj.symbol || obj.instrument_id || '')
        const tickPrice = obj.price != null ? Number(obj.price) : null
        const tickVol = obj.volume != null ? Number(obj.volume) : null
        const bid = obj.bid_price != null ? Number(obj.bid_price) : null
        const ask = obj.ask_price != null ? Number(obj.ask_price) : null
        const bidVol = obj.bid_volume != null ? Number(obj.bid_volume) : null
        const askVol = obj.ask_volume != null ? Number(obj.ask_volume) : null
        const oi = obj.openinterest != null ? Number(obj.openinterest) : null
        const parts: string[] = []
        if (symbol) parts.push(`${t('commonUi.logLblSymbol')}:${symbol}`)
        if (tickPrice != null) parts.push(`${t('commonUi.logLblPrice')}:${tickPrice}`)
        if (tickVol != null) parts.push(`${t('commonUi.logLblVol')}:${tickVol}`)
        if (bid != null) parts.push(`${t('commonUi.logLblBid')}:${bid}`)
        if (bidVol != null) parts.push(`${t('commonUi.logLblBidVol')}:${bidVol}`)
        if (ask != null) parts.push(`${t('commonUi.logLblAsk')}:${ask}`)
        if (askVol != null) parts.push(`${t('commonUi.logLblAskVol')}:${askVol}`)
        if (oi != null) parts.push(`${t('commonUi.logLblOI')}:${oi}`)
        if (strategyName) parts.push(`${t('commonUi.logLblStrategy')}:${strategyName}`)
        return {
          raw: line,
          text: parts.join(' | '),
          time,
          badge: 'TICK',
          badgeClass: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/50 dark:text-cyan-200',
          levelClass: 'border-cyan-400 bg-cyan-50/30 dark:bg-cyan-900/10',
        }
      }

      // Bar/K-line log (bar.log)
      if (eventType === 'bar') {
        const symbol = String(obj.symbol || obj.instrument_id || '')
        const o = obj.open != null ? Number(obj.open) : null
        const h = obj.high != null ? Number(obj.high) : null
        const l = obj.low != null ? Number(obj.low) : null
        const c = obj.close != null ? Number(obj.close) : null
        const v = obj.volume != null ? Number(obj.volume) : null
        const oi = obj.openinterest != null ? Number(obj.openinterest) : null
        const interval = obj.interval || obj.period || ''
        const parts: string[] = []
        if (symbol) parts.push(`${t('commonUi.logLblSymbol')}:${symbol}`)
        if (interval) parts.push(`${t('commonUi.logLblInterval')}:${interval}`)
        if (o != null) parts.push(`O:${o}`)
        if (h != null) parts.push(`H:${h}`)
        if (l != null) parts.push(`L:${l}`)
        if (c != null) parts.push(`C:${c}`)
        if (v != null) parts.push(`V:${v}`)
        if (oi != null) parts.push(`${t('commonUi.logLblOI')}:${oi}`)
        if (strategyName) parts.push(`${t('commonUi.logLblStrategy')}:${strategyName}`)
        return {
          raw: line,
          text: parts.join(' | '),
          time,
          badge: 'BAR',
          badgeClass: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-200',
          levelClass: 'border-indigo-400 bg-indigo-50/30 dark:bg-indigo-900/10',
        }
      }

      // System event log (system.log)
      if (eventType) {
        const levelColors: Record<string, string> = {
          INFO: 'border-blue-400 bg-blue-50/50 dark:bg-blue-900/20',
          ERROR: 'border-red-400 bg-red-50/50 dark:bg-red-900/20',
          WARNING: 'border-amber-400 bg-amber-50/50 dark:bg-amber-900/20',
          DEBUG: 'border-slate-400 bg-slate-50/50 dark:bg-slate-800/30',
        }
        const badgeColors: Record<string, string> = {
          INFO: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200',
          ERROR: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200',
          WARNING: 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200',
          DEBUG: 'bg-slate-100 text-slate-600 dark:bg-slate-700/50 dark:text-slate-300',
        }
        const levelClass = levelColors[level] || levelColors.INFO
        const badgeClass = badgeColors[level] || badgeColors.INFO
        const parts: string[] = [eventType]
        if (status) parts.push(`[${status}]`)
        if (dataName) parts.push(`${t('commonUi.logLblSymbol')}:${dataName}`)
        if (strategyName) parts.push(`${t('commonUi.logLblStrategy')}:${strategyName}`)
        if (provider) parts.push(`${t('commonUi.logLblSource')}:${provider}`)
        if (accountMasked) parts.push(`${t('commonUi.logLblAccount')}:${accountMasked}`)
        if (errorCode) parts.push(`${t('commonUi.logLblErrorCode')}:${errorCode}`)
        if (errorMsg) parts.push(`${t('commonUi.logLblError')}:${errorMsg}`)
        const details = obj.details as Record<string, unknown> | undefined
        if (details && Object.keys(details).length > 0) {
          const d = JSON.stringify(details)
          if (d !== '{}') parts.push(d)
        }
        return {
          raw: line,
          text: parts.join(' | '),
          time,
          badge: level || 'LOG',
          badgeClass,
          levelClass,
        }
      }

      // Position log (position.log)
      if (obj.data_name != null && obj.size != null) {
        const size = Number(obj.size)
        const price = Number(obj.price ?? 0)
        const value = Number(obj.value ?? 0)
        const text = t('commonUi.logPosTpl', { sym: dataName, size, price: price.toFixed(2), value })
        return {
          raw: line,
          text,
          time,
          levelClass: 'border-emerald-400 bg-emerald-50/30 dark:bg-emerald-900/10',
        }
      }

      // Indicator log (indicator.log) — show key data only
      const close = obj.data_BtApiFeed_close ?? obj.dataprimary_BtApiFeed_close
      if (close != null) {
        const open = obj.data_BtApiFeed_open ?? obj.dataprimary_BtApiFeed_open
        const high = obj.data_BtApiFeed_high ?? obj.dataprimary_BtApiFeed_high
        const low = obj.data_BtApiFeed_low ?? obj.dataprimary_BtApiFeed_low
        const vol = obj.data_BtApiFeed_volume ?? obj.dataprimary_BtApiFeed_volume ?? 0
        const oi = obj.data_BtApiFeed_openinterest ?? obj.dataprimary_BtApiFeed_openinterest
        let text = `O:${Number(open).toFixed(1)} H:${Number(high).toFixed(1)} L:${Number(low).toFixed(1)} C:${Number(close).toFixed(1)}`
        if (Number(vol) > 0) text += ` V:${vol}`
        if (oi != null) text += ` OI:${oi}`
        return {
          raw: line,
          text: strategyName ? `[${strategyName}] ${text}` : text,
          time,
          levelClass: 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800/30',
        }
      }

      // Other JSON: pretty-print
      const keys = ['log_time', 'datetime', 'event_time', 'event_type', 'level', 'status', 'data_name']
      const parts: string[] = []
      for (const k of keys) {
        if (obj[k] != null && obj[k] !== '') {
          parts.push(`${k}: ${JSON.stringify(obj[k])}`)
        }
      }
      const rest = Object.entries(obj)
        .filter(([k]) => !keys.includes(k) && k !== 'details')
        .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
      const text = parts.length > 0 ? parts.join(' | ') : rest.slice(0, 5).join(' | ')
      return {
        raw: line,
        text: text || line.slice(0, 120) + (line.length > 120 ? '...' : ''),
        time,
        levelClass: 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-800/30',
      }
    } catch {
      // Parse failed; show as raw
    }
  }

  // TSV row: simple table-style display
  if (line.includes('\t')) {
    const cols = line.split('\t')
    return {
      raw: line,
      text: cols.map((c, i) => `[${i}]: ${c}`).join('  |  '),
      levelClass: 'border-slate-300 dark:border-slate-600',
    }
  }

  return { raw: line }
}

export function formatLogTime(s: string | undefined): string {
  if (!s) return ''
  // "1970-01-01" indicates an invalid time and is hidden
  if (s.startsWith('1970-01-01')) return ''
  try {
    // log_time is mostly UTC (e.g. "2026-03-10T05:57:20.264"); append 'Z' before parsing
    // event_time is mostly local (e.g. "2026-03-10 13:57:18"); parse directly
    let toParse = s.trim()
    // Only ISO-with-millis (log_time format, typically UTC) gets 'Z' suffix; event_time has space + no millis
    if (/T\d{2}:\d{2}:\d{2}\.\d+$/.test(toParse)) {
      toParse = toParse + 'Z'
    }
    toParse = toParse.replace(' ', 'T')
    const date = new Date(toParse)
    if (Number.isNaN(date.getTime())) return s.slice(0, 19)
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    const h = String(date.getHours()).padStart(2, '0')
    const min = String(date.getMinutes()).padStart(2, '0')
    const sec = String(date.getSeconds()).padStart(2, '0')
    return `${y}-${m}-${d} ${h}:${min}:${sec}`
  } catch {
    return s.slice(0, 19)
  }
}

// NOTE: previous version of this helper used `searchText.value` which only
// existed inside the SFC; this caused a TS reference error. We accept
// `searchText` from the caller to keep the helper pure and testable.
export function lineMatchesSearch(line: string, searchText = ''): boolean {
  if (!searchText.trim()) return false
  return line.toLowerCase().includes(searchText.toLowerCase())
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}
