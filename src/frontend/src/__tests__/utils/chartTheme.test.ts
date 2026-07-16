import { afterEach, describe, expect, it } from 'vitest'
import { getChartThemeColor, getChartThemeColors } from '@/utils/chartTheme'

describe('chart theme utilities', () => {
  afterEach(() => {
    document.documentElement.style.cssText = ''
  })

  it('uses the current semantic CSS variables for chart colors', () => {
    document.documentElement.style.setProperty('--primary-color', '#123456')
    document.documentElement.style.setProperty('--success-color', '#234567')
    document.documentElement.style.setProperty('--warning-color', '#345678')
    document.documentElement.style.setProperty('--danger-color', '#456789')
    document.documentElement.style.setProperty('--text-color-regular', '#56789A')
    document.documentElement.style.setProperty('--border-color', '#6789AB')
    document.documentElement.style.setProperty('--bg-color', '#789ABC')

    expect(getChartThemeColors()).toEqual({
      primary: '#123456',
      success: '#234567',
      warning: '#345678',
      danger: '#456789',
      text: '#56789A',
      border: '#6789AB',
      surface: '#789ABC',
    })
  })

  it('falls back when a semantic color is not available', () => {
    expect(getChartThemeColor('--missing-chart-color', '#ABCDEF')).toBe('#ABCDEF')
  })
})
