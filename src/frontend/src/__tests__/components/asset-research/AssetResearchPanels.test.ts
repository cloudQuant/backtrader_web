import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import BondPanel from '@/components/asset-research/BondPanel.vue'
import FuturesPanel from '@/components/asset-research/FuturesPanel.vue'
import ModelCardPanel from '@/components/asset-research/ModelCardPanel.vue'
import type { InstrumentIdentity } from '@/api/assetResearch'

describe('asset-research panels', () => {
  it('renders futures contract facts and missing detail fallback', () => {
    const wrapper = mount(FuturesPanel, {
      props: {
        identity: {
          asset_type: 'futures',
          identity_level: 'CONTRACT',
          canonical_id: 'futures:CFFEX:IF2609:CNY',
          display_symbol: 'IF2609',
          name: '沪深300期货2609',
          venue: 'CFFEX',
          timezone: 'Asia/Shanghai',
          identifier_type: 'CONTRACT_CODE',
          identifier_value: 'IF2609',
          product_type: 'FUTURE',
          metadata_version: 'fixture-v1',
          details: {
            expiry_at: '2026-09-18T07:15:00+00:00',
            contract_multiplier: '300',
            trading_calendar_id: 'CFFEX',
          },
        } satisfies InstrumentIdentity,
        details: { basis: 12 },
      },
    })

    expect(wrapper.text()).toContain('2026-09-18T07:15:00+00:00')
    expect(wrapper.text()).toContain('CFFEX')
  })

  it('renders bond valuation facts', () => {
    const wrapper = mount(BondPanel, {
      props: {
        details: {
          yield_to_maturity: 0.023,
          modified_duration: 5.1,
          convexity: 31,
          dv01: 0.02,
          credit_spread_bps: 120,
        },
      },
    })

    expect(wrapper.text()).toContain('0.023')
    expect(wrapper.text()).toContain('120')
  })

  it('renders model card or research-only fallback', () => {
    const empty = mount(ModelCardPanel)
    expect(empty.text()).toContain('未提供已晋级模型卡')

    const filled = mount(ModelCardPanel, {
      props: {
        modelCard: {
          model_name: 'futures-shadow-v1',
          owner: 'quant-research',
          evaluation_manifest_hash: 'a'.repeat(64),
          limitations: ['研究观察'],
        },
      },
    })
    expect(filled.text()).toContain('futures-shadow-v1')
  })
})
