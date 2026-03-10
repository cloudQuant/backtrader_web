import { defineStore } from 'pinia'
import { ref } from 'vue'

export type PortfolioTradingType = 'simulate' | 'live'

export const usePortfolioUiStore = defineStore('portfolioUi', () => {
  const tradingType = ref<PortfolioTradingType>('simulate')

  function setTradingType(value: PortfolioTradingType) {
    tradingType.value = value
  }

  return {
    tradingType,
    setTradingType,
  }
})

