import { describe, expect, it } from 'vitest'

import {
  getCapabilitiesForDomain,
  getDomainByPath,
  getVisibleDomains,
} from '@/navigation/capabilities'

describe('navigation capabilities', () => {
  it('keeps operational data management in config while exposing data tables in market data', () => {
    const dataIds = getCapabilitiesForDomain('data', true).map((item) => item.id)
    expect(dataIds).toContain('data.quote')
    expect(dataIds).toContain('data.market')
    expect(dataIds).toContain('data.tables')
    expect(dataIds).not.toContain('data.topics')
    expect(dataIds).not.toContain('data.scripts')
    expect(dataIds).not.toContain('data.tasks')
    expect(dataIds).not.toContain('data.executions')
    expect(dataIds).not.toContain('data.sync')
    expect(dataIds).not.toContain('data.interfaces')
    expect(dataIds).not.toContain('data.optionsChain')

    const configIds = getCapabilitiesForDomain('config' as any, true).map((item) => item.id)
    expect(configIds).toEqual(['config.data', 'config.ai', 'config.gateways'])
    const investmentIds = getCapabilitiesForDomain('investment' as any, true).map((item) => item.id)
    expect(investmentIds).toEqual(['investment.stockAnalysis'])
    const tradingIds = getCapabilitiesForDomain('trading', true).map((item) => item.id)
    expect(tradingIds).not.toContain('trading.brokers')
    expect(tradingIds).not.toContain('trading.gateways')
    const portfolioIds = getCapabilitiesForDomain('portfolio', true).map((item) => item.id)
    expect(portfolioIds).not.toContain('portfolio.ledger')
    expect(getVisibleDomains(true).map((domain) => domain.id)).toContain('config')
    expect(getVisibleDomains(false).map((domain) => domain.id)).not.toContain('config')
    expect(getVisibleDomains(false).map((domain) => domain.id)).toEqual([
      'home',
      'data',
      'investment',
      'research',
      'trading',
      'portfolio',
      'ai',
    ])
    expect(getDomainByPath('/config/data/tasks').id).toBe('config')
    expect(getDomainByPath('/data/tasks').id).toBe('config')
    expect(getDomainByPath('/investment/stock-analysis').id).toBe('investment')
    expect(getDomainByPath('/data/tables').id).toBe('data')
    expect(getDomainByPath('/data/tables/1292').id).toBe('data')
    expect(getDomainByPath('/config/data/tables').id).toBe('data')
    expect(getDomainByPath('/config/gateways').id).toBe('config')
    expect(getDomainByPath('/trading/gateways').id).toBe('config')
  })
})
