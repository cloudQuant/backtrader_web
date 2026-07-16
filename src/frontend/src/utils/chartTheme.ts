/** Resolve semantic CSS colors for canvas charts, with SSR/test-safe fallbacks. */
export function getChartThemeColor(variable: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(variable).trim() || fallback
}

export function getChartThemeColors() {
  return {
    primary: getChartThemeColor('--primary-color', '#3b82f6'),
    success: getChartThemeColor('--success-color', '#10b981'),
    warning: getChartThemeColor('--warning-color', '#f59e0b'),
    danger: getChartThemeColor('--danger-color', '#ef4444'),
    text: getChartThemeColor('--text-color-regular', '#4b5563'),
    border: getChartThemeColor('--border-color', '#e5e7eb'),
    surface: getChartThemeColor('--bg-color', '#ffffff'),
  }
}
